"""Authentication enforcement tests for protected API routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from jose import jwt

from tests.conftest import (
    TEST_ADMIN_PASSWORD,
    TEST_ADMIN_USERNAME,
    TEST_JWT_SECRET,
)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_no_token_returns_401_on_protected_endpoints(app_client: TestClient) -> None:
    """Protected routes reject missing credentials with HTTP 401."""
    for path in ("/api/v1/users/me", "/api/v1/cases", "/api/v1/evidence"):
        response = app_client.get(path)
        assert response.status_code == 401, path


def test_expired_token_returns_401(
    app_client: TestClient,
    seeded_db: dict[str, Any],
) -> None:
    """Expired HS256 access tokens are rejected with HTTP 401."""
    now = datetime.now(UTC)
    payload = {
        "sub": seeded_db["user_ids"]["admin"],
        "username": TEST_ADMIN_USERNAME,
        "role": "admin",
        "type": "access",
        "jti": str(uuid4()),
        "iat": int((now - timedelta(hours=2)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    response = app_client.get("/api/v1/users/me", headers=_auth_header(token))
    assert response.status_code == 401


def test_malformed_token_returns_401(app_client: TestClient) -> None:
    """Garbage bearer tokens are rejected with HTTP 401."""
    response = app_client.get(
        "/api/v1/users/me",
        headers=_auth_header("not-a-valid-jwt"),
    )
    assert response.status_code == 401


def test_revoked_token_returns_401(app_client: TestClient) -> None:
    """Logged-out access tokens cannot be reused."""
    login = app_client.post(
        "/api/v1/auth/login",
        data={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    logout = app_client.post("/api/v1/auth/logout", headers=_auth_header(token))
    assert logout.status_code == 204
    response = app_client.get("/api/v1/users/me", headers=_auth_header(token))
    assert response.status_code == 401


def test_token_from_deactivated_user_returns_401(app_client: TestClient) -> None:
    """Tokens belonging to deactivated accounts are rejected with HTTP 401."""
    suffix = uuid4().hex[:8]
    admin = _auth_header(app_client.admin_token)  # type: ignore[attr-defined]
    register = app_client.post(
        "/api/v1/auth/register",
        headers=admin,
        json={
            "username": f"gone{suffix}",
            "email": f"gone{suffix}@example.com",
            "password": "Deactivate12!",
            "full_name": "Soon Disabled",
            "role_name": "analyst",
        },
    )
    assert register.status_code == 201
    user_id = register.json()["id"]
    login = app_client.post(
        "/api/v1/auth/login",
        data={"username": f"gone{suffix}", "password": "Deactivate12!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    deactivated = app_client.put(
        f"/api/v1/users/{user_id}/deactivate",
        headers=admin,
    )
    assert deactivated.status_code == 204
    response = app_client.get("/api/v1/users/me", headers=_auth_header(token))
    assert response.status_code == 401


def test_brute_force_lockout_after_max_attempts(app_client: TestClient) -> None:
    """Accounts lock after the configured number of failed login attempts."""
    suffix = uuid4().hex[:8]
    username = f"lock{suffix}"
    password = "LockoutPass1!"
    admin = _auth_header(app_client.admin_token)  # type: ignore[attr-defined]
    register = app_client.post(
        "/api/v1/auth/register",
        headers=admin,
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "full_name": "Lockout Target",
            "role_name": "analyst",
        },
    )
    assert register.status_code == 201
    for _ in range(5):
        failed = app_client.post(
            "/api/v1/auth/login",
            data={"username": username, "password": "WrongPass!!!!"},
        )
        assert failed.status_code == 401
    locked = app_client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert locked.status_code == 423
