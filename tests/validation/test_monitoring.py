"""Validation tests for health, AI telemetry, and pipeline progress."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from dfat.ai_engine.monitoring.ai_monitor import AIMonitor
from dfat.core.enums import PipelineStage
from dfat.monitoring.health_aggregator import HealthAggregator
from dfat.pipeline.enums import JobStatus
from dfat.pipeline.models import PipelineJob, PipelineProgress
from dfat.pipeline.progress_tracker import ProgressTracker


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _ProgressOrchestrator:
    """Expose a ProgressTracker through the pipeline progress HTTP API."""

    def __init__(self, tracker: ProgressTracker) -> None:
        self._tracker = tracker

    async def get_pipeline_status(self, job_id: str) -> PipelineProgress:
        return self._tracker.get_progress(job_id)

    async def list_pipeline_jobs(
        self,
        *,
        status: JobStatus | None = None,
        case_id: str | None = None,
    ) -> list[PipelineJob]:
        return []


def test_health_endpoint_reflects_actual_state(app_client: TestClient) -> None:
    """Stopping the database flips ready.database to false; restoring flips it back."""
    # Arrange
    container = app_client.app.state.container
    engine = container.database.database_engine()
    original_check = engine.check_connection

    async def _unavailable() -> bool:
        return False

    # Act — database unavailable
    engine.check_connection = _unavailable  # type: ignore[method-assign]
    try:
        down = app_client.get("/api/v1/health/ready")
    finally:
        engine.check_connection = original_check  # type: ignore[method-assign]

    # Act — database restored
    up = app_client.get("/api/v1/health/ready")

    # Assert
    assert down.status_code == 200, down.text
    down_body = down.json()
    assert down_body["checks"]["database"] is False
    assert down_body["status"] == "unavailable"

    assert up.status_code == 200, up.text
    up_body = up.json()
    assert up_body["checks"]["database"] is True
    assert up_body["status"] in {"ready", "degraded"}
    assert HealthAggregator.overall_status(down_body["checks"]) == "unhealthy"
    assert HealthAggregator.overall_status(up_body["checks"]) in {"healthy", "degraded"}


async def test_ai_monitoring_stats_accurate() -> None:
    """Five LLM request/response pairs produce matching usage counters."""
    # Arrange
    monitor = AIMonitor(audit_service=AsyncMock())
    tokens_in = [10, 20, 30, 40, 50]
    tokens_out = [1, 2, 3, 4, 5]
    durations = [100.0, 200.0, 300.0, 400.0, 500.0]

    # Act
    for index in range(5):
        request_id = await monitor.log_llm_request(
            "generate",
            "llama3",
            prompt_tokens=tokens_in[index],
            job_id="job-ai-stats",
        )
        await monitor.log_llm_response(
            request_id,
            completion_tokens=tokens_out[index],
            duration_ms=durations[index],
            success=True,
            cache_hit=False,
        )
    stats = await monitor.get_ai_usage_stats()

    # Assert
    assert stats.total_requests == 5
    assert stats.total_tokens_in == sum(tokens_in)
    assert stats.total_tokens_out == sum(tokens_out)
    assert stats.avg_response_time_ms == sum(durations) / len(durations)
    assert stats.requests_by_type.get("generate") == 5


def test_pipeline_progress_tracking_accurate(app_client: TestClient) -> None:
    """Polled pipeline percent complete increases monotonically and reaches 100%."""
    # Arrange
    tracker = ProgressTracker()
    job_id = f"job-progress-{uuid4().hex[:8]}"
    tracker.start_job(job_id, total_stages=len(PipelineStage))
    container = app_client.app.state.container
    fake = _ProgressOrchestrator(tracker)
    headers = _auth(app_client.investigator_token)  # type: ignore[attr-defined]
    container.pipeline.pipeline_orchestrator.override(fake)

    try:
        # Act
        percents: list[float] = []
        initial = app_client.get(f"/api/v1/pipeline/{job_id}/progress", headers=headers)
        assert initial.status_code == 200, initial.text
        percents.append(float(initial.json()["percent_complete"]))
        for stage in PipelineStage:
            tracker.start_stage(job_id, stage)
            started = app_client.get(
                f"/api/v1/pipeline/{job_id}/progress", headers=headers
            )
            assert started.status_code == 200, started.text
            percents.append(float(started.json()["percent_complete"]))
            tracker.complete_stage(job_id, stage, artefacts_found=1)
            completed = app_client.get(
                f"/api/v1/pipeline/{job_id}/progress", headers=headers
            )
            assert completed.status_code == 200, completed.text
            percents.append(float(completed.json()["percent_complete"]))
    finally:
        container.pipeline.pipeline_orchestrator.reset_override()

    # Assert
    assert percents
    assert all(
        percents[index] <= percents[index + 1] for index in range(len(percents) - 1)
    ), percents
    assert percents[0] == 0.0
    assert percents[-1] == 100.0
    assert max(percents) == 100.0
