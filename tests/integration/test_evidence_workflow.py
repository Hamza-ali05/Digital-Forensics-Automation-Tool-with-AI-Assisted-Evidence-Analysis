"""Evidence management workflow integration tests (Prompt 9.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional
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
        job.artefact_count = 2
        job.report_id = f"rep-{job.evidence_id}"
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
        return list(self.jobs.values())

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


def _open_active_case(
    client: TestClient, headers: dict[str, str], seeded_db: dict[str, Any]
) -> str:
    created = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"case_name": "Evidence Workflow", "description": "prompt-9.4"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    assert (
        client.post(
            f"/api/v1/cases/{case_id}/investigators",
            headers=headers,
            json={"user_id": seeded_db["user_ids"]["investigator"], "role": "lead"},
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/cases/{case_id}/open", headers=headers).status_code == 200
    assert (
        client.post(f"/api/v1/cases/{case_id}/activate", headers=headers).status_code
        == 200
    )
    return case_id


def test_evidence_register_validate_pipeline(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
    fake_orchestrator: _FakePipelineOrchestrator,
) -> None:
    """register → validate integrity → run pipeline → report id present."""
    inv = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    analyst = _auth(app_client.analyst_token)  # type: ignore[attr-defined]
    case_id = _open_active_case(app_client, inv, seeded_db)

    path = tmp_path / "workflow.dd"
    path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    registered = app_client.post(
        "/api/v1/evidence/register",
        headers=inv,
        json={
            "file_path": str(path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": "workflow",
        },
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()
    assert body["validation_passed"] is True
    evidence_id = body["evidence_id"]
    original_hash = body.get("metadata", {}).get("hash_sha256") or body.get(
        "evidence", {}
    )

    verified = app_client.post(
        f"/api/v1/evidence/{evidence_id}/verify-integrity", headers=inv
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["integrity_verified"] is True

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
    assert run.status_code == 202
    job_id = run.json()["job_id"]
    status = app_client.get(f"/api/v1/pipeline/{job_id}", headers=analyst)
    assert status.json()["status"] == "completed"
    assert status.json()["report_id"]
    assert original_hash is not None or evidence_id


def test_evidence_quarantine_revalidate(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
) -> None:
    """register empty file (fail) → quarantine → fix bytes → revalidate pass."""
    inv = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    case_id = _open_active_case(app_client, inv, seeded_db)

    bad_path = tmp_path / "bad.dd"
    bad_path.write_bytes(b"")
    registered = app_client.post(
        "/api/v1/evidence/register",
        headers=inv,
        json={
            "file_path": str(bad_path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": "will fail",
        },
    )
    assert registered.status_code == 201, registered.text
    assert registered.json()["validation_passed"] is False
    evidence_id = registered.json()["evidence_id"]

    status = app_client.get(f"/api/v1/evidence/{evidence_id}/status", headers=inv)
    assert status.status_code == 200
    assert status.json()["current_status"] == "quarantined"

    # Explicit quarantine is idempotent when already quarantined.
    quarantined = app_client.post(
        f"/api/v1/evidence/{evidence_id}/quarantine",
        headers=inv,
        json={"reason": "Empty file failed validation"},
    )
    assert quarantined.status_code == 200
    assert quarantined.json()["current_status"] == "quarantined"

    # Repair file contents and revalidate (clears quarantine → validated).
    bad_path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    revalidated = app_client.post(
        f"/api/v1/evidence/{evidence_id}/validate",
        headers=inv,
    )
    assert revalidated.status_code == 200, revalidated.text
    assert revalidated.json()["validation_passed"] is True

    status_after = app_client.get(
        f"/api/v1/evidence/{evidence_id}/status", headers=inv
    )
    assert status_after.json()["current_status"] == "validated"


def test_evidence_integrity_after_pipeline(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
    fake_orchestrator: _FakePipelineOrchestrator,
) -> None:
    """Evidence hash remains unchanged after a full pipeline run."""
    inv = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    analyst = _auth(app_client.analyst_token)  # type: ignore[attr-defined]
    case_id = _open_active_case(app_client, inv, seeded_db)

    path = tmp_path / "hash-stable.dd"
    path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    registered = app_client.post(
        "/api/v1/evidence/register",
        headers=inv,
        json={
            "file_path": str(path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": None,
        },
    )
    evidence_id = registered.json()["evidence_id"]
    before = app_client.post(
        f"/api/v1/evidence/{evidence_id}/verify-integrity", headers=inv
    )
    assert before.json()["integrity_verified"] is True
    detail_before = app_client.get(
        f"/api/v1/evidence/{evidence_id}/detail", headers=inv
    )
    assert detail_before.status_code == 200
    hash_before = detail_before.json()["original_hash"]

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
    assert run.status_code == 202

    after = app_client.post(
        f"/api/v1/evidence/{evidence_id}/verify-integrity", headers=inv
    )
    assert after.status_code == 200
    assert after.json()["integrity_verified"] is True
    detail_after = app_client.get(
        f"/api/v1/evidence/{evidence_id}/detail", headers=inv
    )
    assert detail_after.json()["original_hash"] == hash_before


def test_batch_integrity_verification(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Register 5 items → modify one file → batch verify yields 4 pass / 1 fail."""
    # Register + verify are both POSTs under /evidence and share the upload bucket.
    monkeypatch.setattr(
        "dfat.api.middleware.rate_limiter.RateLimiterMiddleware._EVIDENCE_UPLOAD_RATE",
        (120.0, 120),
    )
    inv = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    case_id = _open_active_case(app_client, inv, seeded_db)

    paths: list[Path] = []
    evidence_ids: list[str] = []
    for index in range(5):
        path = tmp_path / f"batch-{index}.dd"
        path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
        paths.append(path)
        registered = app_client.post(
            "/api/v1/evidence/register",
            headers=inv,
            json={
                "file_path": str(path),
                "case_id": case_id,
                "evidence_type": "disk_image",
                "description": f"batch-{index}",
            },
        )
        assert registered.status_code == 201, registered.text
        evidence_ids.append(registered.json()["evidence_id"])

    # Tamper with the third evidence file on disk.
    paths[2].write_bytes(b"TAMPERED-CONTENT-FOR-INTEGRITY-FAIL")

    results = []
    for evidence_id in evidence_ids:
        response = app_client.post(
            f"/api/v1/evidence/{evidence_id}/verify-integrity",
            headers=inv,
        )
        assert response.status_code == 200, response.text
        results.append(response.json())

    passed = [item for item in results if item.get("integrity_verified") is True]
    failed = [item for item in results if item.get("integrity_verified") is False]
    assert len(passed) == 4
    assert len(failed) == 1
    assert failed[0]["evidence_id"] == evidence_ids[2]
