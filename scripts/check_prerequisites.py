#!/usr/bin/env python3
"""Verify DFAT launcher prerequisites (stdlib only).

Required: Python 3.11+, Node.js 18+, npm, pip.
Optional: git (warning), Ollama (info).
Exit code 0 when all required checks pass, 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


MIN_PYTHON = (3, 11)
MIN_NODE_MAJOR = 18
OLLAMA_URL = "http://localhost:11434/api/version"


@dataclass
class CheckResult:
    level: str  # OK, WARN, INFO, FAIL
    label: str
    detail: str


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, output.strip()


def _parse_semver(text: str) -> Optional[tuple[int, ...]]:
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        match = re.search(r"v?(\d+)\.(\d+)", text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def check_python() -> CheckResult:
    version = sys.version_info[:3]
    version_str = ".".join(str(part) for part in version)
    if version[:2] < MIN_PYTHON:
        return CheckResult(
            "FAIL",
            "Python",
            f"{version_str} — need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ "
            f"(https://www.python.org/downloads/)",
        )
    return CheckResult("OK", "Python", version_str)


def check_pip() -> CheckResult:
    code, output = _run([sys.executable, "-m", "pip", "--version"])
    if code != 0:
        return CheckResult(
            "FAIL",
            "pip",
            "not available — try: python -m ensurepip --upgrade",
        )
    version_match = re.search(r"pip\s+(\S+)", output)
    version = version_match.group(1) if version_match else output.splitlines()[0]
    return CheckResult("OK", "pip", version)


def check_node() -> CheckResult:
    node = shutil.which("node")
    if not node:
        return CheckResult(
            "FAIL",
            "Node.js",
            "not found — install 18+ from https://nodejs.org/",
        )
    code, output = _run([node, "--version"])
    if code != 0:
        return CheckResult("FAIL", "Node.js", f"cannot run node --version: {output}")
    parsed = _parse_semver(output)
    if parsed is None:
        return CheckResult("FAIL", "Node.js", f"unparseable version: {output}")
    if parsed[0] < MIN_NODE_MAJOR:
        return CheckResult(
            "FAIL",
            "Node.js",
            f"v{'.'.join(str(p) for p in parsed)} — need {MIN_NODE_MAJOR}+",
        )
    return CheckResult("OK", "Node.js", f"v{'.'.join(str(p) for p in parsed)}")


def check_npm() -> CheckResult:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        return CheckResult(
            "FAIL",
            "npm",
            "not found — reinstall Node.js from https://nodejs.org/",
        )
    code, output = _run([npm, "--version"])
    if code != 0:
        return CheckResult("FAIL", "npm", f"cannot run npm --version: {output}")
    return CheckResult("OK", "npm", output.splitlines()[0].strip())


def check_git() -> CheckResult:
    git = shutil.which("git")
    if not git:
        return CheckResult("WARN", "git", "not found (optional)")
    code, output = _run([git, "--version"])
    if code != 0:
        return CheckResult("WARN", "git", "not found (optional)")
    version_match = re.search(r"git version (\S+)", output)
    version = version_match.group(1) if version_match else output
    return CheckResult("OK", "git", version)


def check_ollama() -> CheckResult:
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=2) as response:
            if 200 <= response.status < 300:
                return CheckResult("OK", "Ollama", "running at localhost:11434")
    except (urllib.error.URLError, TimeoutError, OSError):
        pass
    return CheckResult(
        "INFO",
        "Ollama",
        "not detected (optional — AI will use rule-based fallback)",
    )


def run_checks() -> list[CheckResult]:
    return [
        check_python(),
        check_node(),
        check_npm(),
        check_pip(),
        check_git(),
        check_ollama(),
    ]


def _format_line(item: CheckResult) -> str:
    tag = item.level if item.level != "FAIL" else "FAIL"
    if tag == "OK":
        tag = "OK  "
    elif tag == "WARN":
        tag = "WARN"
    elif tag == "INFO":
        tag = "INFO"
    else:
        tag = "FAIL"
    return f"[{tag}] {item.label} {item.detail}"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check DFAT launcher prerequisites")
    parser.parse_args(argv)

    results = run_checks()
    print("DFAT prerequisite report")
    print("=" * 56)
    for item in results:
        print(_format_line(item))
    print("=" * 56)

    failed = [item for item in results if item.level == "FAIL"]
    if failed:
        print("\nRequired checks failed. Fix the FAIL items above.", file=sys.stderr)
        return 1
    print("\nAll required checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
