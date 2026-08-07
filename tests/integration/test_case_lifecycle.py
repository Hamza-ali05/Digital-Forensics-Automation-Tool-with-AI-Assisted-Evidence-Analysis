"""Integration tests for case lifecycle API flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import (
    SAMPLE_EVIDENCE_DIR,
    TEST_INVESTIGATOR_PASSWORD,
    TEST_INVESTIGATOR_USERNAME,
    TEST_VIEWER_PASSWORD,
    TEST_VIEWER_USERNAME,
)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_full_case_lifecycle(app_client: TestClient, seeded_db: dict[str, Any]) -> None:
    """CREATED → OPEN → ACTIVE → UNDER_REVIEW → CLOSED → ARCHIVED via API."""
    # Arrange
    inv_headers = _auth_header(app_client.investigator_token)  # type: ignore[attr-defined]
    inv_id = seeded_db["user_ids"]["investigator"]

    # Act
    created = app_client.post(
        "/api/v1/cases",
        headers=inv_headers,
        json={"case_name": "Lifecycle Case", "description": "integration"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    assign = app_client.post(
        f"/api/v1/cases/{case_id}/investigators",
        headers=inv_headers,
        json={"user_id": inv_id, "role": "lead"},
    )
    assert assign.status_code == 200

    opened = app_client.post(f"/api/v1/cases/{case_id}/open", headers=inv_headers)
    assert opened.status_code == 200
    assert opened.json()["status"] == "open"

    active = app_client.post(f"/api/v1/cases/{case_id}/activate", headers=inv_headers)
    assert active.json()["status"] == "active"

    review = app_client.post(
        f"/api/v1/cases/{case_id}/submit-review",
        headers=inv_headers,
    )
    assert review.json()["status"] == "under_review"

    closed = app_client.post(
        f"/api/v1/cases/{case_id}/close",
        headers=inv_headers,
        json={"reason": "Investigation complete"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    archived = app_client.post(f"/api/v1/cases/{case_id}/archive", headers=inv_headers)

    # Assert
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_role_based_case_access(app_client: TestClient) -> None:
    """Investigator can create cases; viewer cannot."""
    # Arrange
    inv_login = app_client.post(
        "/api/v1/auth/login",
        data={
            "username": TEST_INVESTIGATOR_USERNAME,
            "password": TEST_INVESTIGATOR_PASSWORD,
        },
    )
    view_login = app_client.post(
        "/api/v1/auth/login",
        data={"username": TEST_VIEWER_USERNAME, "password": TEST_VIEWER_PASSWORD},
    )
    assert inv_login.status_code == 200
    assert view_login.status_code == 200
    inv_headers = _auth_header(inv_login.json()["access_token"])
    view_headers = _auth_header(view_login.json()["access_token"])

    # Act
    allowed = app_client.post(
        "/api/v1/cases",
        headers=inv_headers,
        json={"case_name": "Allowed", "description": None},
    )
    denied = app_client.post(
        "/api/v1/cases",
        headers=view_headers,
        json={"case_name": "Denied", "description": None},
    )

    # Assert
    assert allowed.status_code == 201
    assert denied.status_code == 403


def test_evidence_inventory_for_case(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
) -> None:
    """Registering evidence into an open case appears in inventory."""
    # Arrange
    inv_headers = _auth_header(app_client.investigator_token)  # type: ignore[attr-defined]
    inv_id = seeded_db["user_ids"]["investigator"]
    created = app_client.post(
        "/api/v1/cases",
        headers=inv_headers,
        json={"case_name": "Inventory Case", "description": "inv"},
    )
    case_id = created.json()["case_id"]
    app_client.post(
        f"/api/v1/cases/{case_id}/investigators",
        headers=inv_headers,
        json={"user_id": inv_id, "role": "lead"},
    )
    app_client.post(f"/api/v1/cases/{case_id}/open", headers=inv_headers)

    source = SAMPLE_EVIDENCE_DIR / "test_disk.dd"
    evidence_path = tmp_path / "inventory.dd"
    evidence_path.write_bytes(source.read_bytes())

    # Act
    registered = app_client.post(
        "/api/v1/evidence/register",
        headers=inv_headers,
        json={
            "file_path": str(evidence_path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": "inventory item",
        },
    )
    inventory = app_client.get(
        "/api/v1/evidence/inventory",
        headers=inv_headers,
        params={"case_id": case_id},
    )

    # Assert
    assert registered.status_code == 201, registered.text
    assert registered.json()["validation_passed"] is True
    assert inventory.status_code == 200
    assert inventory.json()["total"] >= 1
    assert any(
        item["evidence_id"] == registered.json()["evidence_id"]
        for item in inventory.json()["items"]
    )
