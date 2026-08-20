"""Integration tests for RAG-augmented pipeline analysis."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.knowledge.rag.context_builder import RAGContextBuilder
from dfat.knowledge.rag.rag_analyzer import RAGEnhancedAnalyzer
from dfat.knowledge.rag.rag_prompts import RAGPromptTemplates
from dfat.knowledge.retriever import RetrievalResult


def _artefacts() -> list[Artefact]:
    return [
        Artefact(
            artefact_id="art-rag-1",
            category=ArtefactCategory.RUNNING_PROCESS,
            source_evidence_id="ev-rag",
            raw_data={"name": "cmd.exe", "CommandLine": "cmd.exe /c mimikatz"},
        )
    ]


def _ranked() -> list[RankedArtefact]:
    return [
        RankedArtefact(
            artefact_id="art-rag-1",
            category=ArtefactCategory.RUNNING_PROCESS,
            source_evidence_id="ev-rag",
            raw_data={"name": "cmd.exe"},
            suspicion_level=SuspicionLevel.HIGH,
            relevance_score=0.9,
            classification_reasoning="Suspicious process",
        )
    ]


@pytest.mark.asyncio
async def test_context_builder_includes_retrieval_hits() -> None:
    retriever = AsyncMock()
    retriever.retrieve_for_artefact = AsyncMock(
        return_value=RetrievalResult(
            query="cmd.exe mimikatz",
            total_results=1,
            vector_results=[{"content": "Known credential dumping tool", "score": 0.9}],
            ioc_matches=[],
            sources_queried=["artefacts", "iocs"],
            retrieval_time_ms=1.0,
        )
    )
    truncator = MagicMock()
    truncator.truncate = MagicMock(side_effect=lambda text, **kwargs: text)
    builder = RAGContextBuilder(retriever, truncator)
    context, sources = await builder.build_classification_context_with_sources(_artefacts())
    assert context
    assert isinstance(sources, list)


@pytest.mark.asyncio
async def test_rag_analyzer_annotates_output_with_sources() -> None:
    llm = MagicMock()
    llm.is_available = MagicMock(return_value=True)
    llm.analyzer_name = "LocalLLM"
    llm.analyze_async = AsyncMock(return_value=_ranked())
    llm._classifier = MagicMock()
    llm._classifier._prompt_builder = MagicMock()
    llm._classifier._prompt_builder._templates = MagicMock()
    context_builder = AsyncMock()
    context_builder.build_classification_context_with_sources = AsyncMock(
        return_value=("Known malware context from dataset-a", ["dataset-a"])
    )
    audit = AsyncMock()
    audit.log_action = AsyncMock()
    analyzer = RAGEnhancedAnalyzer(llm, context_builder, RAGPromptTemplates(), audit)

    ranked = await analyzer.analyze_async(
        ArtefactSet(
            evidence_id="ev-rag",
            artefacts=_artefacts(),
            categories_present=[ArtefactCategory.RUNNING_PROCESS],
        )
    )

    assert "[rag_sources: dataset-a]" in ranked[0].classification_reasoning


@pytest.mark.asyncio
async def test_rag_analyzer_without_context_uses_plain_llm() -> None:
    llm = MagicMock()
    llm.is_available = MagicMock(return_value=True)
    llm.analyzer_name = "LocalLLM"
    llm.analyze_async = AsyncMock(return_value=_ranked())
    context_builder = AsyncMock()
    context_builder.build_classification_context_with_sources = AsyncMock(return_value=("", []))
    audit = AsyncMock()
    audit.log_action = AsyncMock()
    analyzer = RAGEnhancedAnalyzer(llm, context_builder, RAGPromptTemplates(), audit)

    await analyzer.analyze_async(
        ArtefactSet(
            evidence_id="ev-rag",
            artefacts=_artefacts(),
            categories_present=[ArtefactCategory.RUNNING_PROCESS],
        )
    )

    llm.analyze_async.assert_awaited_once()
    details = audit.log_action.await_args.kwargs.get("details") or audit.log_action.await_args.args[4]
    assert details["rag_used"] is False
