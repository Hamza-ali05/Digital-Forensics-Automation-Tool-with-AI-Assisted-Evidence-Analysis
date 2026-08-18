#!/usr/bin/env python3
"""Generate DFAT project statistics for documentation and thesis reporting.

Usage:
    python scripts/generate_project_stats.py
    python scripts/generate_project_stats.py --no-write   # console only
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "dfat"
FRONTEND_SRC = ROOT / "frontend" / "src"
OUTPUT = ROOT / "docs" / "PROJECT_STATS.md"
TESTS_ROOT = ROOT / "tests"

FILE_TYPES = (".py", ".js", ".json", ".md", ".yml", ".yaml")

TEST_CATEGORIES = (
    ("unit", ROOT / "tests" / "unit"),
    ("integration", ROOT / "tests" / "integration"),
    ("contract", ROOT / "tests" / "contract"),
    ("security", ROOT / "tests" / "security"),
    ("validation", ROOT / "tests" / "validation"),
    ("regression", ROOT / "tests" / "regression"),
    ("performance", ROOT / "tests" / "performance"),
    ("quality", ROOT / "tests" / "quality"),
    ("e2e", ROOT / "frontend" / "e2e"),
    ("frontend_unit", ROOT / "frontend" / "src" / "__tests__"),
)


def _count_lines(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        try:
            total += len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    return total


def _iter_files(base: Path, suffix: str) -> list[Path]:
    if not base.exists():
        return []
    return [p for p in base.rglob(f"*{suffix}") if p.is_file()]


def count_files_by_type() -> Counter[str]:
    counts: Counter[str] = Counter()
    # Keep this inventory scoped to source + docs to avoid counting coverage reports,
    # node_modules, and other generated artifacts.
    scope_roots = [ROOT / "src", ROOT / "frontend" / "src", ROOT / "docs", ROOT / "scripts"]
    for scope_root in scope_roots:
        for path in scope_root.rglob("*"):
            if not path.is_file():
                continue
            if any(
                part in {".git", "node_modules", ".venv", "htmlcov", "__pycache__"}
                for part in path.parts
            ):
                continue
            suffix = path.suffix.lower()
            if suffix in FILE_TYPES:
                counts[suffix] += 1
            elif suffix == ".yaml":
                counts[".yml"] += 1
    return counts


def count_python_files_src_dfat() -> int:
    """Count backend Python files under ``src/dfat`` only."""
    return len(list(SRC.rglob("*.py")))


def count_js_files_frontend_src() -> int:
    """Count frontend JS/JSX files under ``frontend/src`` only."""
    js = list(FRONTEND_SRC.rglob("*.js"))
    jsx = list(FRONTEND_SRC.rglob("*.jsx"))
    return len(js) + len(jsx)


def count_backend_test_files() -> int:
    """Count backend test files matching ``test_*.py``."""
    if not TESTS_ROOT.exists():
        return 0
    return len(list(TESTS_ROOT.rglob("test_*.py")))


def count_frontend_unit_test_files() -> int:
    """Count frontend unit test files matching ``*.test.js``."""
    unit = FRONTEND_SRC / "__tests__"
    if not unit.exists():
        return 0
    return len(list(unit.rglob("*.test.js")))


def count_e2e_spec_files() -> int:
    """Count Playwright e2e spec files."""
    e2e = ROOT / "frontend" / "e2e"
    if not e2e.exists():
        return 0
    return len(list(e2e.glob("*.spec.js")))


def count_react_pages() -> int:
    pages_dir = FRONTEND_SRC / "pages"
    if not pages_dir.exists():
        return 0
    return len([p for p in pages_dir.rglob("*.js") if p.is_file()]) + len(
        [p for p in pages_dir.rglob("*.jsx") if p.is_file()]
    )


def count_react_components() -> int:
    components_dir = FRONTEND_SRC / "components"
    if not components_dir.exists():
        return 0
    return len([p for p in components_dir.rglob("*.js") if p.is_file()]) + len(
        [p for p in components_dir.rglob("*.jsx") if p.is_file()]
    )


def count_pytest_tests() -> dict[str, int]:
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    results: dict[str, int] = {}
    for name, directory in TEST_CATEGORIES:
        if not directory.exists():
            results[name] = 0
            continue
        if name == "e2e":
            spec_files = list(directory.glob("*.spec.js"))
            results[name] = len(spec_files)
            continue
        if name == "frontend_unit":
            results[name] = len(list(directory.rglob("*.test.js")))
            continue
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", str(directory), "--collect-only", "-q"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        match = re.search(r"(\d+)\s+test", completed.stdout + completed.stderr)
        results[name] = int(match.group(1)) if match else 0
    return results


def backend_coverage_percent() -> float | None:
    path = ROOT / "coverage.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return float(payload.get("totals", {}).get("percent_covered", 0.0))


def frontend_coverage_percent() -> tuple[float | None, float | None]:
    path = ROOT / "frontend" / "coverage" / "coverage-summary.json"
    if not path.exists():
        return None, None
    payload = json.loads(path.read_text(encoding="utf-8"))
    total = float(payload.get("total", {}).get("statements", {}).get("pct", 0.0))
    services_covered = 0
    services_total = 0
    for key, metrics in payload.items():
        if key == "total":
            continue
        if "/services/" not in key.replace("\\", "/").lower():
            continue
        statements = metrics.get("statements", {})
        services_covered += int(statements.get("covered", 0))
        services_total += int(statements.get("total", 0))
    services_pct = (services_covered / services_total * 100.0) if services_total else None
    return total, services_pct


def count_adrs() -> int:
    adr_dir = ROOT / "docs" / "architecture" / "adr"
    if not adr_dir.exists():
        return 0
    return len(
        [
            p
            for p in adr_dir.glob("*.md")
            if p.name.lower().startswith("adr-") or re.match(r"^\d{3}-", p.name)
        ]
    )


def count_api_endpoints() -> int:
    count = 0
    routes_dir = ROOT / "src" / "dfat" / "api" / "routes"
    route_pattern = re.compile(
        r'@router\.(get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']',
        re.MULTILINE,
    )
    for path in routes_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        count += len(route_pattern.findall(text))
    return count


def count_database_tables() -> int:
    """Count SQLAlchemy tables for reporting.

    The project's checklist treats *auxiliary* tables (history / junction link
    tables) as out of scope for the DB table metric.
    """

    models_dir = ROOT / "src" / "dfat" / "database" / "models"
    excluded_suffixes = ("_history",)
    excluded_contains = ("_investigators",)

    tablenames: set[str] = set()
    for path in models_dir.glob("*.py"):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = re.findall(r"__tablename__\s*=\s*[\"']([^\"']+)[\"']", text)
        for name in matches:
            lowered = name.lower()
            if any(lowered.endswith(suf) for suf in excluded_suffixes):
                continue
            if any(part in lowered for part in excluded_contains):
                continue
            tablenames.add(name)
    return len(tablenames)


def count_pydantic_models() -> int:
    """Count pydantic BaseModel subclasses (AST-based)."""

    import ast

    def is_base_model(expr: ast.expr) -> bool:
        # Match `BaseModel` and `something.BaseModel` styles.
        if isinstance(expr, ast.Name):
            return expr.id.endswith("BaseModel")
        if isinstance(expr, ast.Attribute):
            return expr.attr.endswith("BaseModel")
        return False

    total = 0
    for path in (ROOT / "src" / "dfat").rglob("*.py"):
        if "test" in path.parts:
            continue
        # Exclude ORM models; those are SQLAlchemy declarative, not pydantic.
        if "database" in path.parts and "models" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if any(is_base_model(base) for base in node.bases):
                total += 1
    return total


def count_services() -> int:
    """Count concrete service classes under `src/dfat/services`."""
    services = ROOT / "src" / "dfat" / "services"
    if not services.exists():
        return 0
    total = 0
    for path in services.glob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        total += len(re.findall(r"^class\s+\w+.*Service\b", text, flags=re.MULTILINE))
    return total


def count_repositories() -> int:
    """Count repository classes under `src/dfat/database/repositories`."""
    repos = ROOT / "src" / "dfat" / "database" / "repositories"
    if not repos.exists():
        return 0
    total = 0
    for path in repos.glob("*.py"):
        if path.name in {"__init__.py", "base_repo.py"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        total += len(re.findall(r"^class\s+\w+.*Repository\b", text, flags=re.MULTILINE))
    return total


def build_markdown(stats: dict[str, object]) -> str:
    files = stats["files_by_type"]
    tests = stats["test_counts"]
    lines = [
        "# DFAT Project Statistics",
        "",
        f"Generated: {stats['generated_at']}",
        "",
        "## Files by type",
        "",
        "| Extension | Count |",
        "|-----------|------:|",
    ]
    for ext in sorted(files.keys()):
        lines.append(f"| `{ext}` | {files[ext]} |")
    lines.extend(
        [
            "",
            "## Lines of code",
            "",
            f"| Area | Lines |",
            f"|------|------:|",
            f"| Backend Python (`src/dfat`) | {stats['backend_loc']} |",
            f"| Frontend JS/JSX (`frontend/src`) | {stats['frontend_loc']} |",
            "",
            "## Tests by category",
            "",
            "| Category | Count |",
            "|----------|------:|",
        ]
    )
    for name, count in tests.items():
        lines.append(f"| {name} | {count} |")
    lines.append(f"| **Total (approx.)** | **{sum(tests.values())}** |")
    coverage_lines = [
        f"- Backend (overall): **{stats['backend_coverage']:.2f}%**"
        if stats["backend_coverage"] is not None
        else "- Backend (overall): _run `make test-coverage`_",
        f"- Frontend (collected statements): **{stats['frontend_coverage']:.2f}%**"
        if stats["frontend_coverage"] is not None
        else "- Frontend (collected statements): _run `cd frontend && npm run test:coverage`_",
    ]
    if stats.get("frontend_services_coverage") is not None:
        coverage_lines.append(
            f"- Frontend (services layer): **{stats['frontend_services_coverage']:.2f}%**"
        )
    lines.extend(
        [
            "",
            "## Coverage",
            "",
            *coverage_lines,
            "",
            "## Architecture inventory",
            "",
            f"| Metric | Count |",
            f"|--------|------:|",
            f"| ADRs | {stats['adr_count']} |",
            f"| API route decorators | {stats['api_endpoints']} |",
            f"| Total Python files (`src/dfat`) | {stats['python_files']} |",
            f"| Total JavaScript files (`frontend/src`) | {stats['js_files']} |",
            f"| Total backend test files (`tests`) | {stats['backend_test_files']} |",
            f"| Total frontend unit test files (`frontend/src/__tests__`) | {stats['frontend_unit_test_files']} |",
            f"| E2E spec files (`frontend/e2e/*.spec.js`) | {stats['e2e_spec_files']} |",
            f"| React pages (`frontend/src/pages`) | {stats['react_pages']} |",
            f"| React components (`frontend/src/components`) | {stats['react_components']} |",
            f"| Database tables (`__tablename__`) | {stats['db_tables']} |",
            f"| Pydantic domain models | {stats['pydantic_models']} |",
            f"| Application services | {stats['services']} |",
            f"| SQLAlchemy repositories | {stats['repositories']} |",
            "",
            "_Auto-generated by `scripts/generate_project_stats.py`. Do not edit by hand._",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true", help="Skip writing docs/PROJECT_STATS.md")
    args = parser.parse_args(argv)

    backend_py = _iter_files(SRC, ".py")
    frontend_js = _iter_files(FRONTEND_SRC, ".js") + _iter_files(FRONTEND_SRC, ".jsx")

    total_cov, services_cov = frontend_coverage_percent()
    stats: dict[str, object] = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "files_by_type": dict(count_files_by_type()),
        "python_files": count_python_files_src_dfat(),
        "js_files": count_js_files_frontend_src(),
        "backend_loc": _count_lines(backend_py),
        "frontend_loc": _count_lines(frontend_js),
        "backend_test_files": count_backend_test_files(),
        "frontend_unit_test_files": count_frontend_unit_test_files(),
        "e2e_spec_files": count_e2e_spec_files(),
        "react_pages": count_react_pages(),
        "react_components": count_react_components(),
        "test_counts": count_pytest_tests(),
        "backend_coverage": backend_coverage_percent(),
        "frontend_coverage": total_cov,
        "frontend_services_coverage": services_cov,
        "adr_count": count_adrs(),
        "api_endpoints": count_api_endpoints(),
        "db_tables": count_database_tables(),
        "pydantic_models": count_pydantic_models(),
        "services": count_services(),
        "repositories": count_repositories(),
    }

    markdown = build_markdown(stats)
    print(markdown)
    if not args.no_write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(markdown, encoding="utf-8")
        print(f"\nWrote {OUTPUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
