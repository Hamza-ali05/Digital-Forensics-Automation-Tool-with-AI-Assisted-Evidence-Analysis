"""Integration tests for evidence management API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import SAMPLE_EVIDENCE_DIR


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _open_case(client: TestClient, headers: dict[str, str], seeded_db: dict[str, Any]) -> str:
    """Create, assign lead, and open a case; return case_id."""
    created = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"case_name": "Evidence API Case", "description": "mgmt"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    assign = client.post(
        f"/api/v1/cases/{case_id}/investigators",
        headers=headers,
        json={"user_id": seeded_db["user_ids"]["investigator"], "role": "lead"},
    )
    assert assign.status_code == 200
    opened = client.post(f"/api/v1/cases/{case_id}/open", headers=headers)
    assert opened.status_code == 200
    return case_id


def test_register_validate_flow(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
) -> None:
    """POST /evidence/register completes register+validate workflow."""
    # Arrange
    headers = _auth_header(app_client.investigator_token)  # type: ignore[attr-defined]
    case_id = _open_case(app_client, headers, seeded_db)
    evidence_path = tmp_path / "reg.dd"
    evidence_path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())

    # Act
    response = app_client.post(
        "/api/v1/evidence/register",
        headers=headers,
        json={
            "file_path": str(evidence_path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": "register flow",
        },
    )

    # Assert
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["validation_passed"] is True
    assert body["evidence_id"]
    assert body["custody_record"] is not None
    assert body["metadata"] is not None


def test_custody_chain_endpoint(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
) -> None:
    """GET /evidence/{id}/custody returns acquisition entry."""
    # Arrange
    headers = _auth_header(app_client.investigator_token)  # type: ignore[attr-defined]
    case_id = _open_case(app_client, headers, seeded_db)
    evidence_path = tmp_path / "custody.dd"
    evidence_path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    registered = app_client.post(
        "/api/v1/evidence/register",
        headers=headers,
        json={
            "file_path": str(evidence_path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": None,
        },
    )
    evidence_id = registered.json()["evidence_id"]

    # Act
    custody = app_client.get(
        f"/api/v1/evidence/{evidence_id}/custody",
        headers=headers,
    )

    # Assert
    assert custody.status_code == 200
    payload = custody.json()
    assert payload["total_entries"] >= 1
    assert payload["entries"][0]["action"] == "acquired"
    assert payload["entries"][0]["entry_number"] == 1


def test_quarantine_endpoint(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
) -> None:
    """POST /evidence/{id}/quarantine marks evidence quarantined."""
    # Arrange
    headers = _auth_header(app_client.investigator_token)  # type: ignore[attr-defined]
    case_id = _open_case(app_client, headers, seeded_db)
    evidence_path = tmp_path / "quar.dd"
    evidence_path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    registered = app_client.post(
        "/api/v1/evidence/register",
        headers=headers,
        json={
            "file_path": str(evidence_path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": None,
        },
    )
    evidence_id = registered.json()["evidence_id"]

    # Act
    quarantined = app_client.post(
        f"/api/v1/evidence/{evidence_id}/quarantine",
        headers=headers,
        json={"reason": "Suspected tampering"},
    )

    # Assert
    assert quarantined.status_code == 200, quarantined.text
    assert quarantined.json()["current_status"] == "quarantined"


def test_integrity_verification_endpoint(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
) -> None:
    """POST /evidence/{id}/verify-integrity confirms hashes and records ACCESS."""
    # Arrange
    headers = _auth_header(app_client.investigator_token)  # type: ignore[attr-defined]
    case_id = _open_case(app_client, headers, seeded_db)
    evidence_path = tmp_path / "verify.dd"
    evidence_path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    registered = app_client.post(
        "/api/v1/evidence/register",
        headers=headers,
        json={
            "file_path": str(evidence_path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": None,
        },
    )
    evidence_id = registered.json()["evidence_id"]

    # Act
    verified = app_client.post(
        f"/api/v1/evidence/{evidence_id}/verify-integrity",
        headers=headers,
    )

    # Assert
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["integrity_verified"] is True
    assert body["custody_record"] is not None
    assert body["custody_record"]["action"] == "accessed"
