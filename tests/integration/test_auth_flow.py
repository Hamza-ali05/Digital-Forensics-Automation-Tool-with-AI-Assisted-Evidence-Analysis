"""Integration tests for authentication lifecycle and RBAC."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import (
    TEST_ADMIN_PASSWORD,
    TEST_ADMIN_USERNAME,
    TEST_VIEWER_PASSWORD,
    TEST_VIEWER_USERNAME,
)


def test_full_auth_lifecycle(app_client: TestClient, seeded_db: dict[str, Any]) -> None:
    """Register → login → access → refresh → logout → revoked token fails."""
    # Arrange — admin registers a new analyst.
    admin_headers = {"Authorization": f"Bearer {app_client.admin_token}"}  # type: ignore[attr-defined]
    register = app_client.post(
        "/api/v1/auth/register",
        headers=admin_headers,
        json={
            "username": "lifecycle",
            "email": "lifecycle@example.com",
            "password": "LifeCyclePass1!",
            "full_name": "Lifecycle User",
            "role_name": "analyst",
        },
    )
    assert register.status_code == 201

    # Act — login
    login = app_client.post(
        "/api/v1/auth/login",
        data={"username": "lifecycle", "password": "LifeCyclePass1!"},
    )
    assert login.status_code == 200
    tokens = login.json()
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]

    # Access protected resource
    me = app_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == "lifecycle"

    # Refresh
    refreshed = app_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert refreshed.status_code == 200
    new_access = refreshed.json()["access_token"]

    # Logout
    logout = app_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert logout.status_code == 204

    # Assert — revoked token fails
    revoked = app_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert revoked.status_code in (401, 403)


def test_role_based_access(app_client: TestClient) -> None:
    """Viewer tokens cannot create evidence (403)."""
    # Arrange
    login = app_client.post(
        "/api/v1/auth/login",
        data={"username": TEST_VIEWER_USERNAME, "password": TEST_VIEWER_PASSWORD},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    # Act
    response = app_client.post(
        "/api/v1/evidence",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "file_path": "/tmp/nope.dd",
            "case_name": "Denied",
            "investigator": "Viewer",
            "evidence_type": "disk_image",
        },
    )

    # Assert
    assert response.status_code == 403


def test_account_lockout(app_client: TestClient) -> None:
    """Repeated failed logins lock the account."""
    # Arrange / Act
    statuses = []
    for _ in range(6):
        response = app_client.post(
            "/api/v1/auth/login",
            data={"username": TEST_ADMIN_USERNAME, "password": "WrongPass!!!!"},
        )
        statuses.append(response.status_code)

    # Assert — eventually locked (423) or still invalid (401) then locked
    assert 401 in statuses
    locked = app_client.post(
        "/api/v1/auth/login",
        data={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert locked.status_code in (401, 423)
    # After lockout threshold, even correct password should be rejected as locked.
    assert locked.status_code == 423 or any(
        app_client.post(
            "/api/v1/auth/login",
            data={"username": TEST_ADMIN_USERNAME, "password": "WrongPass!!!!"},
        ).status_code
        == 423
        for _ in range(2)
    )
