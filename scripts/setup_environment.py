#!/usr/bin/env python3
"""First-run DFAT environment setup for the one-click launcher.

Idempotent: skips completed steps on subsequent runs. Stdlib + pip/npm only.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / ".dfat"
SETUP_MARKER = STATE_DIR / "setup_complete"
VENV_DIR = REPO_ROOT / ".venv"
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
ALEMBIC_INI = REPO_ROOT / "src" / "dfat" / "database" / "migrations" / "alembic.ini"

REQUIRED_DIRS = (
    "data/evidence",
    "data/datasets",
    "data/outputs",
    "data/outputs/reports",
    "data/knowledge",
    "data/knowledge/vector_store",
    "data/knowledge/graph",
    "data/knowledge/ioc_db",
    "data/ml/models",
    "data/ml/experiments",
    "data/ground_truth",
    "data/questionnaire",
    "data/questionnaire/responses",
)


def _print(msg: str) -> None:
    print(msg, flush=True)


def _run(
    cmd: list[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
) -> None:
    display = " ".join(cmd)
    _print(f"  > {display}")
    completed = subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {display}")


def venv_python() -> Path:
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_exists() -> bool:
    return venv_python().is_file()


def ensure_venv() -> Path:
    if venv_exists():
        _print(f"[skip] Virtual environment already exists: {VENV_DIR}")
        return venv_python()
    _print(f"[setup] Creating virtual environment at {VENV_DIR}")
    builder = venv.EnvBuilder(with_pip=True, clear=False, upgrade_deps=False)
    builder.create(VENV_DIR)
    python = venv_python()
    if not python.is_file():
        raise RuntimeError(f"Virtual environment created but python missing: {python}")
    return python


def ensure_env_file() -> None:
    if ENV_FILE.is_file():
        _print("[skip] .env already present")
        return
    if not ENV_EXAMPLE.is_file():
        raise RuntimeError(".env.example is missing — cannot create .env")
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    generated = secrets.token_urlsafe(32)
    text = re.sub(
        r"(?m)^DFAT_AUTH__SECRET_KEY=.*$",
        f"DFAT_AUTH__SECRET_KEY={generated}",
        text,
        count=1,
    )
    ENV_FILE.write_text(text, encoding="utf-8")
    _print("[setup] Created .env from .env.example (generated JWT secret)")


def ensure_directories() -> None:
    created = 0
    for relative in REQUIRED_DIRS:
        path = REPO_ROOT / relative
        if path.is_dir():
            continue
        path.mkdir(parents=True, exist_ok=True)
        created += 1
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if created:
        _print(f"[setup] Created {created} data directories")
    else:
        _print("[skip] Required data directories already exist")


def install_backend(python: Path, *, with_forensic: bool) -> None:
    _print("[setup] Upgrading pip")
    _run([str(python), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"])
    extras = "dev,forensic" if with_forensic else "dev"
    _print(f"[setup] Installing DFAT Python package with extras [{extras}]")
    try:
        _run([str(python), "-m", "pip", "install", "-e", f".[{extras}]"])
    except RuntimeError:
        if extras == "dev":
            raise
        _print(
            "[warn] Forensic extras failed to install — continuing with [dev] only "
            "(parsers may be degraded; ADR-030)."
        )
        _run([str(python), "-m", "pip", "install", "-e", ".[dev]"])


def install_frontend(*, force: bool = False) -> None:
    node_modules = REPO_ROOT / "frontend" / "node_modules"
    if node_modules.is_dir() and not force:
        _print("[skip] frontend/node_modules already present")
        return
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise RuntimeError("npm not found on PATH")
    _print("[setup] Installing frontend npm dependencies")
    # Prefer legacy-peer-deps for CRA/react-scripts stacks used by this repo.
    _run([npm, "install", "--legacy-peer-deps"], cwd=REPO_ROOT / "frontend")


def run_migrations(python: Path) -> None:
    if not ALEMBIC_INI.is_file():
        raise RuntimeError(f"Alembic config missing: {ALEMBIC_INI}")
    env = os.environ.copy()
    src = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src if not existing else f"{src}{os.pathsep}{existing}"
    _print("[setup] Applying database migrations (alembic upgrade head)")
    _run(
        [str(python), "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        env=env,
    )


def mark_setup_complete() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SETUP_MARKER.write_text("ok\n", encoding="utf-8")
    _print(f"[setup] Wrote marker {SETUP_MARKER.relative_to(REPO_ROOT)}")


def is_setup_complete() -> bool:
    return SETUP_MARKER.is_file() and venv_exists() and ENV_FILE.is_file()


def run_setup(*, force: bool = False, with_forensic: bool = True) -> None:
    _print("DFAT environment setup")
    _print("=" * 48)
    if is_setup_complete() and not force:
        _print("[skip] First-run setup already completed (.dfat/setup_complete)")
        _print("       Re-run with --force to reinstall dependencies.")
        return

    python = ensure_venv()
    ensure_env_file()
    ensure_directories()
    install_backend(python, with_forensic=with_forensic)
    install_frontend(force=force)
    run_migrations(python)
    mark_setup_complete()
    _print("=" * 48)
    _print("Environment setup complete.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="DFAT first-run environment setup")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run setup even when the completion marker exists",
    )
    parser.add_argument(
        "--no-forensic",
        action="store_true",
        help="Skip pytsk3/volatility3 extras (useful on constrained hosts)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Exit 0 if setup is complete, 1 otherwise",
    )
    args = parser.parse_args(argv)

    if args.check_only:
        return 0 if is_setup_complete() else 1

    try:
        run_setup(force=args.force, with_forensic=not args.no_forensic)
    except Exception as exc:  # noqa: BLE001 — user-facing launcher errors
        _print(f"[ERROR] Setup failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
