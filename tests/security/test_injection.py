"""Injection and payload-hardening tests."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _b64url(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def test_sql_injection_in_search(app_client: TestClient) -> None:
    """Search strings are parameterized; table-dropping payloads do not execute."""
    headers = _auth_header(app_client.investigator_token)  # type: ignore[attr-defined]
    created = app_client.post(
        "/api/v1/cases",
        headers=headers,
        json={"case_name": "Injection Canary", "description": "still here"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    injected = app_client.get(
        "/api/v1/cases",
        headers=headers,
        params={"search": "'; DROP TABLE cases; --"},
    )
    assert injected.status_code == 200
    assert "sql" not in injected.text.lower()
    assert "operationalerror" not in injected.text.lower()

    listed = app_client.get("/api/v1/cases", headers=headers)
    assert listed.status_code == 200
    ids = {item["case_id"] for item in listed.json()["cases"]}
    assert case_id in ids


def test_xss_in_case_name(app_client: TestClient) -> None:
    """Script tags in case names are stored and returned as plain JSON text."""
    xss_name = "<script>alert('xss')</script>"
    headers = _auth_header(app_client.investigator_token)  # type: ignore[attr-defined]
    created = app_client.post(
        "/api/v1/cases",
        headers=headers,
        json={"case_name": xss_name, "description": "xss probe"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["case_name"] == xss_name
    fetched = app_client.get(
        f"/api/v1/cases/{body['case_id']}",
        headers=headers,
    )
    assert fetched.status_code == 200
    assert fetched.json()["case_name"] == xss_name
    assert fetched.headers.get("content-type", "").startswith("application/json")


def test_path_traversal_in_evidence_path(app_client: TestClient) -> None:
    """Directory traversal in evidence paths is rejected by validation."""
    headers = _auth_header(app_client.investigator_token)  # type: ignore[attr-defined]
    response = app_client.post(
        "/api/v1/evidence",
        headers=headers,
        json={
            "file_path": "../../etc/passwd",
            "case_name": "Traversal",
            "investigator": "Investigator",
            "evidence_type": "disk_image",
        },
    )
    assert response.status_code == 422
    register = app_client.post(
        "/api/v1/evidence/register",
        headers=headers,
        json={
            "file_path": "../../etc/passwd",
            "case_id": "case-traversal",
            "evidence_type": "disk_image",
        },
    )
    assert register.status_code == 422


def test_jwt_algorithm_confusion(app_client: TestClient) -> None:
    """Unsigned ``alg=none`` tokens are rejected."""
    now = datetime.now(UTC)
    header = {"alg": "none", "typ": "JWT"}
    payload = {
        "sub": app_client.seeded_db["user_ids"]["admin"],  # type: ignore[attr-defined]
        "username": "admin",
        "role": "admin",
        "type": "access",
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    token = f"{_b64url(header)}.{_b64url(payload)}."
    response = app_client.get(
        "/api/v1/users/me",
        headers=_auth_header(token),
    )
    assert response.status_code == 401


def test_oversized_request_rejected(app_client: TestClient) -> None:
    """Bodies advertised above the 10 MiB limit return HTTP 413."""
    oversize = 10 * 1024 * 1024 + 1
    response = app_client.post(
        "/api/v1/cases",
        content=b"{}",
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(oversize),
            "Authorization": f"Bearer {app_client.investigator_token}",  # type: ignore[attr-defined]
        },
    )
    if response.status_code != 413:
        response = app_client.post(
            "/api/v1/cases",
            content=b"{" + b"x" * oversize + b"}",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {app_client.investigator_token}",  # type: ignore[attr-defined]
            },
        )
    assert response.status_code == 413
