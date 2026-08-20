"""Unit tests for ForensicVectorStore."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dfat.knowledge.vector_store import ForensicVectorStore, QueryResult


@pytest.fixture
def vector_store(tmp_path) -> ForensicVectorStore:
    engine = MagicMock()
    engine.embed_batch.return_value = [[0.0] * 384]
    engine.embed_text.return_value = [0.0] * 384
    return ForensicVectorStore(tmp_path / "chroma", embedding_engine=engine)


@pytest.mark.asyncio
async def test_add_documents_requires_matching_lengths(vector_store: ForensicVectorStore) -> None:
    with pytest.raises(ValueError):
        await vector_store.add_documents(
            "artefacts",
            documents=["one"],
            metadatas=[{}, {}],
            ids=["a"],
        )


@pytest.mark.asyncio
async def test_add_documents_calls_sync_add(vector_store: ForensicVectorStore) -> None:
    with patch.object(vector_store, "_add_documents_sync") as sync_add:
        await vector_store.add_documents(
            "artefacts",
            documents=["malware sample"],
            metadatas=[{"source": "dataset-a"}],
            ids=["doc-1"],
        )
    sync_add.assert_called_once()


@pytest.mark.asyncio
async def test_query_returns_query_result(vector_store: ForensicVectorStore) -> None:
    expected = QueryResult(
        query="",
        collection="artefacts",
        documents=["malware indicator"],
        metadatas=[{"source": "dataset-a"}],
        ids=["doc-1"],
        distances=[0.12],
    )
    with patch.object(vector_store, "_query_sync", return_value=expected):
        result = await vector_store.query("artefacts", "cmd.exe malware", n_results=1)
    assert result.query == "cmd.exe malware"
    assert result.documents == ["malware indicator"]


@pytest.mark.asyncio
async def test_get_collection_stats_reports_count(vector_store: ForensicVectorStore) -> None:
    with patch.object(
        vector_store,
        "_get_collection_stats_sync",
        return_value={"name": "artefacts", "description": "x", "count": 2},
    ):
        stats = await vector_store.get_collection_stats("artefacts")
    assert stats["count"] == 2
