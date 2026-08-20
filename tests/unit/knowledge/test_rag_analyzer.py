"""Unit tests for RAGEnhancedAnalyzer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.artefact import RankedArtefact
from dfat.knowledge.rag.rag_analyzer import RAGEnhancedAnalyzer
from dfat.knowledge.rag.rag_prompts import RAGPromptTemplates


def _artefact_set() -> ArtefactSet:
    return ArtefactSet(
        evidence_id="ev-1",
        artefacts=[
            Artefact(
                artefact_id="art-1",
                category=ArtefactCategory.RUNNING_PROCESS,
                source_evidence_id="ev-1",
                raw_data={"name": "cmd.exe"},
            )
        ],
        categories_present=[ArtefactCategory.RUNNING_PROCESS],
    )


def _ranked() -> list[RankedArtefact]:
    return [
        RankedArtefact(
            artefact_id="art-1",
            category=ArtefactCategory.RUNNING_PROCESS,
            source_evidence_id="ev-1",
            raw_data={"name": "cmd.exe"},
            suspicion_level=SuspicionLevel.MEDIUM,
            relevance_score=0.6,
        )
    ]


@pytest.fixture
def analyzer() -> RAGEnhancedAnalyzer:
    llm = MagicMock()
    llm.is_available = MagicMock(return_value=True)
    llm.analyzer_name = "LocalLLM"
    llm.analyze_async = AsyncMock(return_value=_ranked())
    llm.summarize_async = AsyncMock(return_value="Summary text")
    llm._classifier = MagicMock()
    llm._classifier._prompt_builder = MagicMock()
    llm._classifier._prompt_builder._templates = MagicMock()
    llm._summarizer = MagicMock()
    llm._summarizer._prompt_builder = MagicMock()
    llm._summarizer._prompt_builder._templates = MagicMock()
    context_builder = AsyncMock()
    context_builder.build_classification_context_with_sources = AsyncMock(
        return_value=("Known malware family context", ["dataset-a"])
    )
    context_builder.build_summary_context = AsyncMock(return_value=("summary context", ["dataset-a"]))
    audit = AsyncMock()
    audit.log_action = AsyncMock()
    return RAGEnhancedAnalyzer(llm, context_builder, RAGPromptTemplates(), audit)


@pytest.mark.asyncio
async def test_analyze_uses_rag_context_when_available(analyzer: RAGEnhancedAnalyzer) -> None:
    ranked = await analyzer.analyze_async(_artefact_set())
    assert len(ranked) == 1
    analyzer._audit.log_action.assert_awaited()
    details = analyzer._audit.log_action.await_args.kwargs.get("details") or analyzer._audit.log_action.await_args.args[4]
    assert details["rag_used"] is True
    assert "dataset-a" in details["contributing_datasets"]


@pytest.mark.asyncio
async def test_analyze_falls_back_when_context_empty(analyzer: RAGEnhancedAnalyzer) -> None:
    analyzer._context_builder.build_classification_context_with_sources = AsyncMock(
        return_value=("", [])
    )
    ranked = await analyzer.analyze_async(_artefact_set())
    assert len(ranked) == 1
    details = analyzer._audit.log_action.await_args.kwargs.get("details") or analyzer._audit.log_action.await_args.args[4]
    assert details["rag_used"] is False
    assert details["reason"] == "empty_knowledge_base"


@pytest.mark.asyncio
async def test_analyze_falls_back_to_rules_when_llm_unavailable(analyzer: RAGEnhancedAnalyzer) -> None:
    analyzer.llm_client.is_available = MagicMock(return_value=False)
    ranked = await analyzer.analyze_async(_artefact_set())
    assert len(ranked) >= 1
    details = analyzer._audit.log_action.await_args.kwargs.get("details") or analyzer._audit.log_action.await_args.args[4]
    assert details["reason"] == "llm_unavailable"


def test_is_available_delegates_to_llm_client(analyzer: RAGEnhancedAnalyzer) -> None:
    assert analyzer.is_available() is True
    analyzer.llm_client.is_available.return_value = False
    assert analyzer.is_available() is False
