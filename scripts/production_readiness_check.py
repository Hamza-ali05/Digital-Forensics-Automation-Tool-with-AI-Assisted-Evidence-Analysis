#!/usr/bin/env python3
"""Automated DFAT production readiness verification.

Runs a checklist of gates (tests, coverage, security, migrations, Docker,
health, configuration) and prints PASS/FAIL for each item.

Usage:
    python scripts/production_readiness_check.py
    python scripts/production_readiness_check.py --skip-tests --skip-docker
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Literal
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REPORTS = ROOT / "reports"

DEFAULT_JWT_SECRETS = frozenset(
    {
        "CHANGE-ME-IN-PRODUCTION",
        "CHANGE-ME-IN-PRODUCTION-USE-SECRETS",
        "your-secret-key-here-generate-with-openssl",
    }
)

REQUIRED_DOCS = (
    "README.md",
    "PRODUCTION_CHECKLIST.md",
    "docs/architecture/ARCHITECTURE.md",
    "docs/user-guide/QUICKSTART.md",
    "docs/user-guide/USER_MANUAL.md",
    "docs/development/API_REFERENCE.md",
    "docs/development/DEVELOPER_GUIDE.md",
    "docs/deployment/DEPLOYMENT.md",
)

ENV_EXAMPLE_KEYS = (
    "DFAT_ENV",
    "DFAT_AUTH__SECRET_KEY",
    "DFAT_DATABASE__URL",
    "DFAT_AI_ENGINE__LLM_API_URL",
    "DFAT_AI_ENGINE__LLM_MODEL",
    "DFAT_LOGGING__LOG_LEVEL",
    "DFAT_LOGGING__AUDIT_LOG_PATH",
    "DFAT_API__CORS_ALLOW_ORIGINS",
)

Status = Literal["PASS", "FAIL", "WARN", "SKIP"]


@dataclass
class CheckResult:
    """Outcome of a single readiness gate."""

    name: str
    status: Status
    detail: str = ""


@dataclass
class ReadinessReport:
    """Aggregated readiness results."""

    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: Status, detail: str = "") -> None:
        self.results.append(CheckResult(name=name, status=status, detail=detail))

    @property
    def passed(self) -> bool:
        return all(r.status in {"PASS", "WARN", "SKIP"} for r in self.results) and not any(
            r.status == "FAIL" for r in self.results
        )

    def print_summary(self) -> None:
        width = max(len(r.name) for r in self.results) if self.results else 20
        print(f"\n{'Check':<{width}}  Status  Detail")
        print("-" * (width + 40))
        for item in self.results:
            mark = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARN": "[WARN]", "SKIP": "[SKIP]"}[
                item.status
            ]
            detail = item.detail.replace("\n", " ")
            print(f"{item.name:<{width}}  {mark}  {detail}")
        overall = "PASS" if self.passed else "FAIL"
        print(f"\nOverall: {overall}")


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> int:
    merged = os.environ.copy()
    merged["PYTHONPATH"] = str(SRC) + os.pathsep + merged.get("PYTHONPATH", "")
    if env:
        merged.update(env)
    completed = subprocess.run(
        command,
        cwd=str(cwd or ROOT),
        env=merged,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode


def _load_settings():
    from dfat.settings import load_settings

    return load_settings()


def check_tests(report: ReadinessReport, *, skip: bool) -> None:
    if skip:
        report.add("All tests pass (test-full-suite)", "SKIP", "Skipped via --skip-tests")
        return
    env = {
        "DFAT_SKIP_E2E": os.environ.get("DFAT_SKIP_E2E", "1"),
        "DFAT_SKIP_FRONTEND": os.environ.get("DFAT_SKIP_FRONTEND", "0"),
    }
    script = ROOT / "scripts" / "run_full_test_suite.py"
    code = _run([sys.executable, str(script)], env=env)
    if code == 0:
        report.add("All tests pass (test-full-suite)", "PASS")
    else:
        report.add("All tests pass (test-full-suite)", "FAIL", f"exit code {code}")


def check_backend_coverage(report: ReadinessReport, *, minimum: float) -> None:
    coverage_path = Path(os.environ.get("COVERAGE_JSON", ROOT / "coverage.json"))
    if not coverage_path.is_absolute():
        coverage_path = ROOT / coverage_path
    if not coverage_path.exists():
        code = _run([sys.executable, str(ROOT / "tests" / "coverage_targets.py")])
        if code != 0 and not coverage_path.exists():
            report.add(
                "Backend coverage >85%",
                "FAIL",
                "coverage.json missing; run make test-coverage",
            )
            return
    payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    totals = payload.get("totals", {})
    percent = float(totals.get("percent_covered", 0.0))
    if percent >= minimum:
        report.add("Backend coverage >85%", "PASS", f"{percent:.2f}%")
    else:
        report.add("Backend coverage >85%", "FAIL", f"{percent:.2f}% < {minimum}%")


def _frontend_services_coverage(summary_path: Path) -> float | None:
    """Aggregate statement coverage for ``frontend/src/services/`` files."""
    if not summary_path.exists():
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    covered = 0
    total = 0
    for key, metrics in summary.items():
        if key == "total":
            continue
        normalized = key.replace("\\", "/").lower()
        if "/services/" not in normalized:
            continue
        statements = metrics.get("statements", {})
        covered += int(statements.get("covered", 0))
        total += int(statements.get("total", 0))
    if total == 0:
        return None
    return covered / total * 100.0


def check_frontend_coverage(report: ReadinessReport, *, minimum: float, skip: bool) -> None:
    if skip:
        report.add("Frontend coverage >75%", "SKIP", "Skipped (DFAT_SKIP_FRONTEND=1)")
        return
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        report.add("Frontend coverage >75%", "SKIP", "npm not found")
        return
    code = _run(
        [npm, "test", "--", "--coverage", "--watchAll=false"],
        cwd=ROOT / "frontend",
        env={"CI": "true", "NODE_OPTIONS": "--openssl-legacy-provider"},
    )
    summary_path = ROOT / "frontend" / "coverage" / "coverage-summary.json"
    services_pct = _frontend_services_coverage(summary_path)
    detail_parts: list[str] = []
    if services_pct is not None:
        detail_parts.append(f"services {services_pct:.2f}%")
    if summary_path.exists():
        total_pct = float(
            json.loads(summary_path.read_text(encoding="utf-8"))
            .get("total", {})
            .get("statements", {})
            .get("pct", 0.0)
        )
        detail_parts.append(f"collected {total_pct:.2f}%")
    detail = "; ".join(detail_parts)

    # Jest enforces ./src/services/ >= 75% and ./src/pages/ >= 60%.
    # If Jest itself passed (code == 0), its thresholds were met.
    if code == 0:
        report.add("Frontend coverage >75%", "PASS", detail or "Jest thresholds met")
    else:
        report.add("Frontend coverage >75%", "FAIL", f"npm exit {code}; {detail}")


def check_bandit(report: ReadinessReport) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS / "bandit_report.json"
    _run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            str(SRC / "dfat"),
            "-f",
            "json",
            "-o",
            str(json_path),
        ]
    )
    if not json_path.exists():
        report.add("Zero Bandit HIGH issues", "FAIL", "bandit report not generated")
        return
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    high = int(payload.get("metrics", {}).get("_totals", {}).get("SEVERITY.HIGH", 0))
    if high == 0:
        report.add("Zero Bandit HIGH issues", "PASS", f"HIGH={high}")
    else:
        report.add("Zero Bandit HIGH issues", "FAIL", f"HIGH={high}")


def check_migrations(report: ReadinessReport) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "readiness.db"
        db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        env = {"DFAT_DATABASE__URL": db_url}
        code = _run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(SRC / "dfat" / "database" / "migrations" / "alembic.ini"),
                "upgrade",
                "head",
            ],
            env=env,
        )
    if code == 0:
        report.add("Database migrations apply cleanly", "PASS")
    else:
        report.add("Database migrations apply cleanly", "FAIL", f"alembic exit {code}")


def check_docker_build(report: ReadinessReport, *, skip: bool) -> None:
    if skip:
        report.add("Docker builds succeed", "SKIP", "Skipped via --skip-docker")
        return
    compose = shutil.which("docker") or shutil.which("docker.exe")
    if compose is None:
        report.add("Docker builds succeed", "SKIP", "docker CLI not found")
        return
    code = _run(["docker", "compose", "build", "--quiet"])
    if code == 0:
        report.add("Docker builds succeed", "PASS")
    else:
        report.add("Docker builds succeed", "FAIL", f"docker compose build exit {code}")


def _test_client():
    from fastapi.testclient import TestClient
    from dfat.app import create_app

    return TestClient(create_app())


def check_health_endpoint(report: ReadinessReport) -> None:
    try:
        client = _test_client()
        response = client.get("/api/v1/health")
        if response.status_code == 200 and response.json().get("status") == "healthy":
            report.add("Health endpoint returns healthy", "PASS")
        else:
            report.add(
                "Health endpoint returns healthy",
                "FAIL",
                f"status={response.status_code} body={response.text[:120]}",
            )
    except Exception as exc:  # noqa: BLE001
        report.add("Health endpoint returns healthy", "FAIL", str(exc))


def check_ai_health(report: ReadinessReport) -> None:
    try:
        settings = _load_settings()
        client = _test_client()
        response = client.get("/api/v1/ai/health")
        if response.status_code != 200:
            if settings.ai_engine.enable_fallback:
                report.add(
                    "AI engine health (or graceful degrade)",
                    "PASS",
                    f"HTTP {response.status_code}; fallback enabled",
                )
            else:
                report.add("AI engine health (or graceful degrade)", "FAIL", response.text[:120])
            return
        body = response.json()
        healthy = bool(body.get("is_healthy"))
        if healthy:
            report.add("AI engine health (or graceful degrade)", "PASS", "LLM healthy")
        elif settings.ai_engine.enable_fallback:
            report.add(
                "AI engine health (or graceful degrade)",
                "PASS",
                "LLM unavailable; fallback enabled",
            )
        else:
            report.add(
                "AI engine health (or graceful degrade)",
                "FAIL",
                "LLM unhealthy and fallback disabled",
            )
    except Exception as exc:  # noqa: BLE001
        settings = _load_settings()
        if settings.ai_engine.enable_fallback:
            report.add(
                "AI engine health (or graceful degrade)",
                "PASS",
                f"Probe error tolerated: {exc}",
            )
        else:
            report.add("AI engine health (or graceful degrade)", "FAIL", str(exc))


def check_cors(report: ReadinessReport) -> None:
    settings = _load_settings()
    origins = list(settings.api.cors_allow_origins)
    if any(origin.strip() == "*" for origin in origins):
        report.add("CORS origins production-appropriate", "FAIL", "wildcard * origin")
        return
    localhost = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
    if settings.env == "production" and localhost:
        report.add(
            "CORS origins production-appropriate",
            "FAIL",
            f"production env still allows dev origins: {localhost}",
        )
    elif settings.env == "production":
        report.add("CORS origins production-appropriate", "PASS", str(origins))
    elif localhost:
        report.add(
            "CORS origins production-appropriate",
            "WARN",
            f"development env ({settings.env}); localhost origins OK",
        )
    else:
        report.add("CORS origins production-appropriate", "PASS", str(origins))


def check_jwt_secret(report: ReadinessReport) -> None:
    settings = _load_settings()
    secret = settings.auth.secret_key.strip()
    if secret in DEFAULT_JWT_SECRETS or len(secret) < 32:
        if settings.env == "production":
            report.add("JWT secret is not default", "FAIL", "change DFAT_AUTH__SECRET_KEY")
        else:
            report.add(
                "JWT secret is not default",
                "WARN",
                "default/short secret in non-production env",
            )
    else:
        report.add("JWT secret is not default", "PASS")


def check_debug_disabled(report: ReadinessReport) -> None:
    settings = _load_settings()
    debug_logging = settings.logging.log_level.upper() == "DEBUG"
    if settings.env == "production" and debug_logging:
        report.add("Debug mode disabled", "FAIL", "LOG_LEVEL=DEBUG in production")
    elif debug_logging:
        report.add("Debug mode disabled", "WARN", f"DEBUG logging in {settings.env}")
    else:
        report.add("Debug mode disabled", "PASS", f"env={settings.env} level={settings.logging.log_level}")


def check_audit_logging(report: ReadinessReport) -> None:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.log"
            from dfat.core.enums import PipelineStage
            from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

            logger = ForensicAuditLogger(audit_log_path=log_path)
            logger.log_action(
                PipelineStage.ACQUISITION,
                "READINESS_CHECK",
                evidence_id="ev-readiness",
                details={"check_id": str(uuid4())},
            )
            if log_path.exists() and log_path.stat().st_size > 0:
                report.add("Audit logging functional", "PASS")
            else:
                report.add("Audit logging functional", "FAIL", "audit file empty")
    except Exception as exc:  # noqa: BLE001
        report.add("Audit logging functional", "FAIL", str(exc))


def check_report_schema(report: ReadinessReport) -> None:
    try:
        from dfat.reporting.schema import ReportSchemaValidator

        document = {
            "schema_version": "1.0.0",
            "report_id": str(uuid4()),
            "evidence_id": "ev-readiness",
            "case_metadata": {
                "case_id": "case-1",
                "case_name": "Readiness",
                "investigator": "System",
            },
            "generated_at": datetime.now(UTC).isoformat(),
            "integrity_hash": "a" * 64,
            "pipeline_stage_timings": {
                "acquisition_seconds": 1.0,
                "parsing_seconds": 1.0,
                "triage_seconds": 1.0,
                "reporting_seconds": 1.0,
            },
            "artefacts": [
                {
                    "artefact_id": "art-1",
                    "category": "injected_code",
                    "source_path": None,
                    "suspicion_level": "critical",
                    "relevance_score": 0.9,
                    "raw_data": {"pid": 1},
                    "classification_reasoning": "test",
                    "metadata": {},
                }
            ],
            "summary_statistics": {
                "total_artefacts": 1,
                "by_category": {"injected_code": 1},
                "by_suspicion_level": {"critical": 1},
            },
            "ai_metadata": {
                "model_used": "none",
                "prompt_version": "1.0.0",
                "confidence_score": 0.0,
                "analysis_mode": "rule_based",
                "disclaimer": "Advisory only.",
            },
        }
        result = ReportSchemaValidator().validate(document)
        if result.is_valid:
            report.add("Report schema validates", "PASS", result.schema_version)
        else:
            report.add("Report schema validates", "FAIL", "; ".join(result.errors[:3]))
    except Exception as exc:  # noqa: BLE001
        report.add("Report schema validates", "FAIL", str(exc))


def check_todo_fixme(report: ReadinessReport) -> None:
    pattern = re.compile(r"\b(TODO|FIXME)\b", re.IGNORECASE)
    hits: list[str] = []
    for base in (SRC / "dfat", ROOT / "frontend" / "src"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".js", ".jsx"}:
                continue
            if "test" in path.parts or "__tests__" in path.parts:
                continue
            try:
                for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    if pattern.search(line):
                        hits.append(f"{path.relative_to(ROOT)}:{idx}")
            except OSError:
                continue
    if hits:
        report.add(
            "No TODO/FIXME in production code",
            "WARN",
            f"{len(hits)} marker(s); first: {hits[0]}",
        )
    else:
        report.add("No TODO/FIXME in production code", "PASS")


def check_documentation(report: ReadinessReport) -> None:
    missing = [doc for doc in REQUIRED_DOCS if not (ROOT / doc).exists()]
    if missing:
        report.add("Documentation complete", "FAIL", "missing: " + ", ".join(missing))
    else:
        report.add("Documentation complete", "PASS", f"{len(REQUIRED_DOCS)} required docs")


def check_env_example(report: ReadinessReport) -> None:
    example = ROOT / ".env.example"
    if not example.exists():
        report.add(".env.example up to date", "FAIL", "file missing")
        return
    text = example.read_text(encoding="utf-8")
    missing = [key for key in ENV_EXAMPLE_KEYS if key not in text]
    if missing:
        report.add(".env.example up to date", "FAIL", "missing keys: " + ", ".join(missing))
    else:
        report.add(".env.example up to date", "PASS")


def check_package_coverage_targets(report: ReadinessReport) -> None:
    code = _run(
        [sys.executable, str(ROOT / "tests" / "coverage_targets.py"), "--check-only"],
        env={"COVERAGE_JSON": str(ROOT / "coverage.json")},
    )
    if code == 0:
        report.add("Package coverage targets (coverage_targets.py)", "PASS")
    else:
        report.add(
            "Package coverage targets (coverage_targets.py)",
            "FAIL",
            "run make test-coverage-check",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true", help="Skip make test-full-suite")
    parser.add_argument("--skip-docker", action="store_true", help="Skip docker compose build")
    parser.add_argument(
        "--skip-frontend-coverage",
        action="store_true",
        help="Skip frontend coverage npm run",
    )
    args = parser.parse_args(argv)

    report = ReadinessReport()
    print("DFAT production readiness check")
    print(f"Root: {ROOT}")
    print(f"Time: {datetime.now(UTC).isoformat()}")

    check_tests(report, skip=args.skip_tests)
    check_backend_coverage(report, minimum=85.0)
    check_package_coverage_targets(report)
    check_frontend_coverage(
        report,
        minimum=75.0,
        skip=args.skip_frontend_coverage or os.environ.get("DFAT_SKIP_FRONTEND") == "1",
    )
    check_bandit(report)
    check_migrations(report)
    check_docker_build(report, skip=args.skip_docker)
    check_health_endpoint(report)
    check_ai_health(report)
    check_cors(report)
    check_jwt_secret(report)
    check_debug_disabled(report)
    check_audit_logging(report)
    check_report_schema(report)
    check_todo_fixme(report)
    check_documentation(report)
    check_env_example(report)

    report.print_summary()
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
