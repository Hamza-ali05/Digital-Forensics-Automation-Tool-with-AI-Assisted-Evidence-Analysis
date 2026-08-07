"""Unit tests for AI monitoring and telemetry (Prompt 5.17)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.monitoring import AIMonitor
from dfat.ai_engine.validation import HallucinationReport
from dfat.core.enums import PipelineStage


@pytest.fixture
def audit_service() -> MagicMock:
    service = MagicMock()
    service.log_action = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_request_response_correlated_by_request_id(
    audit_service: MagicMock,
) -> None:
    monitor = AIMonitor(audit_service)
    request_id = await monitor.log_llm_request(
        request_type="generate",
        model="llama3",
        prompt_tokens=120,
        job_id="job-1",
    )
    await monitor.log_llm_response(
        request_id=request_id,
        completion_tokens=40,
        duration_ms=250.0,
        success=True,
        cache_hit=False,
    )

    assert request_id
    calls = audit_service.log_action.await_args_list
    assert len(calls) == 2
    req_details = calls[0].kwargs["details"]
    resp_details = calls[1].kwargs["details"]
    assert req_details["request_id"] == request_id
    assert resp_details["request_id"] == request_id
    assert calls[0].kwargs["action"] == "AI_LLM_REQUEST"
    assert calls[1].kwargs["action"] == "AI_LLM_RESPONSE"
    assert calls[0].kwargs["stage"] is PipelineStage.AI_TRIAGE


@pytest.mark.asyncio
async def test_prompt_content_never_logged(audit_service: MagicMock) -> None:
    monitor = AIMonitor(audit_service)
    # Even if a caller tries to sneak prompt into details via internal path,
    # _safe_details must strip forbidden keys — exercise via classification log
    # and by inspecting request log payloads.
    request_id = await monitor.log_llm_request("classify", "llama3", 10, "job-2")
    await monitor.log_classification("job-2", 5, 5, 0.8, 100.0)

    blob = json.dumps(
        [call.kwargs.get("details", {}) for call in audit_service.log_action.await_args_list]
    )
    assert "prompt" not in blob.lower() or "prompt_tokens" in blob
    # Ensure raw prompt text never present
    assert "You are a digital forensics" not in blob
    assert "raw_data" not in blob
    assert request_id


@pytest.mark.asyncio
async def test_usage_stats_aggregate_correctly(audit_service: MagicMock) -> None:
    monitor = AIMonitor(audit_service)
    rid1 = await monitor.log_llm_request("generate", "llama3", 100)
    await monitor.log_llm_response(rid1, 50, 200.0, True, False)
    rid2 = await monitor.log_llm_request("classify", "llama3", 80)
    await monitor.log_llm_response(rid2, 20, 100.0, True, True)
    await monitor.log_classification("job-1", 10, 10, 0.75, 50.0)
    await monitor.log_summarization("job-1", 500, 0.8, 75.0)

    stats = await monitor.get_ai_usage_stats()
    assert stats.total_requests == 2
    assert stats.total_tokens_in == 180
    assert stats.total_tokens_out == 70
    assert stats.avg_response_time_ms == pytest.approx(150.0)
    assert stats.cache_hit_rate == pytest.approx(0.5)
    assert stats.requests_by_type["generate"] == 1
    assert stats.requests_by_type["classify"] == 1
    assert stats.avg_confidence == pytest.approx(0.775)


@pytest.mark.asyncio
async def test_hallucination_events_tracked(audit_service: MagicMock) -> None:
    monitor = AIMonitor(audit_service)
    rid = await monitor.log_llm_request("qa", "llama3", 30)
    report = HallucinationReport(
        hallucinated_ids=["art-999"],
        fabricated_terms=["malware_signature"],
        unsupported_assertions=["it is clear that"],
        risk_level="high",
        clean_response="cleaned",
    )
    await monitor.log_hallucination_detected(rid, report)
    stats = await monitor.get_ai_usage_stats()
    assert stats.hallucination_detections == 1
    action = audit_service.log_action.await_args_list[-1].kwargs
    assert action["action"] == "AI_HALLUCINATION_DETECTED"
    assert action["details"]["hallucinated_id_count"] == 1
    assert "art-999" not in json.dumps(action["details"])
