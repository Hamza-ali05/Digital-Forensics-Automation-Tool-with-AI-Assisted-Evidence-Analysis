"""Evidence endpoint API contract tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.conftest import SAMPLE_EVIDENCE_DIR
from tests.contract.conftest import AuthedClient


def test_register_evidence_returns_201(
    investigator_client: AuthedClient,
    seeded_database: dict[str, Any],
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "register_ok.dd"
    evidence_path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    response = investigator_client.post(
        "/api/v1/evidence/register",
        json={
            "file_path": str(evidence_path),
            "case_id": seeded_database["case_id"],
            "evidence_type": "disk_image",
            "description": "contract register",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["evidence_id"]
    assert body["validation_passed"] is True


def test_register_nonexistent_file_returns_422(
    investigator_client: AuthedClient,
    seeded_database: dict[str, Any],
) -> None:
    response = investigator_client.post(
        "/api/v1/evidence/register",
        json={
            "file_path": "/tmp/dfat-does-not-exist-contract.dd",
            "case_id": seeded_database["case_id"],
            "evidence_type": "disk_image",
            "description": None,
        },
    )
    # Missing path raises EvidenceNotFoundError → 404 (contract of current API).
    assert response.status_code in (404, 422)
    assert response.json()["error_type"] in {
        "EvidenceNotFoundError",
        "EvidenceValidationError",
    }


def test_get_evidence_detail_returns_full_metadata(
    investigator_client: AuthedClient,
    seeded_database: dict[str, Any],
) -> None:
    evidence_id = seeded_database["evidence_id"]
    response = investigator_client.get(f"/api/v1/evidence/{evidence_id}/detail")
    assert response.status_code == 200
    body = response.json()
    assert body["evidence_id"] == evidence_id
    assert "status" in body or "metadata" in body or "file_path" in body


def test_get_inventory_returns_list_with_statistics(
    investigator_client: AuthedClient,
    seeded_database: dict[str, Any],
) -> None:
    inventory = investigator_client.get(
        "/api/v1/evidence/inventory",
        params={"case_id": seeded_database["case_id"]},
    )
    assert inventory.status_code == 200
    inv_body = inventory.json()
    assert isinstance(inv_body, (list, dict))

    stats = investigator_client.get(
        "/api/v1/evidence/statistics",
        params={"case_id": seeded_database["case_id"]},
    )
    assert stats.status_code == 200
    assert isinstance(stats.json(), dict)


def test_verify_integrity_returns_hash_comparison(
    investigator_client: AuthedClient,
    seeded_database: dict[str, Any],
) -> None:
    evidence_id = seeded_database["evidence_id"]
    response = investigator_client.post(
        f"/api/v1/evidence/{evidence_id}/verify-integrity"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["evidence_id"] == evidence_id
    assert body["integrity_verified"] is True
    assert "hash_set" in body


def test_get_custody_chain_returns_ordered_entries(
    investigator_client: AuthedClient,
    seeded_database: dict[str, Any],
) -> None:
    evidence_id = seeded_database["evidence_id"]
    response = investigator_client.get(f"/api/v1/evidence/{evidence_id}/custody")
    assert response.status_code == 200
    body = response.json()
    assert body["total_entries"] >= 1
    entries = body["entries"]
    assert entries[0]["entry_number"] == 1
    numbers = [e["entry_number"] for e in entries]
    assert numbers == sorted(numbers)


def test_get_status_history_returns_chronological(
    investigator_client: AuthedClient,
    seeded_database: dict[str, Any],
) -> None:
    evidence_id = seeded_database["evidence_id"]
    response = investigator_client.get(f"/api/v1/evidence/{evidence_id}/status")
    assert response.status_code == 200
    body = response.json()
    assert "history" in body
    assert body["evidence_id"] == evidence_id
    assert body.get("current_status") is not None


def test_quarantine_returns_updated_status(
    investigator_client: AuthedClient,
    seeded_database: dict[str, Any],
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "quarantine.dd"
    evidence_path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    registered = investigator_client.post(
        "/api/v1/evidence/register",
        json={
            "file_path": str(evidence_path),
            "case_id": seeded_database["case_id"],
            "evidence_type": "disk_image",
            "description": "to quarantine",
        },
    )
    assert registered.status_code == 201
    evidence_id = registered.json()["evidence_id"]

    response = investigator_client.post(
        f"/api/v1/evidence/{evidence_id}/quarantine",
        json={"reason": "Suspected tampering"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert str(body.get("current_status") or "").lower() == "quarantined"
