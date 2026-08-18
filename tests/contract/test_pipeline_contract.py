"""Pipeline endpoint API contract tests."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from dfat.pipeline.enums import JobStatus
from tests.contract.conftest import AuthedClient, FakePipelineOrchestrator


def test_run_pipeline_returns_202_with_job_id(
    analyst_client: AuthedClient,
    fake_orchestrator: FakePipelineOrchestrator,
    seeded_database: dict[str, Any],
) -> None:
    response = analyst_client.post(
        "/api/v1/pipeline/run",
        json={
            "evidence_id": seeded_database["evidence_id"],
            "case_id": seeded_database["case_id"],
            "mode": "full",
            "use_fallback": True,
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert body["job_id"] in fake_orchestrator.jobs


def test_get_job_status_returns_progress(
    analyst_client: AuthedClient,
    fake_orchestrator: FakePipelineOrchestrator,
    seeded_database: dict[str, Any],
) -> None:
    submitted = analyst_client.post(
        "/api/v1/pipeline/run",
        json={
            "evidence_id": seeded_database["evidence_id"],
            "case_id": seeded_database["case_id"],
            "mode": "parse-only",
        },
    )
    job_id = submitted.json()["job_id"]

    status_resp = analyst_client.get(f"/api/v1/pipeline/{job_id}")
    progress_resp = analyst_client.get(f"/api/v1/pipeline/{job_id}/progress")

    assert status_resp.status_code == 200
    assert status_resp.json()["job_id"] == job_id
    assert progress_resp.status_code == 200
    progress = progress_resp.json()
    assert progress["job_id"] == job_id
    assert progress["stages_total"] == 5
    assert "status" in progress


def test_cancel_running_job_returns_200(
    analyst_client: AuthedClient,
    fake_orchestrator: FakePipelineOrchestrator,
    seeded_database: dict[str, Any],
) -> None:
    fake_orchestrator.auto_complete = False
    submitted = analyst_client.post(
        "/api/v1/pipeline/run",
        json={
            "evidence_id": seeded_database["evidence_id"],
            "case_id": seeded_database["case_id"],
            "mode": "full",
        },
    )
    job_id = submitted.json()["job_id"]
    # Ensure job is in a cancellable non-terminal state.
    fake_orchestrator.jobs[job_id].status = JobStatus.RUNNING

    response = analyst_client.post(f"/api/v1/pipeline/{job_id}/cancel")
    assert response.status_code == 200
    assert str(response.json()["status"]).lower() == "cancelled"


def test_cancel_completed_job_returns_409(
    analyst_client: AuthedClient,
    fake_orchestrator: FakePipelineOrchestrator,
    seeded_database: dict[str, Any],
) -> None:
    fake_orchestrator.auto_complete = True
    submitted = analyst_client.post(
        "/api/v1/pipeline/run",
        json={
            "evidence_id": seeded_database["evidence_id"],
            "case_id": seeded_database["case_id"],
            "mode": "full",
        },
    )
    job_id = submitted.json()["job_id"]
    fake_orchestrator.jobs[job_id].status = JobStatus.COMPLETED

    response = analyst_client.post(f"/api/v1/pipeline/{job_id}/cancel")
    assert response.status_code == 409
    assert response.json()["error_type"] == "JobCancellationError"


def test_list_jobs_filterable_by_status(
    analyst_client: AuthedClient,
    fake_orchestrator: FakePipelineOrchestrator,
    seeded_database: dict[str, Any],
) -> None:
    fake_orchestrator.auto_complete = True
    analyst_client.post(
        "/api/v1/pipeline/run",
        json={
            "evidence_id": seeded_database["evidence_id"],
            "case_id": seeded_database["case_id"],
            "mode": "full",
        },
    )
    response = analyst_client.get(
        "/api/v1/pipeline/jobs",
        params={"status": "completed", "case_id": seeded_database["case_id"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert all(str(job["status"]).lower() == "completed" for job in body)


def test_get_parsers_returns_availability(
    analyst_client: AuthedClient,
    fake_orchestrator: FakePipelineOrchestrator,
) -> None:
    response = analyst_client.get("/api/v1/pipeline/parsers")
    assert response.status_code == 200
    body = response.json()
    parsers = body["parsers"] if isinstance(body, dict) else body
    assert isinstance(parsers, list)
    assert parsers
    assert "parser_name" in parsers[0]
    assert "available" in parsers[0]
