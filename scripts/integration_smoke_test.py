#!/usr/bin/env python3
"""Cross-platform DFAT integration smoke test (mirrors integration_smoke_test.sh)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API_BASE = os.environ.get("DFAT_API_BASE", "http://localhost:8000/api/v1").rstrip("/")
SMOKE_USER = os.environ.get("DFAT_SMOKE_USER", "admin")
SMOKE_PASS = os.environ.get("DFAT_SMOKE_PASSWORD", "Admin!Pass#2026")


def _request(
    method: str,
    path: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> dict | list | str | int | float | bool | None:
    url = f"{API_BASE}{path}"
    req = Request(url, data=data, method=method, headers=headers or {})
    try:
        with urlopen(req, timeout=30) as resp:  # noqa: S310
            body = resp.read().decode("utf-8")
            if not body:
                return None
            return json.loads(body)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} for {method} {url}: {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"Request failed for {method} {url}: {exc}") from exc


def main() -> int:
    print("=== DFAT Integration Smoke Test ===")
    print(f"API: {API_BASE}")

    print("1. Health check...")
    health = _request("GET", "/health")
    assert isinstance(health, dict)
    print(health.get("status"))

    print("2. Login...")
    form = urlencode({"username": SMOKE_USER, "password": SMOKE_PASS}).encode()
    token_payload = _request(
        "POST",
        "/auth/login",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert isinstance(token_payload, dict)
    token = token_payload.get("access_token")
    if not token:
        raise SystemExit("login did not return an access_token (run: make seed-dev)")

    auth = {"Authorization": f"Bearer {token}"}

    print("3. Get profile...")
    me = _request("GET", "/users/me", headers=auth)
    assert isinstance(me, dict)
    print(me.get("username"))

    print("4. Create case...")
    case = _request(
        "POST",
        "/cases",
        data=json.dumps(
            {"case_name": "Smoke Test Case", "description": "Integration test"}
        ).encode(),
        headers={**auth, "Content-Type": "application/json"},
    )
    assert isinstance(case, dict)
    print(f"   case_id={case.get('case_id')}")

    print("5. List cases...")
    cases = _request("GET", "/cases", headers=auth)
    assert isinstance(cases, dict)
    print(cases.get("total"))

    print("6. AI health...")
    ai = _request("GET", "/ai/health")
    assert isinstance(ai, dict)
    print(json.dumps(ai.get("is_healthy")))

    print("7. Frontend build...")
    env = os.environ.copy()
    env.setdefault("NODE_OPTIONS", "--openssl-legacy-provider")
    env["CI"] = "true"
    subprocess.run(
        ["npm", "run", "build"],
        cwd=str(ROOT / "frontend"),
        env=env,
        check=True,
        shell=os.name == "nt",
    )

    print("=== All smoke tests passed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
