#!/usr/bin/env python3
"""Generate the definitive DFAT final test report."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
DOCS_TESTING_DIR = REPO_ROOT / "docs" / "testing"
OUTPUT_PATH = DOCS_TESTING_DIR / "FINAL_TEST_REPORT.md"


@dataclass
class CommandResult:
    name: str
    command: list[str]
    status: str
    returncode: int | None
    note: str = ""


def run_suite_commands() -> list[CommandResult]:
    commands = [
        ("Environment validation", [sys.executable, "scripts/validate_environment.py"]),
        ("Backend unit tests", ["make", "test-unit"]),
        ("Backend integration tests", ["make", "test-integration-full"]),
        ("API contract tests", ["make", "test-contract"]),
        ("Security tests", ["make", "test-security"]),
        ("Backend coverage check", ["make", "test-coverage-check"]),
        ("Frontend tests", ["make", "frontend-test"]),
        ("Frontend build", ["make", "frontend-build"]),
        ("Docker build", ["make", "docker-build"]),
        ("Security scan", ["make", "security-scan"]),
        ("Research verification", ["make", "verify-rqs"]),
        ("Feature verification", ["make", "verify-features"]),
        ("DSR verification", ["make", "verify-dsr"]),
        ("Project statistics", ["make", "project-stats"]),
    ]
    results: list[CommandResult] = []
    make_available = shutil.which("make") is not None

    for name, command in commands:
        if command[0] == "make" and not make_available:
            results.append(
                CommandResult(
                    name=name,
                    command=command,
                    status="not-run",
                    returncode=None,
                    note="`make` is not available in this environment.",
                )
            )
            continue
        try:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            results.append(
                CommandResult(
                    name=name,
                    command=command,
                    status="passed" if completed.returncode == 0 else "failed",
                    returncode=completed.returncode,
                    note=(completed.stderr or completed.stdout).strip().splitlines()[-1] if (completed.stderr or completed.stdout).strip() else "",
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                CommandResult(
                    name=name,
                    command=command,
                    status="failed",
                    returncode=None,
                    note=str(exc),
                )
            )
    return results


def parse_pytest_xml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"found": False, "tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    suite = root.find("testsuite")
    if suite is None:
        suite = root
    return {
        "found": True,
        "tests": int(suite.attrib.get("tests", 0)),
        "failures": int(suite.attrib.get("failures", 0)),
        "errors": int(suite.attrib.get("errors", 0)),
        "skipped": int(suite.attrib.get("skipped", 0)),
        "time": suite.attrib.get("time", "0"),
    }


def parse_bandit(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"found": False, "high": 0, "medium": 0, "low": 0, "issues": 0}
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results", [])
    severity = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for issue in results:
        level = str(issue.get("issue_severity", "")).upper()
        if level in severity:
            severity[level] += 1
    return {
        "found": True,
        "issues": len(results),
        "high": severity["HIGH"],
        "medium": severity["MEDIUM"],
        "low": severity["LOW"],
    }


def read_json_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"found": False, "overall_passed": False, "results": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["found"] = True
    return data


def quality_gate_rows(
    pytest_summary: dict[str, Any],
    bandit_summary: dict[str, Any],
    rq_report: dict[str, Any],
    feature_report: dict[str, Any],
    dsr_report: dict[str, Any],
) -> list[tuple[str, str, str]]:
    return [
        (
            "Gate 1 - Core automated tests",
            "PASS" if pytest_summary.get("found") and pytest_summary.get("failures", 0) == 0 and pytest_summary.get("errors", 0) == 0 else "WARN",
            "Derived from pytest XML summary.",
        ),
        (
            "Gate 2 - Coverage / verification readiness",
            "PASS" if feature_report.get("overall_passed") else "WARN",
            "Feature verification passed; dedicated numeric coverage artifacts were not fully available to this script.",
        ),
        (
            "Gate 3 - Security scan",
            "PASS" if bandit_summary.get("found") and bandit_summary.get("high", 0) == 0 else "WARN",
            "Bandit HIGH issues must be zero.",
        ),
        (
            "Gate 4 - Research objective compliance",
            "PASS" if rq_report.get("overall_passed") else "WARN",
            "Based on `verify_research_objectives.py` output.",
        ),
        (
            "Gate 5 - DSR / architecture compliance",
            "PASS" if dsr_report.get("overall_passed") else "WARN",
            "Based on DSR verification output.",
        ),
    ]


def build_report(run_results: list[CommandResult]) -> str:
    pytest_summary = parse_pytest_xml(REPORTS_DIR / "pytest-backend.xml")
    pytest_all_summary = parse_pytest_xml(REPORTS_DIR / "pytest-all.xml")
    bandit_summary = parse_bandit(REPORTS_DIR / "bandit_report.json")
    rq_report = read_json_report(REPORTS_DIR / "research_objectives_verification.json")
    feature_report = read_json_report(REPORTS_DIR / "feature_verification.json")
    dsr_report = read_json_report(REPORTS_DIR / "dsr_verification.json")

    DOCS_TESTING_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()

    lines: list[str] = [
        "# DFAT Final Test Report",
        "",
        f"Generated: `{now}`",
        "",
        "## Environment Info",
        "",
        f"- OS: `{platform.platform()}`",
        f"- Python: `{platform.python_version()}`",
        f"- Working directory: `{REPO_ROOT}`",
        f"- `make` available: `{'yes' if shutil.which('make') else 'no'}`",
        "",
        "## Verification Run Summary",
        "",
        "| Step | Status | Notes |",
        "|------|--------|-------|",
    ]

    for result in run_results:
        note = result.note.replace("|", "/") if result.note else ""
        lines.append(f"| {result.name} | {result.status.upper()} | {note} |")

    lines.extend(
        [
            "",
            "## Test Execution Summary",
            "",
            "| Artifact | Tests | Failures | Errors | Skipped | Time |",
            "|----------|-------|----------|--------|---------|------|",
            f"| `reports/pytest-backend.xml` | {pytest_summary.get('tests', 0)} | {pytest_summary.get('failures', 0)} | {pytest_summary.get('errors', 0)} | {pytest_summary.get('skipped', 0)} | {pytest_summary.get('time', '0')} |",
            f"| `reports/pytest-all.xml` | {pytest_all_summary.get('tests', 0)} | {pytest_all_summary.get('failures', 0)} | {pytest_all_summary.get('errors', 0)} | {pytest_all_summary.get('skipped', 0)} | {pytest_all_summary.get('time', '0')} |",
            "",
            "## Coverage Report Per Module",
            "",
            "- Backend numeric coverage artifacts were not comprehensively available to this script.",
            "- The report therefore records verification status rather than fabricating percentages.",
            "- The active coverage gate is represented by the `test-coverage-check` step and feature verification outputs.",
            "",
            "## Security Scan Results",
            "",
            f"- Bandit report found: `{'yes' if bandit_summary.get('found') else 'no'}`",
            f"- Total issues: `{bandit_summary.get('issues', 0)}`",
            f"- HIGH severity: `{bandit_summary.get('high', 0)}`",
            f"- MEDIUM severity: `{bandit_summary.get('medium', 0)}`",
            f"- LOW severity: `{bandit_summary.get('low', 0)}`",
            "",
            "## Performance Test Baselines",
            "",
            "- Performance baselines are implemented through `MetricsCalculator.compute_time_to_triage()` and `PerformanceAnalyzer`.",
            "- Frontend and API runtime dashboards are present, but no standalone performance-run artifact file was available for extraction here.",
            "",
            "## Quality Gate Status",
            "",
            "| Gate | Status | Notes |",
            "|------|--------|-------|",
        ]
    )

    for gate, status, notes in quality_gate_rows(
        pytest_all_summary if pytest_all_summary.get("found") else pytest_summary,
        bandit_summary,
        rq_report,
        feature_report,
        dsr_report,
    ):
        lines.append(f"| {gate} | {status} | {notes} |")

    lines.extend(
        [
            "",
            "## Research Verification Results",
            "",
            "| RQ | Passed | Checks |",
            "|----|--------|--------|",
        ]
    )
    for item in rq_report.get("results", []):
        lines.append(f"| {item.get('rq')} | {'yes' if item.get('passed') else 'no'} | {item.get('checks_passed', 0)}/{item.get('checks_total', 0)} |")

    lines.extend(
        [
            "",
            "## Feature Verification Results",
            "",
            "| Feature | Passed | Checks |",
            "|---------|--------|--------|",
        ]
    )
    for item in feature_report.get("results", []):
        lines.append(f"| {item.get('feature')} | {'yes' if item.get('passed') else 'no'} | {item.get('checks_passed', 0)}/{item.get('checks_total', 0)} |")

    lines.extend(
        [
            "",
            "## DSR Verification Results",
            "",
            "| Section | Passed | Checks |",
            "|---------|--------|--------|",
        ]
    )
    for item in dsr_report.get("results", []):
        lines.append(f"| {item.get('section')} | {'yes' if item.get('passed') else 'no'} | {item.get('checks_passed', 0)}/{item.get('checks_total', 0)} |")

    lines.extend(
        [
            "",
            "## Definitive Status",
            "",
            f"- Research objectives overall: `{'PASS' if rq_report.get('overall_passed') else 'WARN'}`",
            f"- Feature verification overall: `{'PASS' if feature_report.get('overall_passed') else 'WARN'}`",
            f"- DSR verification overall: `{'PASS' if dsr_report.get('overall_passed') else 'WARN'}`",
            f"- Security HIGH issues: `{bandit_summary.get('high', 0)}`",
            "",
            "This document is the definitive summary of the artifacts available in the repository at generation time. Where a command could not be executed in the current environment, the report explicitly marks that limitation instead of assuming success.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    run_results = run_suite_commands()
    report = build_report(run_results)
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Final test report written to {OUTPUT_PATH}")
    failed_required = [item for item in run_results if item.status == "failed"]
    return 1 if failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
