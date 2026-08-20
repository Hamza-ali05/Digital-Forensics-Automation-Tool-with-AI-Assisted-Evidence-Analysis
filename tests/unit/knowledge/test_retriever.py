"""Unit tests for UnifiedRetriever."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact
from dfat.knowledge.ioc_database import IOCEntry
from dfat.knowledge.retriever import UnifiedRetriever
from dfat.knowledge.vector_store import QueryResult


@pytest.fixture
def retriever() -> UnifiedRetriever:
    vector_store = AsyncMock()
    vector_store.query = AsyncMock(
        return_value=QueryResult(
            query="malware",
            documents=["known malware family"],
            metadatas=[{"source": "dataset-a"}],
            ids=["doc-1"],
            distances=[0.2],
        )
    )
    ioc_db = AsyncMock()
    ioc_db.search = AsyncMock(
        return_value=[
            IOCEntry(
                ioc_id="ioc-1",
                ioc_type="hash",
                value="abc123",
                source_dataset="dataset-a",
                confidence="high",
            )
        ]
    )
    ioc_db.lookup_hash = AsyncMock(return_value=None)
    ioc_db.lookup_ip = AsyncMock(return_value=None)
    ioc_db.lookup_domain = AsyncMock(return_value=None)
    graph = MagicMock()
    graph.graph = MagicMock()
    graph.graph.nodes = MagicMock(return_value=[])
    graph.query_related = MagicMock(return_value=[])
    engine = MagicMock()
    return UnifiedRetriever(vector_store, ioc_db, graph, engine)


@pytest.mark.asyncio
async def test_retrieve_merges_vector_and_ioc_sources(retriever: UnifiedRetriever) -> None:
    result = await retriever.retrieve("malware cmd.exe", max_results=5)
    assert result.total_results >= 1
    assert "iocs" in result.sources_queried
    assert result.retrieval_time_ms >= 0


@pytest.mark.asyncio
async def test_retrieve_for_artefact_uses_serialized_content(retriever: UnifiedRetriever) -> None:
    artefact = Artefact(
        artefact_id="art-1",
        category=ArtefactCategory.RUNNING_PROCESS,
        source_evidence_id="ev-1",
        raw_data={"name": "cmd.exe", "CommandLine": "cmd.exe /c malware"},
    )
    result = await retriever.retrieve_for_artefact(artefact)
    assert result.query
    retriever._vector_store.query.assert_awaited()


@pytest.mark.asyncio
async def test_vector_query_failure_returns_empty_list(retriever: UnifiedRetriever) -> None:
    retriever._vector_store.query = AsyncMock(side_effect=RuntimeError("vector offline"))
    result = await retriever.retrieve("test query", sources=["vector"], max_results=3)
    assert result.vector_results == []
