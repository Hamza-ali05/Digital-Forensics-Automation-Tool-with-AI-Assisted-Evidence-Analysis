"""Cases endpoint API contract tests."""

from __future__ import annotations

from typing import Any

from tests.contract.conftest import AuthedClient


def test_create_case_returns_201_with_case_id(
    investigator_client: AuthedClient,
) -> None:
    response = investigator_client.post(
        "/api/v1/cases",
        json={"case_name": "Contract Case", "description": "create contract"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["case_id"]
    assert body["case_name"] == "Contract Case"
    assert body["status"] in {"created", "CREATED"} or str(body["status"]).lower() == "created"


def test_create_case_viewer_returns_403(viewer_client: AuthedClient) -> None:
    response = viewer_client.post(
        "/api/v1/cases",
        json={"case_name": "Denied", "description": "viewer"},
    )
    assert response.status_code == 403


def test_list_cases_returns_paginated_array(
    investigator_client: AuthedClient,
) -> None:
    investigator_client.post(
        "/api/v1/cases",
        json={"case_name": "List Case A", "description": "a"},
    )
    response = investigator_client.get("/api/v1/cases")
    assert response.status_code == 200
    body = response.json()
    assert "cases" in body
    assert "total" in body
    assert isinstance(body["cases"], list)
    assert body["total"] >= 1


def test_get_case_returns_full_detail(
    investigator_client: AuthedClient,
) -> None:
    created = investigator_client.post(
        "/api/v1/cases",
        json={"case_name": "Detail Case", "description": "detail"},
    )
    case_id = created.json()["case_id"]
    response = investigator_client.get(f"/api/v1/cases/{case_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == case_id
    assert body["case_name"] == "Detail Case"
    assert "investigators" in body
    assert "evidence_ids" in body
    assert "status" in body


def test_get_case_nonexistent_returns_404(
    investigator_client: AuthedClient,
) -> None:
    response = investigator_client.get(
        "/api/v1/cases/00000000-0000-0000-0000-000000000099"
    )
    assert response.status_code == 404


def test_open_case_without_lead_returns_400(
    investigator_client: AuthedClient,
) -> None:
    created = investigator_client.post(
        "/api/v1/cases",
        json={"case_name": "No Lead Case", "description": "no lead"},
    )
    case_id = created.json()["case_id"]
    response = investigator_client.post(f"/api/v1/cases/{case_id}/open")
    assert response.status_code == 400
    assert response.json()["error_type"] == "NoLeadInvestigatorError"


def test_open_case_with_lead_returns_200(
    investigator_client: AuthedClient,
    seeded_db: dict[str, Any],
) -> None:
    created = investigator_client.post(
        "/api/v1/cases",
        json={"case_name": "Lead Case", "description": "with lead"},
    )
    case_id = created.json()["case_id"]
    assign = investigator_client.post(
        f"/api/v1/cases/{case_id}/investigators",
        json={
            "user_id": seeded_db["user_ids"]["investigator"],
            "role": "lead",
        },
    )
    assert assign.status_code == 200
    response = investigator_client.post(f"/api/v1/cases/{case_id}/open")
    assert response.status_code == 200
    assert str(response.json()["status"]).lower() == "open"


def test_invalid_transition_returns_409(
    investigator_client: AuthedClient,
    seeded_db: dict[str, Any],
) -> None:
    created = investigator_client.post(
        "/api/v1/cases",
        json={"case_name": "Transition Case", "description": "bad transition"},
    )
    case_id = created.json()["case_id"]
    # Activate without open is illegal from CREATED.
    response = investigator_client.post(f"/api/v1/cases/{case_id}/activate")
    assert response.status_code == 409
    assert response.json()["error_type"] == "InvalidCaseTransitionError"


def test_assign_investigator_returns_200(
    investigator_client: AuthedClient,
    seeded_db: dict[str, Any],
) -> None:
    created = investigator_client.post(
        "/api/v1/cases",
        json={"case_name": "Assign Case", "description": "assign"},
    )
    case_id = created.json()["case_id"]
    response = investigator_client.post(
        f"/api/v1/cases/{case_id}/investigators",
        json={
            "user_id": seeded_db["user_ids"]["analyst"],
            "role": "member",
        },
    )
    assert response.status_code == 200
    investigators = response.json()["investigators"]
    assert any(
        inv["user_id"] == seeded_db["user_ids"]["analyst"] for inv in investigators
    )


def test_close_case_returns_200_with_closed_status(
    investigator_client: AuthedClient,
    seeded_db: dict[str, Any],
) -> None:
    created = investigator_client.post(
        "/api/v1/cases",
        json={"case_name": "Close Case", "description": "close"},
    )
    case_id = created.json()["case_id"]
    investigator_client.post(
        f"/api/v1/cases/{case_id}/investigators",
        json={
            "user_id": seeded_db["user_ids"]["investigator"],
            "role": "lead",
        },
    )
    assert investigator_client.post(f"/api/v1/cases/{case_id}/open").status_code == 200
    assert (
        investigator_client.post(f"/api/v1/cases/{case_id}/activate").status_code == 200
    )
    response = investigator_client.post(
        f"/api/v1/cases/{case_id}/close",
        json={"reason": "Investigation complete"},
    )
    assert response.status_code == 200
    assert str(response.json()["status"]).lower() == "closed"
