"""Integration tests for pipeline REST API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from dfat.core.enums import PipelineStage
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.models import PipelineJob, PipelineProgress


def _auth(client: TestClient) -> dict[str, str]:
    """Analyst bearer auth header."""
    return {"Authorization": f"Bearer {client.analyst_token}"}


class _FakePipelineOrchestrator:
    """In-memory orchestrator stand-in for API route tests."""

    def __init__(self) -> None:
        self.jobs: dict[str, PipelineJob] = {}
        self._auto_complete = True

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
        if self._auto_complete:
            job.status = JobStatus.COMPLETED
            job.current_stage = PipelineStage.EVALUATION
            job.completed_at = datetime.now(UTC)
            job.artefact_count = 5
            job.report_id = "rep-test-1"
        return job

    async def get_job(self, job_id: str) -> PipelineJob:
        return self.jobs[job_id]

    async def get_pipeline_status(self, job_id: str) -> PipelineProgress:
        job = self.jobs[job_id]
        completed = 5 if job.status is JobStatus.COMPLETED else 0
        return PipelineProgress(
            job_id=job_id,
            status=job.status,
            current_stage=(
                job.current_stage.value if job.current_stage is not None else None
            ),
            stages_completed=completed,
            stages_total=5,
            artefacts_found_so_far=job.artefact_count,
        )

    async def cancel_pipeline(self, job_id: str, user_id: str) -> PipelineJob:
        job = self.jobs[job_id]
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(UTC)
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
        return [
            {
                "parser_name": "FileSystemParser",
                "available": True,
                "supported_evidence_types": ["disk_image"],
            }
        ]


@pytest.fixture
def fake_orchestrator(app_client: TestClient) -> _FakePipelineOrchestrator:
    """Override the DI orchestrator with an in-memory fake."""
    fake = _FakePipelineOrchestrator()
    container = app_client.app.state.container
    container.pipeline.pipeline_orchestrator.override(fake)
    try:
        yield fake
    finally:
        container.pipeline.pipeline_orchestrator.reset_override()


def test_submit_pipeline_job_returns_202(
    app_client: TestClient,
    fake_orchestrator: _FakePipelineOrchestrator,
) -> None:
    """Verify POST /pipeline/run submits a job and returns 202."""
    # Act
    response = app_client.post(
        "/api/v1/pipeline/run",
        headers=_auth(app_client),
        json={
            "evidence_id": "ev-api-1",
            "case_id": "case-api-1",
            "mode": "full",
            "use_fallback": True,
        },
    )

    # Assert
    assert response.status_code == 202
    body = response.json()
    assert body["evidence_id"] == "ev-api-1"
    assert body["case_id"] == "case-api-1"
    assert body["job_id"] in fake_orchestrator.jobs


def test_get_pipeline_status_and_progress(
    app_client: TestClient,
    fake_orchestrator: _FakePipelineOrchestrator,
) -> None:
    """Verify job status and progress endpoints after submission."""
    # Arrange
    submit = app_client.post(
        "/api/v1/pipeline/run",
        headers=_auth(app_client),
        json={
            "evidence_id": "ev-api-2",
            "case_id": "case-api-2",
            "mode": "parse-only",
        },
    )
    job_id = submit.json()["job_id"]

    # Act
    status_resp = app_client.get(
        f"/api/v1/pipeline/{job_id}",
        headers=_auth(app_client),
    )
    progress_resp = app_client.get(
        f"/api/v1/pipeline/{job_id}/progress",
        headers=_auth(app_client),
    )

    # Assert
    assert status_resp.status_code == 200
    assert status_resp.json()["job_id"] == job_id
    # Background task should have marked the job completed.
    assert status_resp.json()["status"] == JobStatus.COMPLETED.value
    assert progress_resp.status_code == 200
    assert progress_resp.json()["job_id"] == job_id
    assert progress_resp.json()["stages_total"] == 5


def test_pipeline_job_completion_lists_in_jobs(
    app_client: TestClient,
    fake_orchestrator: _FakePipelineOrchestrator,
) -> None:
    """Verify completed jobs appear in GET /pipeline/jobs."""
    # Arrange
    app_client.post(
        "/api/v1/pipeline/run",
        headers=_auth(app_client),
        json={
            "evidence_id": "ev-api-3",
            "case_id": "case-api-3",
            "mode": "full",
        },
    )

    # Act
    response = app_client.get(
        "/api/v1/pipeline/jobs",
        headers=_auth(app_client),
        params={"status": "completed", "case_id": "case-api-3"},
    )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["status"] == "completed"
    assert body[0]["case_id"] == "case-api-3"


def test_cancel_pipeline_job(
    app_client: TestClient,
    fake_orchestrator: _FakePipelineOrchestrator,
) -> None:
    """Verify owner can cancel a job via POST /pipeline/{id}/cancel."""
    # Arrange — keep job queued (skip auto-complete for cancel race).
    fake_orchestrator._auto_complete = False  # noqa: SLF001
    submit = app_client.post(
        "/api/v1/pipeline/run",
        headers=_auth(app_client),
        json={
            "evidence_id": "ev-api-4",
            "case_id": "case-api-4",
            "mode": "full",
        },
    )
    job_id = submit.json()["job_id"]
    # Reset status to queued in case background execute ran without completing.
    fake_orchestrator.jobs[job_id].status = JobStatus.QUEUED

    # Act
    response = app_client.post(
        f"/api/v1/pipeline/{job_id}/cancel",
        headers=_auth(app_client),
    )

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == JobStatus.CANCELLED.value
    assert fake_orchestrator.jobs[job_id].status is JobStatus.CANCELLED
