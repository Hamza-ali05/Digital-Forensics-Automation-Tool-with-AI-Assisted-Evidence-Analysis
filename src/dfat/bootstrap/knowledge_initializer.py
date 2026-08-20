"""Knowledge base bootstrap — vector store, embeddings, IOC, graph."""

from __future__ import annotations

import logging
import time
from typing import Any

from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)


class KnowledgeInitializer:
    """Initialize ChromaDB, embedding engine, knowledge graph, and IOC database."""

    def __init__(
        self,
        vector_store: Any,
        embedding_engine: Any,
        indexer: Any,
        ioc_kb: Any,
        knowledge_graph: Any,
        settings: DFATSettings,
    ) -> None:
        self._vector_store = vector_store
        self._embedding_engine = embedding_engine
        self._indexer = indexer
        self._ioc_kb = ioc_kb
        self._knowledge_graph = knowledge_graph
        self._settings = settings

    async def initialize(self) -> PhaseResult:
        """Initialize all knowledge subsystems (compat / combined entry point)."""
        kb = await self.initialize_knowledge_base()
        ioc = await self.initialize_ioc()
        degraded = list(dict.fromkeys(kb.degraded_capabilities + ioc.degraded_capabilities))
        details = {**kb.details, **ioc.details}
        status = InitStatus.COMPLETED if not degraded else InitStatus.DEGRADED
        return PhaseResult(
            phase=InitPhase.KNOWLEDGE_BASE,
            status=status,
            duration_ms=kb.duration_ms + ioc.duration_ms,
            message=(
                "Knowledge base ready"
                if not degraded
                else f"Knowledge base degraded: {', '.join(degraded)}"
            ),
            details=details,
            is_critical=False,
            degraded_capabilities=degraded,
        )

    async def initialize_knowledge_base(self) -> PhaseResult:
        """Initialize vector store, embeddings, graph, and stale-index checks."""
        started = time.perf_counter()
        details: dict[str, Any] = {}
        degraded: list[str] = []

        try:
            import chromadb  # noqa: F401

            if chromadb is None:
                raise ImportError("chromadb is not installed")
            vs = self._vector_store
            if hasattr(vs, "_get_client"):
                vs._get_client()
            details["vector_store"] = "ready"
            details["document_count"] = self._document_count()
        except Exception as exc:  # noqa: BLE001
            details["vector_store"] = f"unavailable: {exc}"
            details["document_count"] = 0
            degraded.append("vector_store")
            logger.warning("ChromaDB unavailable: %s", exc)

        try:
            model_name = getattr(self._embedding_engine, "_model_name", "unknown")
            details["embedding_model"] = model_name
            logger.info("Embedding model configured: %s (lazy-load on first use)", model_name)
        except Exception as exc:  # noqa: BLE001
            details["embedding_model"] = f"error: {exc}"
            degraded.append("embedding_engine")

        stale = self._check_stale_indexes()
        details["stale_indexes"] = stale
        if stale:
            logger.info(
                "%d dataset(s) have stale indexes and may need re-indexing",
                len(stale),
            )

        try:
            details["graph_nodes"] = self._graph_node_count()
        except Exception as exc:  # noqa: BLE001
            details["graph_nodes"] = f"error: {exc}"
            degraded.append("knowledge_graph")

        duration_ms = (time.perf_counter() - started) * 1000.0
        status = InitStatus.COMPLETED if not degraded else InitStatus.DEGRADED
        return PhaseResult(
            phase=InitPhase.KNOWLEDGE_BASE,
            status=status,
            duration_ms=duration_ms,
            message=(
                "Knowledge base ready"
                if not degraded
                else f"Knowledge base degraded: {', '.join(degraded)}"
            ),
            details=details,
            is_critical=False,
            degraded_capabilities=degraded,
        )

    async def initialize_ioc(self) -> PhaseResult:
        """Initialize the IOC database only."""
        started = time.perf_counter()
        details: dict[str, Any] = {}
        degraded: list[str] = []

        try:
            ioc_stats: dict[str, Any] = {}
            if hasattr(self._ioc_kb, "get_statistics"):
                ioc_stats = self._ioc_kb.get_statistics()
            details["ioc_total_count"] = ioc_stats.get("total_count", 0)
        except Exception as exc:  # noqa: BLE001
            details["ioc_total_count"] = 0
            details["error"] = str(exc)
            degraded.append("ioc_database")
            logger.warning("IOC database unavailable: %s", exc)

        duration_ms = (time.perf_counter() - started) * 1000.0
        status = InitStatus.COMPLETED if not degraded else InitStatus.DEGRADED
        return PhaseResult(
            phase=InitPhase.IOC_DATABASE,
            status=status,
            duration_ms=duration_ms,
            message=(
                f"IOC database ready ({details.get('ioc_total_count', 0)} IOCs)"
                if not degraded
                else "IOC database degraded"
            ),
            details=details,
            is_critical=False,
            degraded_capabilities=degraded,
        )

    def _check_stale_indexes(self) -> list[str]:
        """Return dataset IDs that may need re-indexing (stub — always empty)."""
        return []

    def _document_count(self) -> int:
        vs = self._vector_store
        if hasattr(vs, "count"):
            return int(vs.count())
        if hasattr(vs, "get_document_count"):
            return int(vs.get_document_count())
        return 0

    def _graph_node_count(self) -> int:
        graph = self._knowledge_graph
        if hasattr(graph, "node_count"):
            return int(graph.node_count())
        if hasattr(graph, "_graph"):
            nodes = getattr(graph._graph, "nodes", [])
            return len(nodes)
        return 0
