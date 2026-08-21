#!/usr/bin/env python3
"""Seed development users and sample cases via the DFAT HTTP API.

Requires a running API (``make dev-backend``). The first admin account is
bootstrapped through ``UserService.register_user`` (same code path as
``POST /api/v1/auth/register``) because registration itself requires an
existing admin. All subsequent users and cases are created over HTTP.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Optional

import httpx

API_BASE = os.environ.get("DFAT_API_BASE", "http://localhost:8000/api/v1").rstrip("/")

USERS = (
    {
        "username": "admin",
        "password": "Admin!Pass#2026",
        "email": "admin@example.com",
        "full_name": "DFAT Administrator",
        "role_name": "admin",
    },
    {
        "username": "investigator1",
        "password": "Invest!Pass#2026",
        "email": "investigator1@example.com",
        "full_name": "Lead Investigator",
        "role_name": "investigator",
    },
    {
        "username": "analyst1",
        "password": "Analyst!Pass#2026",
        "email": "analyst1@example.com",
        "full_name": "Forensic Analyst",
        "role_name": "analyst",
    },
    {
        "username": "viewer1",
        "password": "Viewer!Pass#2026",
        "email": "viewer1@example.com",
        "full_name": "Read-Only Viewer",
        "role_name": "viewer",
    },
)

CASES = (
    {
        "case_name": "Dev Sample",
        "description": "Seeded OPEN case for local development",
        "target_status": "open",
    },
    {
        "case_name": "Dev Sample Lab",
        "description": "Seeded ACTIVE case for local development",
        "target_status": "active",
    },
)


class SeedError(RuntimeError):
    """Raised when seeding cannot complete."""


def _print(msg: str) -> None:
    print(msg, flush=True)


async def _login(
    client: httpx.AsyncClient, username: str, password: str
) -> Optional[str]:
    response = await client.post(
        f"{API_BASE}/auth/login",
        data={"username": username, "password": password},
    )
    if response.status_code != 200:
        return None
    token = response.json().get("access_token")
    return str(token) if token else None


async def _bootstrap_admin(user: dict[str, str]) -> None:
    """Create the first admin via UserService when login is impossible."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    src = os.path.join(root, "src")
    if src not in sys.path:
        sys.path.insert(0, src)

    from dfat.auth.exceptions import AuthenticationError, RoleNotFoundError
    from dfat.auth.schemas import RegisterRequest
    from dfat.container import build_application_container

    container = build_application_container()
    settings = container.settings()
    db_engine = container.database.database_engine()
    if settings.database.create_tables_on_startup:
        import dfat.database  # noqa: F401

        await db_engine.create_tables()

    user_service = container.services.user_service()
    try:
        await user_service.register_user(
            RegisterRequest(
                username=user["username"],
                email=user["email"],
                password=user["password"],
                full_name=user["full_name"],
                role_name=user["role_name"],
            ),
            registered_by=None,
        )
        _print(f"  Bootstrapped admin user '{user['username']}' via UserService")
    except (AuthenticationError, RoleNotFoundError) as exc:
        _print(f"  Admin bootstrap skipped ({exc})")
    finally:
        await db_engine.dispose()


async def _ensure_user(
    client: httpx.AsyncClient,
    admin_token: str,
    user: dict[str, str],
) -> None:
    token = await _login(client, user["username"], user["password"])
    if token:
        _print(f"  User exists: {user['username']} ({user['role_name']})")
        return

    response = await client.post(
        f"{API_BASE}/auth/register",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": user["username"],
            "email": user["email"],
            "password": user["password"],
            "full_name": user["full_name"],
            "role_name": user["role_name"],
        },
    )
    if response.status_code in (200, 201):
        _print(f"  Registered: {user['username']} ({user['role_name']})")
        return
    token = await _login(client, user["username"], user["password"])
    if token:
        _print(f"  User exists after register attempt: {user['username']}")
        return
    raise SeedError(
        f"Failed to register {user['username']}: "
        f"{response.status_code} {response.text}"
    )


async def _find_case_id(
    client: httpx.AsyncClient,
    token: str,
    case_name: str,
) -> Optional[str]:
    response = await client.get(
        f"{API_BASE}/cases",
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    payload = response.json()
    cases = payload.get("cases") or []
    for item in cases:
        if item.get("case_name") == case_name:
            return str(item.get("case_id"))
    return None


async def _ensure_case(
    client: httpx.AsyncClient,
    token: str,
    spec: dict[str, str],
) -> str:
    existing = await _find_case_id(client, token, spec["case_name"])
    if existing:
        _print(f"  Case exists: {spec['case_name']} ({existing})")
        case_id = existing
    else:
        response = await client.post(
            f"{API_BASE}/cases",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "case_name": spec["case_name"],
                "description": spec["description"],
            },
        )
        if response.status_code not in (200, 201):
            raise SeedError(
                f"Failed to create case {spec['case_name']}: "
                f"{response.status_code} {response.text}"
            )
        case_id = str(response.json()["case_id"])
        _print(f"  Created case: {spec['case_name']} ({case_id})")

    target = spec["target_status"]
    headers = {"Authorization": f"Bearer {token}"}
    if target in ("open", "active"):
        opened = await client.post(f"{API_BASE}/cases/{case_id}/open", headers=headers)
        if opened.status_code >= 500:
            raise SeedError(f"open failed: {opened.status_code} {opened.text}")
    if target == "active":
        activated = await client.post(
            f"{API_BASE}/cases/{case_id}/activate", headers=headers
        )
        if activated.status_code >= 500:
            raise SeedError(
                f"activate failed: {activated.status_code} {activated.text}"
            )
    _print(f"  Case status target '{target}' applied for {case_id}")
    return case_id


async def main() -> int:
    _print("=== DFAT Dev Data Seed ===")
    _print(f"API: {API_BASE}")

    admin = USERS[0]
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            health = await client.get(f"{API_BASE}/health")
            health.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            _print(
                "ERROR: API is not reachable. Start it with `make dev-backend` "
                f"first.\n  ({exc})"
            )
            return 1

        token = await _login(client, admin["username"], admin["password"])
        if not token:
            _print("Admin login failed — bootstrapping first admin…")
            await _bootstrap_admin(admin)
            token = await _login(client, admin["username"], admin["password"])
        if not token:
            raise SeedError("Unable to obtain admin access token after bootstrap")

        _print("Seeding users…")
        for user in USERS[1:]:
            await _ensure_user(client, token, user)
        _print(f"  User ready: {admin['username']} (admin)")

        _print("Seeding cases…")
        for spec in CASES:
            await _ensure_case(client, token, spec)

    _print("=== Seed complete ===")
    _print("Logins:")
    for user in USERS:
        _print(f"  {user['username']} / {user['password']} ({user['role_name']})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except SeedError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        raise SystemExit(1) from err
