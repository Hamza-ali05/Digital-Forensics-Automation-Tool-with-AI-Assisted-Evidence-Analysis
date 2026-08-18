"""Case lifecycle multi-step API integration flows (Prompt 9.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from dfat.core.enums import PipelineStage
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.models import PipelineJob, PipelineProgress
from tests.conftest import SAMPLE_EVIDENCE_DIR


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _FakePipelineOrchestrator:
    """In-memory pipeline orchestrator for HTTP case-flow tests."""

    def __init__(self) -> None:
        self.jobs: dict[str, PipelineJob] = {}

    async def submit_pipeline(
        self,
        evidence_id: str,
        case_id: str,
        user_id: str,
        mode: str = "full",
        use_fallback: bool = False,
        *,
        metadata: Optional[dict] = None,
    ) -> PipelineJob:
        job = PipelineJob(
            job_id=str(uuid4()),
            evidence_id=evidence_id,
            case_id=case_id,
            user_id=user_id,
            status=JobStatus.QUEUED,
            mode=mode,
            use_fallback_analyzer=use_fallback,
            created_at=datetime.now(UTC),
        )
        self.jobs[job.job_id] = job
        return job

    async def execute_submitted_job(self, job_id: str) -> PipelineJob:
        job = self.jobs[job_id]
        job.status = JobStatus.COMPLETED
        job.current_stage = PipelineStage.EVALUATION
        job.completed_at = datetime.now(UTC)
        job.artefact_count = 3
        job.report_id = f"rep-{job_id[:8]}"
        return job

    async def get_job(self, job_id: str) -> PipelineJob:
        return self.jobs[job_id]

    async def get_pipeline_status(self, job_id: str) -> PipelineProgress:
        job = self.jobs[job_id]
        return PipelineProgress(
            job_id=job_id,
            status=job.status,
            current_stage=(
                job.current_stage.value if job.current_stage is not None else None
            ),
            stages_completed=5 if job.status is JobStatus.COMPLETED else 0,
            stages_total=5,
            artefacts_found_so_far=job.artefact_count,
        )

    async def cancel_pipeline(self, job_id: str, user_id: str) -> PipelineJob:
        job = self.jobs[job_id]
        job.status = JobStatus.CANCELLED
        return job

    async def list_pipeline_jobs(
        self,
        *,
        status: Optional[JobStatus] = None,
        case_id: Optional[str] = None,
    ) -> list[PipelineJob]:
        jobs = list(self.jobs.values())
        if status is not None:
            jobs = [job for job in jobs if job.status is status]
        if case_id is not None:
            jobs = [job for job in jobs if job.case_id == case_id]
        return jobs

    def list_parsers(self) -> list[dict]:
        return []


@pytest.fixture
def fake_orchestrator(app_client: TestClient) -> _FakePipelineOrchestrator:
    fake = _FakePipelineOrchestrator()
    container = app_client.app.state.container
    container.pipeline.pipeline_orchestrator.override(fake)
    try:
        yield fake
    finally:
        container.pipeline.pipeline_orchestrator.reset_override()


def _create_open_active_case(
    client: TestClient,
    headers: dict[str, str],
    seeded_db: dict[str, Any],
    *,
    name: str,
) -> str:
    created = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"case_name": name, "description": "lifecycle flow"},
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]
    assign = client.post(
        f"/api/v1/cases/{case_id}/investigators",
        headers=headers,
        json={"user_id": seeded_db["user_ids"]["investigator"], "role": "lead"},
    )
    assert assign.status_code == 200, assign.text
    opened = client.post(f"/api/v1/cases/{case_id}/open", headers=headers)
    assert opened.status_code == 200
    assert opened.json()["status"] == "open"
    active = client.post(f"/api/v1/cases/{case_id}/activate", headers=headers)
    assert active.status_code == 200
    assert active.json()["status"] == "active"
    return case_id


def _register_evidence(
    client: TestClient,
    headers: dict[str, str],
    case_id: str,
    path: Path,
    *,
    evidence_type: str = "disk_image",
) -> str:
    response = client.post(
        "/api/v1/evidence/register",
        headers=headers,
        json={
            "file_path": str(path),
            "case_id": case_id,
            "evidence_type": evidence_type,
            "description": path.name,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["validation_passed"] is True
    return response.json()["evidence_id"]


def test_complete_case_lifecycle(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
    fake_orchestrator: _FakePipelineOrchestrator,
) -> None:
    """create → lead → open → activate → evidence → pipeline → review → close → archive."""
    inv = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    analyst = _auth(app_client.analyst_token)  # type: ignore[attr-defined]

    created = app_client.post(
        "/api/v1/cases",
        headers=inv,
        json={"case_name": "Complete Lifecycle", "description": "prompt-9.4"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    assert created.json()["status"] == "created"

    assign = app_client.post(
        f"/api/v1/cases/{case_id}/investigators",
        headers=inv,
        json={"user_id": seeded_db["user_ids"]["investigator"], "role": "lead"},
    )
    assert assign.status_code == 200
    assert assign.json()["lead_investigator_id"] == seeded_db["user_ids"]["investigator"]

    opened = app_client.post(f"/api/v1/cases/{case_id}/open", headers=inv)
    assert opened.json()["status"] == "open"

    active = app_client.post(f"/api/v1/cases/{case_id}/activate", headers=inv)
    assert active.json()["status"] == "active"

    evidence_path = tmp_path / "lifecycle.dd"
    evidence_path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    evidence_id = _register_evidence(app_client, inv, case_id, evidence_path)

    custody = app_client.get(f"/api/v1/evidence/{evidence_id}/custody", headers=inv)
    assert custody.status_code == 200
    assert any(entry["action"] == "acquired" for entry in custody.json()["entries"])

    run = app_client.post(
        "/api/v1/pipeline/run",
        headers=analyst,
        json={
            "evidence_id": evidence_id,
            "case_id": case_id,
            "mode": "full",
            "use_fallback": True,
        },
    )
    assert run.status_code == 202, run.text
    job_id = run.json()["job_id"]
    status = app_client.get(f"/api/v1/pipeline/{job_id}", headers=analyst)
    assert status.status_code == 200
    assert status.json()["status"] == JobStatus.COMPLETED.value

    review = app_client.post(f"/api/v1/cases/{case_id}/submit-review", headers=inv)
    assert review.json()["status"] == "under_review"

    closed = app_client.post(
        f"/api/v1/cases/{case_id}/close",
        headers=inv,
        json={"reason": "Investigation complete"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    sealed_custody = app_client.get(
        f"/api/v1/evidence/{evidence_id}/custody", headers=inv
    )
    assert sealed_custody.status_code == 200
    assert any(
        entry["action"] == "sealed" for entry in sealed_custody.json()["entries"]
    )

    archived = app_client.post(f"/api/v1/cases/{case_id}/archive", headers=inv)
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_case_with_multiple_evidence(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
    fake_orchestrator: _FakePipelineOrchestrator,
) -> None:
    """Three evidence items → pipeline each → inventory → close seals all."""
    inv = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    analyst = _auth(app_client.analyst_token)  # type: ignore[attr-defined]
    case_id = _create_open_active_case(
        app_client, inv, seeded_db, name="Multi Evidence Case"
    )

    evidence_ids: list[str] = []
    for index in range(3):
        path = tmp_path / f"multi-{index}.dd"
        path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
        evidence_id = _register_evidence(app_client, inv, case_id, path)
        evidence_ids.append(evidence_id)
        run = app_client.post(
            "/api/v1/pipeline/run",
            headers=analyst,
            json={
                "evidence_id": evidence_id,
                "case_id": case_id,
                "mode": "full",
                "use_fallback": True,
            },
        )
        assert run.status_code == 202, run.text

    inventory = app_client.get(
        "/api/v1/evidence/inventory",
        headers=inv,
        params={"case_id": case_id},
    )
    assert inventory.status_code == 200
    assert inventory.json()["total"] >= 3
    listed = {item["evidence_id"] for item in inventory.json()["items"]}
    assert set(evidence_ids).issubset(listed)

    closed = app_client.post(
        f"/api/v1/cases/{case_id}/close",
        headers=inv,
        json={"reason": "All evidence processed"},
    )
    assert closed.status_code == 200

    for evidence_id in evidence_ids:
        custody = app_client.get(
            f"/api/v1/evidence/{evidence_id}/custody", headers=inv
        )
        assert custody.status_code == 200
        assert any(entry["action"] == "sealed" for entry in custody.json()["entries"])


def test_case_reopen_flow(
    app_client: TestClient,
    seeded_db: dict[str, Any],
) -> None:
    """create → open → activate → review → reopen (reason required) → activate → close."""
    inv = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    case_id = _create_open_active_case(
        app_client, inv, seeded_db, name="Reopen Flow Case"
    )

    review = app_client.post(f"/api/v1/cases/{case_id}/submit-review", headers=inv)
    assert review.json()["status"] == "under_review"

    missing_reason = app_client.post(
        f"/api/v1/cases/{case_id}/reopen",
        headers=inv,
        json={},
    )
    assert missing_reason.status_code == 422

    empty_reason = app_client.post(
        f"/api/v1/cases/{case_id}/reopen",
        headers=inv,
        json={"reason": ""},
    )
    assert empty_reason.status_code == 422

    reopened = app_client.post(
        f"/api/v1/cases/{case_id}/reopen",
        headers=inv,
        json={"reason": "New lead identified"},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "active"

    # Under review again then close from active path via review → close if needed.
    # ACTIVE can go to UNDER_REVIEW then CLOSE, or some systems close from ACTIVE.
    # Existing transitions: ACTIVE → UNDER_REVIEW → CLOSED.
    review_again = app_client.post(
        f"/api/v1/cases/{case_id}/submit-review", headers=inv
    )
    assert review_again.json()["status"] == "under_review"

    closed = app_client.post(
        f"/api/v1/cases/{case_id}/close",
        headers=inv,
        json={"reason": "Closed after reopen"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


def test_multi_investigator_case(
    app_client: TestClient,
    seeded_db: dict[str, Any],
) -> None:
    """Assign lead + two members, remove one member, verify case visibility."""
    inv = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    analyst = _auth(app_client.analyst_token)  # type: ignore[attr-defined]
    admin = _auth(app_client.admin_token)  # type: ignore[attr-defined]

    created = app_client.post(
        "/api/v1/cases",
        headers=inv,
        json={"case_name": "Multi Investigator", "description": None},
    )
    case_id = created.json()["case_id"]
    lead_id = seeded_db["user_ids"]["investigator"]
    member_a = seeded_db["user_ids"]["analyst"]
    member_b = seeded_db["user_ids"]["admin"]

    assert (
        app_client.post(
            f"/api/v1/cases/{case_id}/investigators",
            headers=inv,
            json={"user_id": lead_id, "role": "lead"},
        ).status_code
        == 200
    )
    assert (
        app_client.post(
            f"/api/v1/cases/{case_id}/investigators",
            headers=inv,
            json={"user_id": member_a, "role": "member"},
        ).status_code
        == 200
    )
    assigned = app_client.post(
        f"/api/v1/cases/{case_id}/investigators",
        headers=inv,
        json={"user_id": member_b, "role": "member"},
    )
    assert assigned.status_code == 200
    investigators = {
        item["user_id"]: item["role"] for item in assigned.json()["investigators"]
    }
    assert investigators[lead_id] == "lead"
    assert investigators[member_a] == "member"
    assert investigators[member_b] == "member"

    # All assigned investigators can read the case (RBAC cases:read).
    for headers in (inv, analyst, admin):
        detail = app_client.get(f"/api/v1/cases/{case_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["case_id"] == case_id

    removed = app_client.delete(
        f"/api/v1/cases/{case_id}/investigators/{member_a}",
        headers=inv,
    )
    assert removed.status_code == 200, removed.text
    remaining_ids = {item["user_id"] for item in removed.json()["investigators"]}
    assert member_a not in remaining_ids
    assert lead_id in remaining_ids
    assert member_b in remaining_ids

    # Lead and remaining member still see the case on /mine when applicable.
    mine_lead = app_client.get("/api/v1/cases/mine", headers=inv)
    assert mine_lead.status_code == 200
    mine_body = mine_lead.json()
    mine_cases = mine_body.get("cases", mine_body if isinstance(mine_body, list) else [])
    assert any(item["case_id"] == case_id for item in mine_cases)
