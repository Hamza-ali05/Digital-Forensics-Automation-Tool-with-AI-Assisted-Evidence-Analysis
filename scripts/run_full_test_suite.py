"""Run every DFAT test category and emit a combined coverage report."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
COVERAGE_FILE = ROOT / ".coverage"
HTMLCOV = ROOT / "htmlcov"
PYTEST_INI_OVERRIDE = "-v --tb=short --strict-markers"

CATEGORIES: list[tuple[str, list[str], dict[str, str]]] = [
    ("Backend unit", ["pytest", "tests/unit/", "-v", "--cov=src/dfat", "--cov-append", "--cov-report="], {}),
    (
        "Backend integration",
        ["pytest", "tests/integration/", "-v", "--cov=src/dfat", "--cov-append", "--cov-report="],
        {},
    ),
    ("Contract", ["pytest", "tests/contract/", "-v", "--cov=src/dfat", "--cov-append", "--cov-report="], {}),
    ("Security", ["pytest", "tests/security/", "-v", "--cov=src/dfat", "--cov-append", "--cov-report="], {}),
    (
        "Validation",
        ["pytest", "tests/validation/", "-v", "--cov=src/dfat", "--cov-append", "--cov-report="],
        {},
    ),
    (
        "Regression",
        ["pytest", "tests/regression/", "-v", "--cov=src/dfat", "--cov-append", "--cov-report="],
        {},
    ),
    (
        "Performance",
        [
            "pytest",
            "tests/performance/",
            "-m",
            "performance and not requires_ollama",
            "-o",
            f"addopts={PYTEST_INI_OVERRIDE}",
            "-v",
            "--cov=src/dfat",
            "--cov-append",
            "--cov-report=",
        ],
        {},
    ),
    (
        "Frontend unit",
        ["npm", "test", "--", "--watchAll=false"],
        {
            "CI": "true",
            "NODE_OPTIONS": "--openssl-legacy-provider",
        },
    ),
    ("E2E", ["npx", "playwright", "test"], {"CI": "true", "NODE_OPTIONS": "--openssl-legacy-provider"}),
]


def _run(name: str, argv: list[str], extra_env: dict[str, str], cwd: Path) -> int:
    print(f"\n=== {name} ===", flush=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env.update(extra_env)
    completed = subprocess.run(argv, cwd=str(cwd), env=env, check=False)
    status = "PASS" if completed.returncode == 0 else "FAIL"
    print(f"--- {name}: {status} (exit {completed.returncode}) ---", flush=True)
    return completed.returncode


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    if COVERAGE_FILE.exists():
        COVERAGE_FILE.unlink()

    results: list[tuple[str, int]] = []
    for name, argv, extra_env in CATEGORIES:
        if name == "E2E" and os.environ.get("DFAT_SKIP_E2E") == "1":
            print(f"\n=== {name} ===\n--- skipped (DFAT_SKIP_E2E=1) ---", flush=True)
            continue
        if name == "Frontend unit" and os.environ.get("DFAT_SKIP_FRONTEND") == "1":
            print(f"\n=== {name} ===\n--- skipped (DFAT_SKIP_FRONTEND=1) ---", flush=True)
            continue
        command = list(argv)
        if command[0] in {"pytest", "npm", "npx"} and shutil.which(command[0]) is None:
            if command[0] == "pytest":
                command = [sys.executable, "-m", "pytest", *command[1:]]
            elif command[0] == "npm":
                command = ["npm.cmd" if os.name == "nt" else "npm", *command[1:]]
            elif command[0] == "npx":
                command = ["npx.cmd" if os.name == "nt" else "npx", *command[1:]]
        cwd = ROOT / "frontend" if name in {"Frontend unit", "E2E"} else ROOT
        results.append((name, _run(name, command, extra_env, cwd)))

    print("\n=== Combined backend coverage ===", flush=True)
    coverage_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/unit",
        "tests/integration",
        "tests/contract",
        "tests/security",
        "tests/validation",
        "tests/regression",
        "--cov=src/dfat",
        "--cov-append",
        f"--cov-report=html:{HTMLCOV}",
        f"--cov-report=xml:{REPORTS / 'coverage-full.xml'}",
        "--cov-report=term",
        "-q",
    ]
    # Report-only: reuse .coverage data already collected; a no-test collect can
    # fail if pytest still wants a path. Running coverage report is enough.
    report = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "report",
            "-m",
        ],
        cwd=str(ROOT),
        check=False,
    )
    html = subprocess.run(
        [sys.executable, "-m", "coverage", "html", "-d", str(HTMLCOV)],
        cwd=str(ROOT),
        check=False,
    )
    xml = subprocess.run(
        [sys.executable, "-m", "coverage", "xml", "-o", str(REPORTS / "coverage-full.xml")],
        cwd=str(ROOT),
        check=False,
    )
    if report.returncode != 0:
        # Fallback: one combined pytest coverage pass if coverage CLI is missing.
        subprocess.run(coverage_cmd, cwd=str(ROOT), check=False)
    _ = html.returncode, xml.returncode

    print("\n=== Full suite summary ===", flush=True)
    failed = 0
    for name, code in results:
        label = "PASS" if code == 0 else "FAIL"
        print(f"  {label:4}  {name}")
        if code != 0:
            failed += 1
    if failed:
        print(f"\nOVERALL: FAIL ({failed} categor{'y' if failed == 1 else 'ies'})")
        return 1
    print("\nOVERALL: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
