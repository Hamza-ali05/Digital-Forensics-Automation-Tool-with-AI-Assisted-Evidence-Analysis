"""Unit tests for assembled LocalLLMClient and rule-based fallback (Prompt 5.20)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.analyzer import LocalLLMClient
from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.connection import LLMHealthStatus
from dfat.ai_engine.summarization.narrative import FormattedNarrative
from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.core.enums import SuspicionLevel
from dfat.core.exceptions import LLMConnectionError
from dfat.core.interfaces.analyzer import IArtefactAnalyzer
from dfat.core.models.artefact import ArtefactSet, RankedArtefact


def _assembled_client(
    *,
    healthy: bool = True,
    ranked: list[RankedArtefact] | None = None,
    summary_text: str = "Investigative narrative.",
) -> LocalLLMClient:
    config = LLMConfig(api_url="http://127.0.0.1:11434", model="llama3")
    connection = MagicMock()
    connection.check_health = AsyncMock(
        return_value=LLMHealthStatus(
            is_healthy=healthy,
            model_loaded=healthy,
            model_name="llama3",
            response_time_ms=1.0,
        )
    )
    monitor = MagicMock()
    monitor.log_llm_request = AsyncMock(return_value="req-1")
    monitor.log_llm_response = AsyncMock()
    monitor.log_classification = AsyncMock()
    monitor.log_summarization = AsyncMock()
    monitor.log_hallucination_detected = AsyncMock()

    validator = MagicMock()
    validation = MagicMock()
    validation.hallucination_report = None
    validator.validate_classification.return_value = validation
    validator.validate_summary.return_value = validation

    classifier = MagicMock()
    classifier.classify = AsyncMock(return_value=[])
    ranker = MagicMock()
    ranker.rank = AsyncMock(return_value=ranked or [])
    summarizer = MagicMock()
    summarizer.generate_summary = AsyncMock(
        return_value=SummaryResult(
            full_text=summary_text,
            executive_summary=summary_text,
            model_used="llama3",
            prompt_version="1.0.0",
            confidence_score=0.8,
        )
    )
    narrative = MagicMock()
    narrative.format_narrative.return_value = FormattedNarrative(
        full_text=summary_text,
        sections={},
        disclaimer="Advisory only.",
        word_count=3,
        model_used="llama3",
        confidence_score=0.8,
    )
    return LocalLLMClient(
        config=config,
        ollama_client=MagicMock(),
        connection_manager=connection,
        classifier=classifier,
        ranker=ranker,
        summarizer=summarizer,
        validator=validator,
        cache=MagicMock(),
        monitor=monitor,
        audit_logger=MagicMock(),
        narrative_formatter=narrative,
    )


def test_local_llm_client_implements_interface() -> None:
    """Verify LocalLLMClient is an IArtefactAnalyzer."""
    client = _assembled_client()
    assert isinstance(client, IArtefactAnalyzer)
    assert client.analyzer_name == "LocalLLaMA3Client"


@pytest.mark.asyncio
async def test_analyze_returns_ranked_artefacts(
    sample_artefact_set: ArtefactSet,
) -> None:
    """Verify analyze_async returns RankedArtefact objects."""
    base = sample_artefact_set.artefacts[0]
    expected = [
        RankedArtefact(
            **base.model_dump(),
            suspicion_level=SuspicionLevel.HIGH,
            relevance_score=0.9,
            classification_reasoning="test",
        )
    ]
    client = _assembled_client(ranked=expected)
    ranked = await client.analyze_async(sample_artefact_set)
    assert ranked == expected
    assert all(isinstance(item, RankedArtefact) for item in ranked)


@pytest.mark.asyncio
async def test_summarize_returns_narrative(
    sample_artefact_set: ArtefactSet,
) -> None:
    """Verify summarize_async returns a non-empty narrative string."""
    ranked = RuleBasedAnalyzer().analyze(sample_artefact_set)
    client = _assembled_client(summary_text="Case narrative with findings.")
    text = await client.summarize_async(ranked)
    assert isinstance(text, str)
    assert len(text) > 0


@pytest.mark.asyncio
async def test_unavailable_raises_connection_error(
    sample_artefact_set: ArtefactSet,
) -> None:
    """Verify analyze_async raises when the local LLM is unhealthy."""
    client = _assembled_client(healthy=False)
    with pytest.raises(LLMConnectionError):
        await client.analyze_async(sample_artefact_set)


def test_rule_based_fallback_always_available() -> None:
    """Verify rule-based fallback reports availability unconditionally."""
    analyzer = RuleBasedAnalyzer()
    assert analyzer.is_available() is True
    assert isinstance(analyzer, IArtefactAnalyzer)
