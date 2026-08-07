"""Integration tests for AI triage flow with mocked LLM (Prompt 5.20)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dfat.ai_engine.classification import (
    ClassificationPromptBuilder,
    ClassificationResponseParser,
    DefaultConfidenceScorer,
    LLMArtefactClassifier,
)
from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.ai_engine.llm.client import LLMResponse
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.connection import LLMHealthStatus
from dfat.ai_engine.llm.prompts import ForensicPromptTemplates
from dfat.ai_engine.preprocessing import ArtefactBatcher, ArtefactSerializer
from dfat.ai_engine.ranking import (
    LLMRelevanceRanker,
    RankingPromptBuilder,
    RankingResponseParser,
)
from dfat.ai_engine.summarization import (
    LLMInvestigativeSummarizer,
    SummarizationPromptBuilder,
    SummaryResponseValidator,
)
from dfat.core.enums import SuspicionLevel
from dfat.core.models.artefact import ArtefactSet


def _classification_json(artefact_set: ArtefactSet) -> str:
    items = []
    for artefact in artefact_set.artefacts[:5]:
        items.append(
            "{"
            f'"artefact_id":"{artefact.artefact_id}",'
            '"suspicion_level":"HIGH",'
            '"reasoning":"Mock classification",'
            '"ioc_indicators":[]'
            "}"
        )
    return "[" + ",".join(items) + "]"


def _ranking_json(artefact_set: ArtefactSet) -> str:
    items = []
    for artefact in artefact_set.artefacts[:5]:
        items.append(
            "{"
            f'"artefact_id":"{artefact.artefact_id}",'
            '"relevance_score":0.8,'
            '"priority_reasoning":"Mock rank"'
            "}"
        )
    return "[" + ",".join(items) + "]"


_SUMMARY = """
1. EXECUTIVE SUMMARY
Mock triage indicates elevated activity [UNCERTAIN].

2. KEY FINDINGS
- HIGH findings present in mock evidence

3. TIMELINE OF EVENTS
Mock timeline unavailable.

4. INDICATORS OF COMPROMISE
- Mock IOC

5. RECOMMENDED NEXT STEPS
- Validate against structured JSON
"""


@pytest.mark.asyncio
async def test_full_ai_flow_with_mock_llm(
    mock_artefact_set_for_ai: ArtefactSet,
    mock_audit_logger: MagicMock,
) -> None:
    """Classify → rank → summarize using a mocked OllamaClient."""
    artefacts = list(mock_artefact_set_for_ai.artefacts[:5])
    subset = ArtefactSet(
        evidence_id=mock_artefact_set_for_ai.evidence_id,
        artefacts=artefacts,
        categories_present=sorted({a.category for a in artefacts}, key=lambda c: c.value),
    )
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        side_effect=[
            LLMResponse(text=_classification_json(subset), model="llama3"),
            LLMResponse(text=_ranking_json(subset), model="llama3"),
            LLMResponse(text=_SUMMARY, model="llama3"),
        ]
    )
    serializer = ArtefactSerializer()
    classifier = LLMArtefactClassifier(
        ollama_client=ollama,
        prompt_builder=ClassificationPromptBuilder(
            templates=ForensicPromptTemplates(),
            serializer=serializer,
            batcher=ArtefactBatcher(max_tokens_per_batch=8000, serializer=serializer),
        ),
        response_parser=ClassificationResponseParser(),
        confidence_scorer=DefaultConfidenceScorer(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(),
    )
    ranker = LLMRelevanceRanker(
        ollama_client=ollama,
        prompt_builder=RankingPromptBuilder(),
        response_parser=RankingResponseParser(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(),
    )
    summarizer = LLMInvestigativeSummarizer(
        ollama_client=ollama,
        prompt_builder=SummarizationPromptBuilder(),
        response_validator=SummaryResponseValidator(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(),
    )

    classified = await classifier.classify(artefacts)
    assert classified
    assert all(item.suspicion_level is SuspicionLevel.HIGH for item in classified)

    ranked = await ranker.rank(classified, artefacts, rule_based_scores=None)
    assert ranked
    assert all(item.relevance_score >= 0.0 for item in ranked)

    summary = await summarizer.generate_summary(ranked)
    assert summary.full_text
    assert summary.executive_summary
    assert ollama.generate.await_count == 3


def test_fallback_when_llm_unavailable(
    mock_artefact_set_for_ai: ArtefactSet,
) -> None:
    """Verify rule-based fallback works without any LLM dependency."""
    analyzer = RuleBasedAnalyzer()
    assert analyzer.is_available() is True
    ranked = analyzer.analyze(mock_artefact_set_for_ai)
    assert len(ranked) == mock_artefact_set_for_ai.total_count
    summary = analyzer.summarize(ranked)
    assert isinstance(summary, str) and summary


def test_ai_api_endpoints(app_client: TestClient) -> None:
    """Verify AI health endpoint is reachable without authentication."""
    healthy = LLMHealthStatus(
        is_healthy=True,
        model_loaded=True,
        model_name="llama3",
        response_time_ms=1.0,
        checked_at=datetime.now(UTC),
    )
    with patch(
        "dfat.ai_engine.llm.connection.LLMConnectionManager.check_health",
        new=AsyncMock(return_value=healthy),
    ):
        response = app_client.get("/api/v1/ai/health")
    assert response.status_code == 200
    assert response.json()["is_healthy"] is True

