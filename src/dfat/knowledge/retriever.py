"""Unified retrieval across vector store, IOC database, and knowledge graph."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.preprocessing.serializer import ArtefactSerializer
from dfat.core.models.artefact import Artefact
from dfat.knowledge.embeddings import LocalEmbeddingEngine
from dfat.knowledge.ioc_database import IOCEntry, IOCKnowledgeBase
from dfat.knowledge.knowledge_graph import ForensicKnowledgeGraph, NodeType
from dfat.knowledge.vector_store import ForensicVectorStore

DEFAULT_SOURCES: tuple[str, ...] = (
    "artefacts",
    "knowledge",
    "iocs",
    "threat_intel",
    "graph",
)

_VECTOR_SOURCES: dict[str, str] = {
    "artefacts": "artefacts",
    "knowledge": "knowledge",
    "threat_intel": "threat_intel",
    "iocs": "iocs",
}

_CONFIDENCE_SCORES = {"high": 1.0, "medium": 0.7, "low": 0.4}


class RetrievalResult(BaseModel):
    """Merged retrieval output from multiple knowledge sources."""

    model_config = ConfigDict(validate_assignment=True)

    query: str
    total_results: int = Field(ge=0)
    vector_results: list[dict[str, Any]] = Field(default_factory=list)
    ioc_matches: list[IOCEntry] = Field(default_factory=list)
    graph_connections: list[dict[str, Any]] = Field(default_factory=list)
    sources_queried: list[str] = Field(default_factory=list)
    retrieval_time_ms: float = Field(ge=0.0)


class UnifiedRetriever:
    """Query vector store, IOC database, and knowledge graph through one interface."""

    def __init__(
        self,
        vector_store: ForensicVectorStore,
        ioc_db: IOCKnowledgeBase,
        knowledge_graph: ForensicKnowledgeGraph,
        embedding_engine: LocalEmbeddingEngine,
    ) -> None:
        self._vector_store = vector_store
        self._ioc_db = ioc_db
        self._knowledge_graph = knowledge_graph
        self._embedding_engine = embedding_engine
        self._artefact_serializer = ArtefactSerializer()

    async def retrieve(
        self,
        query: str,
        sources: list[str] | None = None,
        max_results: int = 10,
    ) -> RetrievalResult:
        """Query across selected knowledge sources and return ranked merged results."""
        started = asyncio.get_running_loop().time()
        selected = sources or list(DEFAULT_SOURCES)
        vector_results: list[dict[str, Any]] = []
        ioc_matches: list[IOCEntry] = []
        graph_connections: list[dict[str, Any]] = []

        per_source_limit = max(1, max_results // max(len(selected), 1))

        if "iocs" in selected:
            ioc_matches = await self._ioc_db.search(query)
            ioc_matches = self._rank_ioc_matches(ioc_matches)[:per_source_limit]

        for source in selected:
            collection = _VECTOR_SOURCES.get(source)
            if collection is None:
                continue
            results = await self._query_vector_collection(
                collection=collection,
                query=query,
                limit=per_source_limit,
                source_label=source,
            )
            vector_results.extend(results)

        if "graph" in selected:
            graph_connections = await asyncio.to_thread(
                self._search_graph,
                query,
                per_source_limit,
            )

        vector_results = self._dedupe_and_rank_vector_results(vector_results)[:max_results]
        duration_ms = round((asyncio.get_running_loop().time() - started) * 1000, 2)
        total_results = len(vector_results) + len(ioc_matches) + len(graph_connections)

        return RetrievalResult(
            query=query,
            total_results=total_results,
            vector_results=vector_results,
            ioc_matches=ioc_matches,
            graph_connections=graph_connections,
            sources_queried=selected,
            retrieval_time_ms=duration_ms,
        )

    async def retrieve_for_artefact(self, artefact: Artefact) -> RetrievalResult:
        """Find similar artefacts, related IOCs, and graph connections for one artefact."""
        started = asyncio.get_running_loop().time()
        artefact_text = self._artefact_serializer.serialize_artefact(artefact)
        vector_results = await self._query_vector_collection(
            collection="artefacts",
            query=artefact_text,
            limit=5,
            source_label="artefacts",
            extra_metadata={"artefact_id": artefact.artefact_id},
        )

        ioc_matches: list[IOCEntry] = []
        for indicator in self._extract_artefact_indicators(artefact):
            matches = await self._lookup_ioc_indicator(indicator)
            ioc_matches.extend(matches)
        ioc_matches = self._dedupe_ioc_matches(ioc_matches)

        graph_node = f"{NodeType.ARTEFACT.value}:{artefact.artefact_id}"
        graph_connections = await asyncio.to_thread(
            self._knowledge_graph.query_related,
            graph_node,
            2,
        )

        vector_results = self._dedupe_and_rank_vector_results(vector_results)
        duration_ms = round((asyncio.get_running_loop().time() - started) * 1000, 2)
        return RetrievalResult(
            query=artefact_text,
            total_results=len(vector_results) + len(ioc_matches) + len(graph_connections),
            vector_results=vector_results,
            ioc_matches=self._rank_ioc_matches(ioc_matches),
            graph_connections=graph_connections,
            sources_queried=["artefacts", "iocs", "graph"],
            retrieval_time_ms=duration_ms,
        )

    async def retrieve_for_case(
        self,
        case_id: str,
        query: str,
        max_results: int = 10,
    ) -> RetrievalResult:
        """Perform case-scoped retrieval with same-case artefacts ranked first."""
        started = asyncio.get_running_loop().time()
        case_results = await self._query_vector_collection(
            collection="artefacts",
            query=query,
            limit=max_results,
            source_label="artefacts",
            metadata_filter={"case_id": case_id},
            score_boost=1.5,
        )
        general = await self.retrieve(
            query=query,
            sources=["knowledge", "iocs", "threat_intel", "graph"],
            max_results=max_results,
        )

        merged_vectors = self._dedupe_and_rank_vector_results(
            [*case_results, *general.vector_results]
        )[:max_results]
        duration_ms = round((asyncio.get_running_loop().time() - started) * 1000, 2)
        total_results = len(merged_vectors) + len(general.ioc_matches) + len(general.graph_connections)

        return RetrievalResult(
            query=query,
            total_results=total_results,
            vector_results=merged_vectors,
            ioc_matches=general.ioc_matches,
            graph_connections=general.graph_connections,
            sources_queried=["artefacts", "knowledge", "iocs", "threat_intel", "graph"],
            retrieval_time_ms=duration_ms,
        )

    async def _query_vector_collection(
        self,
        *,
        collection: str,
        query: str,
        limit: int,
        source_label: str,
        metadata_filter: dict[str, Any] | None = None,
        score_boost: float = 1.0,
        extra_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            result = await self._vector_store.query(
                collection=collection,
                query_text=query,
                n_results=limit,
                filter=metadata_filter,
            )
        except Exception:  # noqa: BLE001
            return []

        items: list[dict[str, Any]] = []
        for index, document in enumerate(result.documents):
            distance = result.distances[index] if index < len(result.distances) else 1.0
            metadata = result.metadatas[index] if index < len(result.metadatas) else {}
            doc_id = result.ids[index] if index < len(result.ids) else f"{collection}:{index}"
            score = round(score_boost / (1.0 + float(distance)), 4)
            items.append(
                {
                    "source": source_label,
                    "collection": collection,
                    "id": doc_id,
                    "document": document,
                    "metadata": metadata,
                    "distance": float(distance),
                    "score": score,
                    **(extra_metadata or {}),
                }
            )
        return items

    async def _lookup_ioc_indicator(self, indicator: tuple[str, str]) -> list[IOCEntry]:
        ioc_type, value = indicator
        if ioc_type == "hash":
            return await self._ioc_db.lookup_hash(value)
        if ioc_type == "ip":
            return await self._ioc_db.lookup_ip(value)
        if ioc_type == "domain":
            return await self._ioc_db.lookup_domain(value)
        if ioc_type == "process":
            return await self._ioc_db.lookup_process_name(value)
        if ioc_type == "registry":
            return await self._ioc_db.lookup_registry_key(value)
        return await self._ioc_db.search(value, ioc_type=ioc_type)

    def _search_graph(self, query: str, limit: int) -> list[dict[str, Any]]:
        query_lower = query.lower()
        matches: list[dict[str, Any]] = []
        for node_id, attrs in self._knowledge_graph.graph.nodes(data=True):
            label = str(attrs.get("label", "")).lower()
            if query_lower not in label and query_lower not in node_id.lower():
                continue
            related = self._knowledge_graph.query_related(node_id, max_depth=1)
            matches.append(
                {
                    "node_id": node_id,
                    "label": attrs.get("label", node_id),
                    "node_type": attrs.get("node_type"),
                    "related_nodes": related,
                    "score": 1.0 if query_lower == label else 0.8,
                }
            )
        matches.sort(key=lambda item: item["score"], reverse=True)
        return matches[:limit]

    @staticmethod
    def _extract_artefact_indicators(artefact: Artefact) -> list[tuple[str, str]]:
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        indicators: list[tuple[str, str]] = []

        for key, ioc_type in (
            ("remote_address", "ip"),
            ("local_address", "ip"),
            ("destination_ip", "ip"),
            ("domain", "domain"),
            ("hostname", "domain"),
            ("hash_sha256", "hash"),
            ("hash", "hash"),
            ("name", "process"),
            ("process_name", "process"),
            ("key_path", "registry"),
        ):
            value = raw.get(key)
            if value:
                indicators.append((ioc_type, str(value)))
        return indicators

    @staticmethod
    def _rank_ioc_matches(matches: list[IOCEntry]) -> list[IOCEntry]:
        return sorted(
            matches,
            key=lambda item: _CONFIDENCE_SCORES.get(item.confidence.lower(), 0.5),
            reverse=True,
        )

    @staticmethod
    def _dedupe_ioc_matches(matches: list[IOCEntry]) -> list[IOCEntry]:
        seen: set[str] = set()
        deduped: list[IOCEntry] = []
        for match in matches:
            if match.ioc_id in seen:
                continue
            seen.add(match.ioc_id)
            deduped.append(match)
        return deduped

    @staticmethod
    def _dedupe_and_rank_vector_results(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for item in sorted(items, key=lambda entry: entry.get("score", 0.0), reverse=True):
            key = str(item.get("id") or item.get("document"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
