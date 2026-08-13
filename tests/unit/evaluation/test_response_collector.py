"""Unit tests for anonymised usability response collection (Prompt 6.17)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from dfat.core.models.evaluation import UsabilityResponse
from dfat.evaluation.usability.questionnaire import QuestionnaireInstrument
from dfat.evaluation.usability.response_collector import ResponseCollector


def _collector() -> tuple[ResponseCollector, AsyncMock, AsyncMock]:
    """Build a ResponseCollector with mocked repo and audit service."""
    repo = AsyncMock()
    audit = AsyncMock()
    collector = ResponseCollector(
        questionnaire=QuestionnaireInstrument(),
        usability_repo=repo,
        audit_service=audit,
    )
    return collector, repo, audit


@pytest.mark.asyncio
async def test_collect_response_uses_uuid_participant_id() -> None:
    """Verify collected participant IDs are UUID format, not sequential."""
    collector, repo, audit = _collector()
    repo.save.return_value = "row-1"

    first = await collector.collect_response(
        {"usefulness": 4, "accuracy": 5, "clarity": 3},
        free_text="Helpful triage",
    )
    second = await collector.collect_response(
        {"usefulness": 5, "accuracy": 4, "clarity": 4},
    )

    UUID(first)
    UUID(second)
    assert first != second
    assert repo.save.await_count == 2
    saved: UsabilityResponse = repo.save.await_args_list[0].args[0]
    assert saved.participant_id == first
    assert saved.usefulness_rating == 4


@pytest.mark.asyncio
async def test_collect_response_audit_omits_content() -> None:
    """Verify audit logs collection metadata but not response content."""
    collector, _repo, audit = _collector()

    participant_id = await collector.collect_response(
        {"usefulness": 4, "accuracy": 5, "clarity": 3},
        free_text="secret feedback with alice@example.com",
    )

    audit.log_action.assert_awaited_once()
    kwargs = audit.log_action.await_args.kwargs
    assert kwargs["action"] == "USABILITY_RESPONSE_COLLECTED"
    details = kwargs["details"]
    assert details["participant_id"] == participant_id
    assert "usefulness" not in details
    assert "accuracy" not in details
    assert "clarity" not in details
    assert "free_text" not in str(details).lower()
    assert "alice@example.com" not in str(details)
    assert "rating" not in str(details).lower()


@pytest.mark.asyncio
async def test_export_responses_anonymised_redacts_email() -> None:
    """Verify export redacts email patterns from free text."""
    collector, repo, _audit = _collector()
    repo.get_all_responses.return_value = [
        UsabilityResponse(
            participant_id="11111111-1111-1111-1111-111111111111",
            usefulness_rating=4,
            accuracy_rating=4,
            clarity_rating=4,
            free_text_feedback="Contact me at alice@example.com please",
            submitted_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
    ]

    payload = await collector.export_responses_anonymised("json")
    parsed = json.loads(payload)

    assert parsed["response_count"] == 1
    free_text = parsed["responses"][0]["free_text_feedback"]
    assert "alice@example.com" not in free_text
    assert "[REDACTED_EMAIL]" in free_text
    assert parsed["responses"][0]["participant_id"].count("-") == 4


@pytest.mark.asyncio
async def test_delete_all_responses_logs_destruction() -> None:
    """Verify ethics data destruction deletes rows and audits the count."""
    collector, repo, audit = _collector()
    repo.delete_all_responses.return_value = 3

    deleted = await collector.delete_all_responses()

    assert deleted == 3
    repo.delete_all_responses.assert_awaited_once()
    audit.log_action.assert_awaited_once()
    kwargs = audit.log_action.await_args.kwargs
    assert kwargs["action"] == "USABILITY_DATA_DESTROYED"
    assert kwargs["details"] == {"deleted_count": 3}


@pytest.mark.asyncio
async def test_get_response_count_and_all_responses() -> None:
    """Verify count and list helpers delegate to the repository."""
    collector, repo, _audit = _collector()
    sample = [
        UsabilityResponse(
            participant_id="22222222-2222-2222-2222-222222222222",
            usefulness_rating=5,
            accuracy_rating=5,
            clarity_rating=5,
        )
    ]
    repo.count_responses.return_value = 1
    repo.get_all_responses.return_value = sample

    assert await collector.get_response_count() == 1
    assert await collector.get_all_responses() == sample
