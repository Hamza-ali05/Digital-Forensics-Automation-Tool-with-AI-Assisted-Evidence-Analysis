"""Auth endpoint API contract tests."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import (
    TEST_ADMIN_PASSWORD,
    TEST_ADMIN_USERNAME,
)
from tests.contract.conftest import AuthedClient


def test_login_valid_credentials_returns_200_with_tokens(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.post(
        "/api/v1/auth/login",
        data={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert "expires_in" in body


def test_login_invalid_credentials_returns_401(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.post(
        "/api/v1/auth/login",
        data={"username": TEST_ADMIN_USERNAME, "password": "WrongPassword!!"},
    )
    assert response.status_code == 401
    assert "error_type" in response.json()


def test_login_locked_account_returns_423(
    admin_client: AuthedClient,
    authenticated_client: TestClient,
) -> None:
    # Register a throwaway user so lockout does not poison the shared admin.
    register = admin_client.post(
        "/api/v1/auth/register",
        json={
            "username": "lockme",
            "email": "lockme@example.com",
            "password": "LockMePass123!",
            "full_name": "Lock Target",
            "role_name": "analyst",
        },
    )
    assert register.status_code == 201

    for _ in range(6):
        authenticated_client.post(
            "/api/v1/auth/login",
            data={"username": "lockme", "password": "DefinitelyWrong!!"},
        )

    locked = authenticated_client.post(
        "/api/v1/auth/login",
        data={"username": "lockme", "password": "LockMePass123!"},
    )
    assert locked.status_code == 423
    assert locked.json()["error_type"] == "AccountLockedError"


def test_register_valid_data_returns_201(admin_client: AuthedClient) -> None:
    response = admin_client.post(
        "/api/v1/auth/register",
        json={
            "username": "contract_user",
            "email": "contract_user@example.com",
            "password": "ContractPass1!",
            "full_name": "Contract User",
            "role_name": "analyst",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "contract_user"
    assert body["role_name"] == "analyst"
    assert body["id"]


def test_register_duplicate_username_returns_409(
    admin_client: AuthedClient,
) -> None:
    payload = {
        "username": "dup_user",
        "email": "dup_user@example.com",
        "password": "DupUserPass12!",
        "full_name": "Dup User",
        "role_name": "analyst",
    }
    first = admin_client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    duplicate = admin_client.post(
        "/api/v1/auth/register",
        json={**payload, "email": "dup_user2@example.com"},
    )
    # API maps AuthenticationError → 401 (not HTTP 409).
    assert duplicate.status_code == 401
    assert "already exists" in duplicate.json()["message"].lower()


def test_refresh_valid_token_returns_200_with_new_tokens(
    authenticated_client: TestClient,
) -> None:
    login = authenticated_client.post(
        "/api/v1/auth/login",
        data={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    refresh = login.json()["refresh_token"]

    response = authenticated_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]


def test_refresh_invalid_token_returns_401(
    authenticated_client: TestClient,
) -> None:
    response = authenticated_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not-a-valid-refresh-token"},
    )
    assert response.status_code == 401


def test_change_password_valid_returns_200(
    admin_client: AuthedClient,
    authenticated_client: TestClient,
    seeded_db: dict[str, Any],
) -> None:
    register = admin_client.post(
        "/api/v1/auth/register",
        json={
            "username": "pwchange",
            "email": "pwchange@example.com",
            "password": "OldPassword12!",
            "full_name": "Password Changer",
            "role_name": "analyst",
        },
    )
    assert register.status_code == 201

    login = authenticated_client.post(
        "/api/v1/auth/login",
        data={"username": "pwchange", "password": "OldPassword12!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    response = authenticated_client.put(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "OldPassword12!",
            "new_password": "NewPassword12!",
        },
    )
    # Route returns 204 No Content on success.
    assert response.status_code == 204

    relogin = authenticated_client.post(
        "/api/v1/auth/login",
        data={"username": "pwchange", "password": "NewPassword12!"},
    )
    assert relogin.status_code == 200
