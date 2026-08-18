"""AI subsystem edge cases for empty and malformed inputs."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dfat.ai_engine.caching import AIResponseCache
from dfat.ai_engine.llm.client import LLMResponse
from dfat.ai_engine.summarization.validator import SummaryResponseValidator
from dfat.ai_engine.triage.classifier import ArtefactClassifier
from dfat.ai_engine.triage.summarizer import InvestigativeSummarizer
from dfat.ai_engine.validation.hallucination_guard import HallucinationGuard


@pytest.mark.asyncio
async def test_cache_distinguishes_hit_miss_and_temperature() -> None:
    # Arrange
    cache = AIResponseCache()
    response = LLMResponse(text="answer", model="llama3")
    await cache.put("prompt", "llama3", 0.1, response)

    # Act
    hit = await cache.get("prompt", "llama3", 0.1)
    missing_prompt = await cache.get("other", "llama3", 0.1)
    missing_temperature = await cache.get("prompt", "llama3", 0.2)
    stats = await cache.get_stats()

    # Assert
    assert hit is not None and hit.response.text == "answer"
    assert missing_prompt is missing_temperature is None
    assert stats.total_hits == 1
    assert stats.total_misses == 2


def test_hallucination_guard_empty_text_is_low_risk() -> None:
    # Arrange
    guard = HallucinationGuard({"art-1"}, {"event_log"}, {"low", "high"})

    # Act
    result = guard.check_response("")

    # Assert
    assert result.risk_level == "low"
    assert result.hallucinated_ids == result.fabricated_terms == []
    assert result.clean_response == ""


def test_hallucination_guard_flags_fabricated_category_and_id() -> None:
    # Arrange
    guard = HallucinationGuard({"art-1"}, {"event_log"}, {"low", "high"})

    # Act
    result = guard.check_response(
        "Artefact art-made-up belongs to malware_signature."
    )

    # Assert
    assert "art-made-up" in result.hallucinated_ids
    assert "malware_signature" in result.fabricated_terms
    assert result.risk_level in {"medium", "high"}


def test_classifier_empty_artefact_list_does_not_call_llm() -> None:
    # Arrange
    llm = MagicMock()
    classifier = ArtefactClassifier(llm)

    # Act / Assert
    assert classifier.classify([]) == []
    llm.is_available.assert_not_called()


def test_summarizer_empty_model_response_returns_safe_placeholder() -> None:
    # Arrange
    llm = MagicMock()
    llm.summarize.return_value = ""
    summarizer = InvestigativeSummarizer(llm)

    # Act
    result = summarizer.generate_summary([])

    # Assert
    assert result == "Summary unavailable: empty model response."


def test_summary_response_validator_handles_empty_text() -> None:
    # Act
    result = SummaryResponseValidator().validate("")

    # Assert
    assert result["executive_summary"] == ""
    assert result["key_findings"] == []
    assert result["iocs_identified"] == []
    assert result["confidence_score"] == 0.2
