"""Fixtures for DFAT API contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from dfat.core.enums import PipelineStage
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.job_manager import JobCancellationError
from dfat.pipeline.models import PipelineJob, PipelineProgress
from tests.conftest import SAMPLE_EVIDENCE_DIR


class AuthedClient:
    """Thin wrapper that injects a bearer token on every request."""

    def __init__(self, client: TestClient, token: str) -> None:
        self.client = client
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}

    def get(self, url: str, **kwargs: Any):
        return self.client.get(url, headers=self._merge(kwargs), **kwargs)

    def post(self, url: str, **kwargs: Any):
        return self.client.post(url, headers=self._merge(kwargs), **kwargs)

    def put(self, url: str, **kwargs: Any):
        return self.client.put(url, headers=self._merge(kwargs), **kwargs)

    def delete(self, url: str, **kwargs: Any):
        return self.client.delete(url, headers=self._merge(kwargs), **kwargs)

    def _merge(self, kwargs: dict[str, Any]) -> dict[str, str]:
        headers = dict(self.headers)
        extra = kwargs.pop("headers", None) or {}
        headers.update(extra)
        return headers


@pytest.fixture
def authenticated_client(app_client: TestClient) -> TestClient:
    """Raw TestClient with role tokens attached."""
    return app_client


@pytest.fixture
def admin_client(app_client: TestClient) -> AuthedClient:
    return AuthedClient(app_client, app_client.admin_token)  # type: ignore[attr-defined]


@pytest.fixture
def investigator_client(app_client: TestClient) -> AuthedClient:
    return AuthedClient(
        app_client, app_client.investigator_token  # type: ignore[attr-defined]
    )


@pytest.fixture
def analyst_client(app_client: TestClient) -> AuthedClient:
    return AuthedClient(app_client, app_client.analyst_token)  # type: ignore[attr-defined]


@pytest.fixture
def viewer_client(app_client: TestClient) -> AuthedClient:
    return AuthedClient(app_client, app_client.viewer_token)  # type: ignore[attr-defined]


@pytest.fixture
def seeded_database(
    app_client: TestClient,
    seeded_db: dict[str, Any],
    tmp_path: Path,
) -> dict[str, Any]:
    """Seed an OPEN case with registered evidence for contract tests."""
    headers = {
        "Authorization": f"Bearer {app_client.investigator_token}"  # type: ignore[attr-defined]
    }
    created = app_client.post(
        "/api/v1/cases",
        headers=headers,
        json={
            "case_name": "Contract Seed Case",
            "description": "Seeded for contract tests",
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]

    assign = app_client.post(
        f"/api/v1/cases/{case_id}/investigators",
        headers=headers,
        json={
            "user_id": seeded_db["user_ids"]["investigator"],
            "role": "lead",
        },
    )
    assert assign.status_code == 200, assign.text

    opened = app_client.post(f"/api/v1/cases/{case_id}/open", headers=headers)
    assert opened.status_code == 200, opened.text

    evidence_path = tmp_path / "contract_seed.dd"
    evidence_path.write_bytes((SAMPLE_EVIDENCE_DIR / "test_disk.dd").read_bytes())
    registered = app_client.post(
        "/api/v1/evidence/register",
        headers=headers,
        json={
            "file_path": str(evidence_path),
            "case_id": case_id,
            "evidence_type": "disk_image",
            "description": "contract seed evidence",
        },
    )
    assert registered.status_code == 201, registered.text
    evidence_body = registered.json()

    return {
        "case_id": case_id,
        "evidence_id": evidence_body["evidence_id"],
        "evidence_path": str(evidence_path),
        "seeded_db": seeded_db,
        "report_id": None,
    }


class FakePipelineOrchestrator:
    """In-memory orchestrator for pipeline contract tests."""

    def __init__(self) -> None:
        self.jobs: dict[str, PipelineJob] = {}
        self.auto_complete = False

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
        if self.auto_complete:
            job.status = JobStatus.COMPLETED
            job.current_stage = PipelineStage.EVALUATION
            job.completed_at = datetime.now(UTC)
            job.artefact_count = 3
            job.report_id = "rep-contract-1"
        else:
            job.status = JobStatus.RUNNING
            job.current_stage = PipelineStage.PARSING
            job.started_at = datetime.now(UTC)
        return job

    async def get_job(self, job_id: str) -> PipelineJob:
        return self.jobs[job_id]

    async def get_pipeline_status(self, job_id: str) -> PipelineProgress:
        job = self.jobs[job_id]
        completed = 5 if job.status is JobStatus.COMPLETED else 1
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
        terminal = {
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMED_OUT,
        }
        if job.status in terminal:
            raise JobCancellationError(
                f"Job cannot be cancelled in status {job.status.value}",
                context={"job_id": job_id, "status": job.status.value},
            )
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
            },
            {
                "parser_name": "ProcessListParser",
                "available": False,
                "supported_evidence_types": ["memory_dump"],
            },
        ]


@pytest.fixture
def fake_orchestrator(app_client: TestClient) -> FakePipelineOrchestrator:
    fake = FakePipelineOrchestrator()
    container = app_client.app.state.container
    container.pipeline.pipeline_orchestrator.override(fake)
    try:
        yield fake
    finally:
        container.pipeline.pipeline_orchestrator.reset_override()
