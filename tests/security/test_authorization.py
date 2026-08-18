"""Authorisation and privilege-escalation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from jose import jwt

from tests.conftest import TEST_JWT_SECRET

_PUBLIC_WRITE = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/evaluation/usability/respond"),
}

_AUTH_DEPENDENCY_NAMES = {
    "get_current_user",
    "get_current_active_user",
}


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_investigator(app_client: TestClient, *, suffix: str) -> str:
    """Register a second investigator and return a live access token."""
    username = f"inv{suffix}"
    password = "SecondInvest1!"
    register = app_client.post(
        "/api/v1/auth/register",
        headers=_auth_header(app_client.admin_token),  # type: ignore[attr-defined]
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "full_name": "Second Investigator",
            "role_name": "investigator",
        },
    )
    assert register.status_code == 201
    login = app_client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def _dependency_names(dependant: Any) -> set[str]:
    names: set[str] = set()
    call = getattr(dependant, "call", None)
    if call is not None:
        names.add(getattr(call, "__name__", ""))
    for child in getattr(dependant, "dependencies", []) or []:
        names.update(_dependency_names(child))
    return names


def test_viewer_cannot_create_case(app_client: TestClient) -> None:
    """Viewers are denied case creation (403)."""
    response = app_client.post(
        "/api/v1/cases",
        headers=_auth_header(app_client.viewer_token),  # type: ignore[attr-defined]
        json={"case_name": "Viewer Case", "description": "denied"},
    )
    assert response.status_code == 403


def test_analyst_cannot_delete_evidence(app_client: TestClient) -> None:
    """Analysts lack evidence delete permission (403)."""
    response = app_client.delete(
        f"/api/v1/evidence/{uuid4()}",
        headers=_auth_header(app_client.analyst_token),  # type: ignore[attr-defined]
    )
    assert response.status_code == 403


def test_viewer_cannot_access_admin_endpoints(app_client: TestClient) -> None:
    """Viewers cannot reach admin-only routes (403)."""
    headers = _auth_header(app_client.viewer_token)  # type: ignore[attr-defined]
    for path in ("/api/v1/users", "/api/v1/health/detailed"):
        response = app_client.get(path, headers=headers)
        assert response.status_code == 403, path


def test_investigator_cannot_manage_users(app_client: TestClient) -> None:
    """Investigators cannot list or deactivate users (403)."""
    headers = _auth_header(app_client.investigator_token)  # type: ignore[attr-defined]
    listed = app_client.get("/api/v1/users", headers=headers)
    assert listed.status_code == 403
    deactivated = app_client.put(
        f"/api/v1/users/{uuid4()}/deactivate",
        headers=headers,
    )
    assert deactivated.status_code == 403


def test_user_cannot_access_other_users_cases(app_client: TestClient) -> None:
    """Case listing is scoped to the requester's own cases."""
    created = app_client.post(
        "/api/v1/cases",
        headers=_auth_header(app_client.investigator_token),  # type: ignore[attr-defined]
        json={"case_name": "Private Isolation Case", "description": "owner only"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    other_token = _register_investigator(app_client, suffix=uuid4().hex[:8])
    listed = app_client.get("/api/v1/cases", headers=_auth_header(other_token))
    assert listed.status_code == 200
    ids = {item["case_id"] for item in listed.json()["cases"]}
    assert case_id not in ids
    detail = app_client.get(
        f"/api/v1/cases/{case_id}",
        headers=_auth_header(other_token),
    )
    assert detail.status_code == 403


def test_role_escalation_prevented(app_client: TestClient) -> None:
    """Investigators cannot register themselves as admin or spoof the role claim."""
    register = app_client.post(
        "/api/v1/auth/register",
        headers=_auth_header(app_client.investigator_token),  # type: ignore[attr-defined]
        json={
            "username": f"esc{uuid4().hex[:8]}",
            "email": f"esc{uuid4().hex[:8]}@example.com",
            "password": "EscalatePass1!",
            "full_name": "Escalation Attempt",
            "role_name": "admin",
        },
    )
    assert register.status_code == 403

    now = datetime.now(UTC)
    spoofed = jwt.encode(
        {
            "sub": app_client.seeded_db["user_ids"]["investigator"],  # type: ignore[attr-defined]
            "username": "investigator",
            "role": "admin",
            "type": "access",
            "jti": str(uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    response = app_client.get("/api/v1/users", headers=_auth_header(spoofed))
    assert response.status_code == 403


def test_horizontal_privilege_escalation_prevented(app_client: TestClient) -> None:
    """An investigator cannot mutate or read another investigator's case."""
    created = app_client.post(
        "/api/v1/cases",
        headers=_auth_header(app_client.investigator_token),  # type: ignore[attr-defined]
        json={"case_name": "Owner Case", "description": "horizontal"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    other_token = _register_investigator(app_client, suffix=uuid4().hex[:8])
    other = _auth_header(other_token)
    assert app_client.get(f"/api/v1/cases/{case_id}", headers=other).status_code == 403
    assert app_client.post(
        f"/api/v1/cases/{case_id}/open",
        headers=other,
    ).status_code == 403
    assert app_client.get(
        f"/api/v1/cases/{case_id}/summary",
        headers=other,
    ).status_code == 403


def test_permission_check_on_every_write_endpoint(app_client: TestClient) -> None:
    """Mutating API routes authenticate the caller (except documented public writes)."""
    missing: list[str] = []
    for route in app_client.app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = {method.upper() for method in (route.methods or set())}
        write_methods = methods & {"POST", "PUT", "PATCH", "DELETE"}
        if not write_methods:
            continue
        path = route.path
        if not path.startswith("/api/"):
            continue
        names = _dependency_names(route.dependant)
        for method in sorted(write_methods):
            if (method, path) in _PUBLIC_WRITE:
                continue
            if names.isdisjoint(_AUTH_DEPENDENCY_NAMES):
                missing.append(f"{method} {path}")
    assert missing == [], f"Write endpoints missing auth: {missing}"

    viewer = _auth_header(app_client.viewer_token)  # type: ignore[attr-defined]
    for path, body in (
        ("/api/v1/cases", {"case_name": "Nope", "description": "viewer"}),
        (
            "/api/v1/evidence",
            {
                "file_path": "/tmp/x.dd",
                "case_name": "Nope",
                "investigator": "Viewer",
                "evidence_type": "disk_image",
            },
        ),
        (
            "/api/v1/pipeline/run",
            {"evidence_id": "e1", "case_id": "c1", "mode": "full"},
        ),
    ):
        response = app_client.post(path, headers=viewer, json=body)
        assert response.status_code == 403, path
