#!/usr/bin/env python3
"""Wait for DFAT backend health, then open the default browser (stdlib only)."""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from typing import Optional


DEFAULT_URL = "http://localhost:3000"
DEFAULT_HEALTH_URL = "http://localhost:8000/api/v1/health"
DEFAULT_TIMEOUT = 60
POLL_INTERVAL = 2


def _print(msg: str) -> None:
    print(msg, flush=True)


def _health_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status == 200
    except urllib.error.HTTPError as exc:
        return exc.code == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Poll backend health and open the DFAT UI in the default browser"
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL to open when ready")
    parser.add_argument(
        "--health-url",
        default=DEFAULT_HEALTH_URL,
        help="Backend health endpoint to poll",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Maximum seconds to wait for backend health",
    )
    args = parser.parse_args(argv)

    max_attempts = max(1, args.timeout // POLL_INTERVAL)
    for attempt in range(1, max_attempts + 1):
        if _health_ok(args.health_url):
            _print("Backend is ready! Opening browser...")
            opened = webbrowser.open(args.url, new=2)
            if not opened:
                _print(f"Could not open browser automatically. Navigate to {args.url}")
            return 0
        _print(f"Waiting for backend... (attempt {attempt}/{max_attempts})")
        time.sleep(POLL_INTERVAL)

    _print(
        f"Backend did not respond within {args.timeout}s. "
        "Please check the backend console for errors. "
        f"You can still try opening {args.url} manually."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
