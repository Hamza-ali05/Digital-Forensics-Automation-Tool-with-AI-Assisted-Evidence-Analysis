"""Run coverage and enforce package-level DFAT coverage targets."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

MODULE_TARGETS = {
    "dfat/core": 95,
    "dfat/database": 85,
    "dfat/services": 85,
    "dfat/forensic_engine": 80,
    "dfat/pipeline": 85,
    "dfat/ai_engine": 80,
    "dfat/reporting": 85,
    "dfat/evaluation": 90,
}


def _normalise_relative(raw_path: str) -> str:
    """Map coverage file paths to ``dfat/...`` package-relative form."""
    normalised = raw_path.replace("\\", "/")
    if "/src/" in normalised:
        normalised = normalised.split("/src/", 1)[-1]
    normalised = normalised.lstrip("./")
    if normalised.startswith("src/"):
        normalised = normalised.removeprefix("src/")
    return normalised


def _run_pytest(output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "--cov=src/dfat",
        "--cov-report=term-missing",
        "--cov-report=html",
        f"--cov-report=json:{output_path}",
    ]
    return subprocess.run(command, check=False).returncode


def _aggregate(coverage_path: Path) -> dict[str, tuple[int, int, float]]:
    payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    files = payload.get("files", {})
    totals = {package: [0, 0] for package in MODULE_TARGETS}

    for raw_path, details in files.items():
        relative = _normalise_relative(raw_path)
        summary = details.get("summary", {})
        statements = int(summary.get("num_statements", 0))
        covered = int(summary.get("covered_lines", 0))
        for package in MODULE_TARGETS:
            if relative == package + ".py" or relative.startswith(package + "/"):
                totals[package][0] += covered
                totals[package][1] += statements
                break

    result: dict[str, tuple[int, int, float]] = {}
    for package, (covered, statements) in totals.items():
        percent = (covered / statements * 100.0) if statements else 0.0
        result[package] = (covered, statements, percent)
    return result


def _print_table(results: dict[str, tuple[int, int, float]]) -> list[str]:
    failures: list[str] = []
    print(f"{'Package':<24} {'Covered':>9} {'Total':>7} {'Actual':>8} {'Target':>8}  Status")
    print("-" * 75)
    for package, target in MODULE_TARGETS.items():
        covered, total, actual = results[package]
        passed = actual >= target
        status = "PASS" if passed else "MISS"
        print(
            f"{package:<24} {covered:>9} {total:>7} "
            f"{actual:>7.2f}% {target:>7.2f}%  {status}"
        )
        if not passed:
            failures.append(package)
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Read existing coverage JSON without running pytest.",
    )
    args = parser.parse_args(argv)

    env_path = os.environ.get("COVERAGE_JSON")
    coverage_path = Path(env_path or "coverage.json").resolve()
    skip_run = args.check_only or (env_path is not None and coverage_path.exists())

    if not skip_run:
        pytest_status = _run_pytest(coverage_path)
        if pytest_status != 0:
            print(f"pytest failed with exit code {pytest_status}", file=sys.stderr)
            return pytest_status
    if not coverage_path.exists():
        print(f"Coverage JSON not found: {coverage_path}", file=sys.stderr)
        return 2

    failures = _print_table(_aggregate(coverage_path))
    if failures:
        print("\nMissed targets: " + ", ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
