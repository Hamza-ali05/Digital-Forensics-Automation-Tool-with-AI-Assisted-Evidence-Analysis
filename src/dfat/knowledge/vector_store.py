"""ChromaDB-backed vector store for local forensic knowledge retrieval."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.knowledge.embeddings import LocalEmbeddingEngine

try:
    import chromadb
    from chromadb.api.models.Collection import Collection
except Exception:  # noqa: BLE001 — optional dependency
    chromadb = None  # type: ignore[assignment]
    Collection = Any  # type: ignore[misc,assignment]


class QueryResult(BaseModel):
    """Vector similarity search results from a forensic knowledge collection."""

    model_config = ConfigDict(validate_assignment=True)

    documents: list[str] = Field(default_factory=list)
    metadatas: list[dict[str, Any]] = Field(default_factory=list)
    distances: list[float] = Field(default_factory=list)
    ids: list[str] = Field(default_factory=list)
    query: str = ""
    collection: str = ""


class ForensicVectorStore:
    """ChromaDB-backed vector store for forensic knowledge retrieval."""

    COLLECTIONS: dict[str, str] = {
        "artefacts": "Forensic artefact embeddings from pipeline executions",
        "knowledge": "Forensic knowledge base from datasets and documentation",
        "iocs": "Indicators of compromise embeddings",
        "threat_intel": "Threat intelligence feed embeddings",
        "benchmark": "Benchmark ground truth embeddings",
    }

    def __init__(
        self,
        persist_path: Path,
        embedding_engine: LocalEmbeddingEngine | None = None,
    ) -> None:
        self._persist_path = Path(persist_path)
        self._embedding_engine = embedding_engine or LocalEmbeddingEngine()
        self._client: Any | None = None

    async def add_documents(
        self,
        collection: str,
        documents: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        """Add documents with locally generated embeddings to a collection."""
        await asyncio.to_thread(
            self._add_documents_sync,
            collection,
            documents,
            metadatas,
            ids,
        )

    async def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 5,
        filter: Optional[dict[str, Any]] = None,
    ) -> QueryResult:
        """Query a collection using locally embedded query text."""
        embedding = await asyncio.to_thread(self._embedding_engine.embed_text, query_text)
        result = await asyncio.to_thread(
            self._query_sync,
            collection,
            embedding,
            n_results,
            filter,
        )
        result.query = query_text
        return result

    async def query_by_embedding(
        self,
        collection: str,
        embedding: list[float],
        n_results: int = 5,
    ) -> QueryResult:
        """Query a collection using a precomputed embedding vector."""
        return await asyncio.to_thread(
            self._query_sync,
            collection,
            embedding,
            n_results,
            None,
        )

    async def get_collection_stats(self, collection: str) -> dict[str, Any]:
        """Return basic statistics for a named collection."""
        return await asyncio.to_thread(self._get_collection_stats_sync, collection)

    async def delete_collection(self, collection: str) -> None:
        """Delete a collection from the persistent store."""
        await asyncio.to_thread(self._delete_collection_sync, collection)

    async def list_collections(self) -> list[str]:
        """List all collection names present in the persistent store."""
        return await asyncio.to_thread(self._list_collections_sync)

    def _ensure_client(self) -> Any:
        if chromadb is None:
            raise ImportError(
                "chromadb is not installed. Install with: pip install 'dfat[intelligence]'"
            )
        if self._client is None:
            self._persist_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._persist_path))
        return self._client

    def _get_collection(self, name: str) -> Collection:
        self._validate_collection_name(name)
        client = self._ensure_client()
        description = self.COLLECTIONS[name]
        return client.get_or_create_collection(name=name, metadata={"description": description})

    @staticmethod
    def _validate_collection_name(name: str) -> None:
        if name not in ForensicVectorStore.COLLECTIONS:
            raise ValueError(f"Unknown collection '{name}'")

    def _add_documents_sync(
        self,
        collection: str,
        documents: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        if not (len(documents) == len(metadatas) == len(ids)):
            raise ValueError("documents, metadatas, and ids must have the same length")
        chroma_collection = self._get_collection(collection)
        embeddings = self._embedding_engine.embed_batch(documents)
        chroma_collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings,
        )

    def _query_sync(
        self,
        collection: str,
        embedding: list[float],
        n_results: int,
        filter: Optional[dict[str, Any]],
    ) -> QueryResult:
        chroma_collection = self._get_collection(collection)
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if filter is not None:
            kwargs["where"] = filter
        raw = chroma_collection.query(**kwargs)
        return QueryResult(
            documents=list(raw.get("documents", [[]])[0] or []),
            metadatas=list(raw.get("metadatas", [[]])[0] or []),
            distances=[float(value) for value in raw.get("distances", [[]])[0] or []],
            ids=list(raw.get("ids", [[]])[0] or []),
            collection=collection,
        )

    def _get_collection_stats_sync(self, collection: str) -> dict[str, Any]:
        """Return document count and metadata for a collection.

        When chromadb is unavailable, returns a degraded payload instead of
        raising so /knowledge/stats can report availability without a 500.
        """
        self._validate_collection_name(collection)
        base: dict[str, Any] = {
            "name": collection,
            "description": self.COLLECTIONS[collection],
            "count": 0,
            "available": False,
        }
        if chromadb is None:
            return {**base, "error": "chromadb is not installed"}
        try:
            chroma_collection = self._get_collection(collection)
            return {
                "name": collection,
                "description": self.COLLECTIONS[collection],
                "count": chroma_collection.count(),
                "available": True,
            }
        except Exception as exc:  # noqa: BLE001
            return {**base, "error": str(exc)}

    def _delete_collection_sync(self, collection: str) -> None:
        self._validate_collection_name(collection)
        client = self._ensure_client()
        client.delete_collection(name=collection)

    def _list_collections_sync(self) -> list[str]:
        if chromadb is None:
            raise ImportError(
                "chromadb is not installed. Install with: pip install 'dfat[intelligence]'"
            )
        client = self._ensure_client()
        return [item.name for item in client.list_collections()]
