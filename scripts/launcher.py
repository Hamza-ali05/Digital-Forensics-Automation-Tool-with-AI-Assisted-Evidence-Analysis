#!/usr/bin/env python3
"""Cross-platform DFAT one-click launcher.

Orchestrates prerequisite checks, first-run setup, backend/frontend process
management, optional Ollama detection, and browser open. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
STATE_DIR = REPO_ROOT / ".dfat"
BACKEND_PID = STATE_DIR / "backend.pid"
FRONTEND_PID = STATE_DIR / "frontend.pid"
BACKEND_LOG = STATE_DIR / "backend.log"
FRONTEND_LOG = STATE_DIR / "frontend.log"
LAUNCHER_META = STATE_DIR / "launcher.json"

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_PORT = 3000
HEALTH_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/v1/health"
FRONTEND_URL = f"http://{BACKEND_HOST}:{FRONTEND_PORT}"
OLLAMA_URL = "http://127.0.0.1:11434/api/tags"


def _print(msg: str) -> None:
    print(msg, flush=True)


def _banner() -> None:
    _print("")
    _print("=" * 64)
    _print("  DFAT — Digital Forensics Automation Tool")
    _print("  One-click local development launcher")
    _print("=" * 64)
    _print("")


def venv_python() -> Path:
    if platform.system() == "Windows":
        return REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    return REPO_ROOT / ".venv" / "bin" / "python"


def resolve_python() -> Path:
    candidate = venv_python()
    if candidate.is_file():
        return candidate
    return Path(sys.executable)


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def check_ports(*, allow_occupied: bool = False) -> None:
    conflicts = []
    for port, label in ((BACKEND_PORT, "backend"), (FRONTEND_PORT, "frontend")):
        if port_in_use(BACKEND_HOST, port):
            conflicts.append(f"port {port} ({label})")
    if conflicts and not allow_occupied:
        raise RuntimeError(
            "Port conflict: "
            + ", ".join(conflicts)
            + " already in use. Stop the other process or run stop.bat / ./stop.sh first."
        )


def probe_ollama() -> None:
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=2) as response:
            if 200 <= int(response.status) < 300:
                _print("[info] Ollama is reachable at http://127.0.0.1:11434")
                return
    except (urllib.error.URLError, TimeoutError, OSError):
        pass
    _print(
        "[info] Ollama not detected — AI triage will use rule-based fallback "
        "(ADR-030). Install from https://ollama.com/ if desired."
    )


def run_python_script(script: Path, *args: str, python: Optional[Path] = None) -> int:
    exe = str(python or Path(sys.executable))
    cmd = [exe, str(script), *args]
    _print(f"  > {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)
    return int(completed.returncode)


def _write_pid(path: Path, pid: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid), encoding="utf-8")


def _read_pid(path: Path) -> Optional[int]:
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        # tasklist is available on all supported Windows versions.
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return str(pid) in (completed.stdout or "")
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _kill_pid(pid: int) -> None:
    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.3)
    if _pid_alive(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def stop_services() -> None:
    _print("Stopping DFAT services…")
    for label, path in (("backend", BACKEND_PID), ("frontend", FRONTEND_PID)):
        pid = _read_pid(path)
        if pid is None:
            _print(f"[skip] No {label} PID file")
            continue
        if not _pid_alive(pid):
            _print(f"[skip] {label} PID {pid} is not running")
            path.unlink(missing_ok=True)
            continue
        _print(f"[stop] Sending shutdown to {label} (PID {pid})")
        _kill_pid(pid)
        path.unlink(missing_ok=True)
    if LAUNCHER_META.is_file():
        LAUNCHER_META.unlink(missing_ok=True)
    _print("Shutdown complete.")


def _spawn(
    cmd: list[str],
    *,
    log_path: Path,
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> subprocess.Popen[bytes]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("ab")
    kwargs: dict = {
        "cwd": str(cwd),
        "env": env,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }
    if platform.system() == "Windows":
        # New process group so stop.bat can taskkill the tree cleanly.
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True

    process = subprocess.Popen(cmd, **kwargs)
    try:
        log_handle.close()
    except OSError:
        pass
    return process


def start_backend(python: Path) -> int:
    if port_in_use(BACKEND_HOST, BACKEND_PORT):
        existing = _read_pid(BACKEND_PID)
        if existing and _pid_alive(existing):
            _print(f"[skip] Backend already running (PID {existing})")
            return existing
        raise RuntimeError(
            f"Port {BACKEND_PORT} is in use by another process. "
            "Run stop.bat / ./stop.sh or free the port."
        )

    env = os.environ.copy()
    src = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src if not existing else f"{src}{os.pathsep}{existing}"
    env.setdefault("DFAT_ENV", "development")

    cmd = [
        str(python),
        "-m",
        "uvicorn",
        "dfat.app:create_app",
        "--factory",
        "--host",
        BACKEND_HOST,
        "--port",
        str(BACKEND_PORT),
        "--reload",
    ]
    _print(f"[start] Backend → http://{BACKEND_HOST}:{BACKEND_PORT}")
    _print(f"        Log: {BACKEND_LOG.relative_to(REPO_ROOT)}")
    process = _spawn(cmd, log_path=BACKEND_LOG, cwd=REPO_ROOT, env=env)
    _write_pid(BACKEND_PID, process.pid)
    return process.pid


def start_frontend() -> int:
    if port_in_use(BACKEND_HOST, FRONTEND_PORT):
        existing = _read_pid(FRONTEND_PID)
        if existing and _pid_alive(existing):
            _print(f"[skip] Frontend already running (PID {existing})")
            return existing
        raise RuntimeError(
            f"Port {FRONTEND_PORT} is in use by another process. "
            "Run stop.bat / ./stop.sh or free the port."
        )

    import shutil

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise RuntimeError("npm not found on PATH")

    env = os.environ.copy()
    env["BROWSER"] = "none"
    env.setdefault("PORT", str(FRONTEND_PORT))
    env.setdefault("HOST", "127.0.0.1")

    cmd = [npm, "start"]
    _print(f"[start] Frontend → {FRONTEND_URL}")
    _print(f"        Log: {FRONTEND_LOG.relative_to(REPO_ROOT)}")
    process = _spawn(cmd, log_path=FRONTEND_LOG, cwd=REPO_ROOT / "frontend", env=env)
    _write_pid(FRONTEND_PID, process.pid)
    return process.pid


def wait_backend(timeout: float = 120.0) -> bool:
    from open_browser import wait_for_http

    _print(f"[wait] {HEALTH_URL}")
    return wait_for_http(HEALTH_URL, timeout=timeout)


def maybe_seed(python: Path) -> None:
    seed_marker = STATE_DIR / "seed_complete"
    if seed_marker.is_file():
        _print("[skip] Dev seed already completed")
        return
    seed_script = SCRIPTS / "seed_dev_data.py"
    if not seed_script.is_file():
        _print("[skip] seed_dev_data.py not found")
        return
    _print("[setup] Seeding development users/cases via API")
    code = run_python_script(seed_script, python=python)
    if code == 0:
        seed_marker.write_text("ok\n", encoding="utf-8")
        _print("[setup] Seed complete")
    else:
        _print(
            "[warn] Seed script failed — you can still log in with the "
            "first-run admin credentials printed by the backend, or re-run "
            "scripts/seed_dev_data.py later."
        )


def write_meta(backend_pid: int, frontend_pid: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "backend_pid": backend_pid,
        "frontend_pid": frontend_pid,
        "backend_url": f"http://{BACKEND_HOST}:{BACKEND_PORT}",
        "frontend_url": FRONTEND_URL,
        "health_url": HEALTH_URL,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    LAUNCHER_META.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def cmd_start(*, skip_browser: bool, no_seed: bool, force_setup: bool) -> int:
    _banner()
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Prerequisites use the invoking interpreter (before venv may exist).
    if run_python_script(SCRIPTS / "check_prerequisites.py") != 0:
        return 1

    setup_args = ["--force"] if force_setup else []
    if run_python_script(SCRIPTS / "setup_environment.py", *setup_args) != 0:
        return 1

    python = resolve_python()
    _print(f"[info] Using Python: {python}")

    try:
        check_ports()
    except RuntimeError as exc:
        # If our own previous launch left services running, treat as success path.
        backend_pid = _read_pid(BACKEND_PID)
        frontend_pid = _read_pid(FRONTEND_PID)
        if (
            backend_pid
            and frontend_pid
            and _pid_alive(backend_pid)
            and _pid_alive(frontend_pid)
            and port_in_use(BACKEND_HOST, BACKEND_PORT)
            and port_in_use(BACKEND_HOST, FRONTEND_PORT)
        ):
            _print("[info] DFAT appears to already be running.")
            _print(f"       Frontend: {FRONTEND_URL}")
            _print(f"       API docs: http://{BACKEND_HOST}:{BACKEND_PORT}/docs")
            if not skip_browser:
                run_python_script(
                    SCRIPTS / "open_browser.py",
                    "--timeout",
                    "30",
                    python=python,
                )
            return 0
        _print(f"[ERROR] {exc}")
        return 1

    probe_ollama()

    try:
        backend_pid = start_backend(python)
    except Exception as exc:  # noqa: BLE001
        _print(f"[ERROR] Failed to start backend: {exc}")
        return 1

    if not wait_backend():
        _print(
            f"[ERROR] Backend did not become healthy. See {BACKEND_LOG.relative_to(REPO_ROOT)}"
        )
        return 1
    _print("[ok] Backend healthy")

    if not no_seed:
        maybe_seed(python)

    try:
        frontend_pid = start_frontend()
    except Exception as exc:  # noqa: BLE001
        _print(f"[ERROR] Failed to start frontend: {exc}")
        return 1

    write_meta(backend_pid, frontend_pid)

    if skip_browser:
        _print("[info] Skipping browser open (--no-browser)")
    else:
        code = run_python_script(
            SCRIPTS / "open_browser.py",
            "--timeout",
            "180",
            python=python,
        )
        if code != 0:
            _print(
                f"[warn] Browser helper timed out. Open {FRONTEND_URL} manually once "
                "the frontend finishes compiling."
            )

    _print("")
    _print("DFAT is starting.")
    _print(f"  UI:      {FRONTEND_URL}")
    _print(f"  API:     http://{BACKEND_HOST}:{BACKEND_PORT}/api/v1")
    _print(f"  Docs:    http://{BACKEND_HOST}:{BACKEND_PORT}/docs")
    _print(f"  Stop:    stop.bat  (Windows)  or  ./stop.sh  (macOS/Linux)")
    _print("")
    return 0


def cmd_status() -> int:
    backend_pid = _read_pid(BACKEND_PID)
    frontend_pid = _read_pid(FRONTEND_PID)
    _print("DFAT launcher status")
    _print("=" * 48)
    for label, pid, port in (
        ("backend", backend_pid, BACKEND_PORT),
        ("frontend", frontend_pid, FRONTEND_PORT),
    ):
        alive = bool(pid and _pid_alive(pid))
        listening = port_in_use(BACKEND_HOST, port)
        _print(
            f"  {label:8} pid={pid or '-'} "
            f"alive={'yes' if alive else 'no'} "
            f"port_{port}={'open' if listening else 'closed'}"
        )
    if LAUNCHER_META.is_file():
        _print(f"  meta: {LAUNCHER_META.relative_to(REPO_ROOT)}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    # Allow `from open_browser import …` when executed as a script.
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))

    parser = argparse.ArgumentParser(description="DFAT one-click launcher")
    parser.add_argument(
        "command",
        nargs="?",
        default="start",
        choices=("start", "stop", "status"),
        help="Action to perform (default: start)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the default browser",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip development data seeding",
    )
    parser.add_argument(
        "--force-setup",
        action="store_true",
        help="Force environment setup even if already completed",
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "stop":
            stop_services()
            return 0
        if args.command == "status":
            return cmd_status()
        return cmd_start(
            skip_browser=args.no_browser,
            no_seed=args.no_seed,
            force_setup=args.force_setup,
        )
    except KeyboardInterrupt:
        _print("\nInterrupted.")
        return 130
    except Exception as exc:  # noqa: BLE001
        _print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
