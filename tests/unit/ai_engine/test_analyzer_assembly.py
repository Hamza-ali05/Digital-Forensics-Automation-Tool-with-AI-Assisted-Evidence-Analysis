"""Acceptance tests for Prompt 5.18 LocalLLMClient assembly and fallback."""

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
from dfat.core.interfaces.analyzer import IArtefactAnalyzer
from dfat.core.models.artefact import ArtefactSet, RankedArtefact


def _assembled_client(
    *,
    healthy: bool = True,
    ranked: list[RankedArtefact] | None = None,
    summary_text: str = "Investigative narrative.",
) -> LocalLLMClient:
    """Build a LocalLLMClient with mocked collaborators."""
    config = LLMConfig(
        api_url="http://127.0.0.1:11434/api/generate",
        model="llama3",
    )
    connection = MagicMock()
    connection.check_health = AsyncMock(
        return_value=LLMHealthStatus(
            is_healthy=healthy,
            model_loaded=healthy,
            model_name="llama3",
            response_time_ms=1.0,
            error=None if healthy else "down",
        )
    )
    monitor = MagicMock()
    monitor.log_llm_request = AsyncMock(return_value="req-1")
    monitor.log_llm_response = AsyncMock()
    monitor.log_classification = AsyncMock()
    monitor.log_summarization = AsyncMock()
    monitor.log_hallucination_detected = AsyncMock()

    classifier = MagicMock()
    classifier.classify = AsyncMock(return_value=[])
    validator = MagicMock()
    validation = MagicMock()
    validation.hallucination_report = None
    validator.validate_classification.return_value = validation
    validator.validate_summary.return_value = validation

    ranker = MagicMock()
    ranker.rank = AsyncMock(return_value=ranked or [])

    summarizer = MagicMock()
    summarizer.generate_summary = AsyncMock(
        return_value=SummaryResult(
            full_text=summary_text,
            executive_summary=summary_text,
            model_used="llama3",
            prompt_version="test",
            confidence_score=0.8,
        )
    )
    narrative = MagicMock()
    narrative.format_narrative.return_value = FormattedNarrative(
        full_text=summary_text,
        sections={},
        disclaimer="Advisory only.",
        word_count=len(summary_text.split()),
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


def test_local_llm_client_is_iartefact_analyzer() -> None:
    """Verify assembled client implements the Prompt 1 analyser port."""
    client = _assembled_client()
    assert isinstance(client, IArtefactAnalyzer)
    assert client.analyzer_name == "LocalLLaMA3Client"


def test_local_llm_client_docstring_acknowledges_sharma_limitation() -> None:
    """Verify docstring documents base LLaMA-3 vs ForensicLLM limitation."""
    doc = LocalLLMClient.__doc__ or ""
    assert "Sharma et al., 2025" in doc
    assert "ForensicLLM" in doc


def test_rule_based_analyzer_always_available() -> None:
    """Verify rule-based fallback reports availability unconditionally."""
    assert RuleBasedAnalyzer().is_available() is True
    assert isinstance(RuleBasedAnalyzer(), IArtefactAnalyzer)


def test_rule_based_analyze_and_summarize(sample_artefact_set: ArtefactSet) -> None:
    """Verify fallback analyze/summarize produce RankedArtefact and text."""
    analyzer = RuleBasedAnalyzer()
    ranked = analyzer.analyze(sample_artefact_set)
    assert ranked
    assert all(isinstance(item, RankedArtefact) for item in ranked)
    summary = analyzer.summarize(ranked)
    assert isinstance(summary, str)
    assert len(summary) > 0


@pytest.mark.asyncio
async def test_assembled_analyze_returns_ranked(
    sample_artefact_set: ArtefactSet,
) -> None:
    """Verify analyze_async returns RankedArtefact list when LLM is healthy."""
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


@pytest.mark.asyncio
async def test_assembled_summarize_returns_non_empty(
    sample_artefact_set: ArtefactSet,
) -> None:
    """Verify summarize_async returns a non-empty narrative string."""
    analyzer = RuleBasedAnalyzer()
    ranked = analyzer.analyze(sample_artefact_set)
    client = _assembled_client(summary_text="Case narrative with findings.")
    text = await client.summarize_async(ranked)
    assert isinstance(text, str)
    assert len(text) > 0
