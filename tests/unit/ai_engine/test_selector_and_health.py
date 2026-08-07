"""Extra coverage for connection health, analyser selection, and sync wrappers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from dfat.ai_engine.analyzer import LocalLLMClient
from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.connection import LLMConnectionManager, LLMHealthStatus
from dfat.ai_engine.selector import select_analyzer
from dfat.ai_engine.summarization.narrative import FormattedNarrative
from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.core.enums import SuspicionLevel
from dfat.core.models.artefact import ArtefactSet, RankedArtefact


@pytest.mark.asyncio
async def test_connection_health_healthy(mock_audit_logger: MagicMock) -> None:
    """Verify check_health reports model availability from /api/tags."""
    config = LLMConfig(
        api_url="http://127.0.0.1:11434",
        model="llama3",
        max_retries=1,
        retry_delay_seconds=0.0,
    )
    manager = LLMConnectionManager(config, mock_audit_logger)
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"models": [{"name": "llama3:latest"}]}
    response.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("dfat.ai_engine.llm.connection.httpx.AsyncClient", return_value=mock_client):
        status = await manager.check_health()
    assert status.is_healthy is True
    assert status.model_loaded is True
    assert status.model_name == "llama3"


@pytest.mark.asyncio
async def test_connection_health_unreachable(mock_audit_logger: MagicMock) -> None:
    """Verify check_health never raises and reports unhealthy on errors."""
    config = LLMConfig(
        api_url="http://127.0.0.1:11434",
        model="llama3",
        max_retries=1,
        retry_delay_seconds=0.0,
    )
    manager = LLMConnectionManager(config, mock_audit_logger)
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=httpx.ConnectError("down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("dfat.ai_engine.llm.connection.httpx.AsyncClient", return_value=mock_client):
        status = await manager.check_health()
    assert status.is_healthy is False
    assert status.error


def test_select_analyzer_prefers_llm_when_available() -> None:
    """Verify selector returns the LLM client when healthy."""
    llm = MagicMock()
    llm.is_available.return_value = True
    fallback = RuleBasedAnalyzer()
    assert select_analyzer(llm, fallback, enable_fallback=True) is llm


def test_select_analyzer_falls_back_when_unavailable() -> None:
    """Verify selector returns rule-based fallback when LLM is down."""
    llm = MagicMock()
    llm.is_available.return_value = False
    fallback = RuleBasedAnalyzer()
    assert select_analyzer(llm, fallback, enable_fallback=True) is fallback


def test_select_analyzer_keeps_llm_when_fallback_disabled() -> None:
    """Verify selector keeps the LLM client when fallback is disabled."""
    llm = MagicMock()
    llm.is_available.return_value = False
    fallback = RuleBasedAnalyzer()
    assert select_analyzer(llm, fallback, enable_fallback=False) is llm


def test_local_llm_sync_wrappers(sample_artefact_set: ArtefactSet) -> None:
    """Exercise sync analyze/summarize wrappers with mocked async pipeline."""
    base = sample_artefact_set.artefacts[0]
    ranked = [
        RankedArtefact(
            **base.model_dump(),
            suspicion_level=SuspicionLevel.HIGH,
            relevance_score=0.9,
        )
    ]
    config = LLMConfig(api_url="http://127.0.0.1:11434", model="llama3")
    connection = MagicMock()
    connection.check_health = AsyncMock(
        return_value=LLMHealthStatus(
            is_healthy=True,
            model_loaded=True,
            model_name="llama3",
            response_time_ms=1.0,
        )
    )
    monitor = MagicMock()
    monitor.log_llm_request = AsyncMock(return_value="req")
    monitor.log_llm_response = AsyncMock()
    monitor.log_classification = AsyncMock()
    monitor.log_summarization = AsyncMock()
    monitor.log_hallucination_detected = AsyncMock()
    validation = MagicMock()
    validation.hallucination_report = None
    validator = MagicMock()
    validator.validate_classification.return_value = validation
    validator.validate_summary.return_value = validation
    classifier = MagicMock()
    classifier.classify = AsyncMock(return_value=[])
    ranker = MagicMock()
    ranker.rank = AsyncMock(return_value=ranked)
    summarizer = MagicMock()
    summarizer.generate_summary = AsyncMock(
        return_value=SummaryResult(
            full_text="summary",
            executive_summary="summary",
            model_used="llama3",
            prompt_version="1.0.0",
            confidence_score=0.7,
        )
    )
    narrative = MagicMock()
    narrative.format_narrative.return_value = FormattedNarrative(
        full_text="summary narrative",
        sections={},
        disclaimer="disclaimer",
        word_count=2,
        model_used="llama3",
        confidence_score=0.7,
    )
    client = LocalLLMClient(
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
    assert client.analyze(sample_artefact_set) == ranked
    assert "summary" in client.summarize(ranked)

