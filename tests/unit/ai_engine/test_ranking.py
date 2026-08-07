"""Unit tests for LLM relevance ranking (Prompt 5.7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.llm.client import LLMResponse
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.ranking import (
    LLMRelevanceRanker,
    RankingPromptBuilder,
    RankingResponseParser,
)
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact


def _artefact(artefact_id: str) -> Artefact:
    return Artefact(
        artefact_id=artefact_id,
        category=ArtefactCategory.INJECTED_CODE,
        source_evidence_id="ev-1",
        raw_data={"pid": 1, "name": artefact_id},
    )


def _classified(
    artefact_id: str,
    level: SuspicionLevel,
) -> ClassificationResult:
    return ClassificationResult(
        artefact_id=artefact_id,
        suspicion_level=level,
        reasoning=f"Classified {artefact_id}",
        confidence=0.8,
    )


@pytest.mark.asyncio
async def test_weighted_average_prefers_rule_based(
    mock_audit_logger: MagicMock,
) -> None:
    # llm=1.0, rule=0.0 → 0.4*1 + 0.6*0 = 0.4
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(
            text='[{"artefact_id":"a1","relevance_score":1.0,"priority_reasoning":"LLM high"}]',
            model="llama3",
        )
    )
    ranker = LLMRelevanceRanker(
        ollama_client=ollama,
        prompt_builder=RankingPromptBuilder(),
        response_parser=RankingResponseParser(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(),
    )
    ranked = await ranker.rank(
        classified=[_classified("a1", SuspicionLevel.HIGH)],
        artefacts=[_artefact("a1")],
        rule_based_scores={"a1": 0.0},
    )
    assert len(ranked) == 1
    assert ranked[0].relevance_score == pytest.approx(0.4)
    details = mock_audit_logger.log_action.call_args.kwargs["details"]
    assert details["rule_weight"] == 0.6
    assert details["llm_weight"] == 0.4


@pytest.mark.asyncio
async def test_missing_llm_score_falls_back_to_rule_only(
    mock_audit_logger: MagicMock,
) -> None:
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(text="[]", model="llama3")
    )
    ranker = LLMRelevanceRanker(
        ollama_client=ollama,
        prompt_builder=RankingPromptBuilder(),
        response_parser=RankingResponseParser(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(),
    )
    ranked = await ranker.rank(
        classified=[_classified("a1", SuspicionLevel.MEDIUM)],
        artefacts=[_artefact("a1")],
        rule_based_scores={"a1": 0.75},
    )
    assert ranked[0].relevance_score == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_sorted_by_suspicion_then_score(
    mock_audit_logger: MagicMock,
) -> None:
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=LLMResponse(
            text=(
                "["
                '{"artefact_id":"low","relevance_score":0.99,"priority_reasoning":"x"},'
                '{"artefact_id":"crit","relevance_score":0.2,"priority_reasoning":"y"},'
                '{"artefact_id":"high","relevance_score":0.5,"priority_reasoning":"z"}'
                "]"
            ),
            model="llama3",
        )
    )
    ranker = LLMRelevanceRanker(
        ollama_client=ollama,
        prompt_builder=RankingPromptBuilder(),
        response_parser=RankingResponseParser(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(),
    )
    ranked = await ranker.rank(
        classified=[
            _classified("low", SuspicionLevel.LOW),
            _classified("crit", SuspicionLevel.CRITICAL),
            _classified("high", SuspicionLevel.HIGH),
        ],
        artefacts=[_artefact("low"), _artefact("crit"), _artefact("high")],
        rule_based_scores=None,
    )
    assert [item.artefact_id for item in ranked] == ["crit", "high", "low"]
    assert "Classified crit" in (ranked[0].classification_reasoning or "")
    assert "y" in (ranked[0].classification_reasoning or "")


@pytest.mark.asyncio
async def test_ranking_weighted_average(mock_audit_logger: MagicMock) -> None:
    """Alias for weighted LLM/rule score merge."""
    await test_weighted_average_prefers_rule_based(mock_audit_logger)


@pytest.mark.asyncio
async def test_ranking_sort_order(mock_audit_logger: MagicMock) -> None:
    """Alias for suspicion-then-score sort order."""
    await test_sorted_by_suspicion_then_score(mock_audit_logger)


@pytest.mark.asyncio
async def test_ranking_handles_missing_llm_scores(
    mock_audit_logger: MagicMock,
) -> None:
    """Alias for missing LLM score → rule-only score."""
    await test_missing_llm_score_falls_back_to_rule_only(mock_audit_logger)


@pytest.mark.asyncio
async def test_ranking_fallback_to_rule_based_only(
    mock_audit_logger: MagicMock,
) -> None:
    """Verify LLM generate failures fall back to rule-based scores only."""
    ollama = MagicMock()
    ollama.generate = AsyncMock(side_effect=RuntimeError("ollama down"))
    ranker = LLMRelevanceRanker(
        ollama_client=ollama,
        prompt_builder=RankingPromptBuilder(),
        response_parser=RankingResponseParser(),
        audit_logger=mock_audit_logger,
        config=LLMConfig(),
    )
    ranked = await ranker.rank(
        classified=[_classified("a1", SuspicionLevel.HIGH)],
        artefacts=[_artefact("a1")],
        rule_based_scores={"a1": 0.85},
    )
    assert ranked[0].relevance_score == pytest.approx(0.85)
