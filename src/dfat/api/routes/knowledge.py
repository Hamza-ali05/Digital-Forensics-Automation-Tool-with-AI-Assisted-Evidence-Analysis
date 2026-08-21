"""Knowledge base query and statistics API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from dfat.api.dependencies import (
    get_ioc_knowledge_base,
    get_knowledge_graph,
    get_unified_retriever,
    get_vector_store,
    require_permission,
)
from dfat.api.schemas.extension import (
    IOCSearchResponse,
    KnowledgeQueryRequest,
    KnowledgeStatsResponse,
)
from dfat.database.models.user import UserORM
from dfat.knowledge.ioc_database import IOCKnowledgeBase
from dfat.knowledge.knowledge_graph import ForensicKnowledgeGraph
from dfat.knowledge.retriever import RetrievalResult, UnifiedRetriever
from dfat.knowledge.vector_store import ForensicVectorStore

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.get("/stats", response_model=KnowledgeStatsResponse)
async def knowledge_stats(
    _: UserORM = Depends(require_permission("knowledge", "read")),
    vector_store: ForensicVectorStore = Depends(get_vector_store),
    ioc_kb: IOCKnowledgeBase = Depends(get_ioc_knowledge_base),
    knowledge_graph: ForensicKnowledgeGraph = Depends(get_knowledge_graph),
) -> KnowledgeStatsResponse:
    """Return aggregate knowledge-base statistics.

    Unavailable subsystems (e.g. chromadb not installed) are reported as
    degraded payloads rather than failing the whole request with 500.
    """
    collection_stats: dict[str, object] = {}
    for collection in ForensicVectorStore.COLLECTIONS:
        try:
            collection_stats[collection] = await vector_store.get_collection_stats(
                collection
            )
        except Exception as exc:  # noqa: BLE001
            collection_stats[collection] = {
                "name": collection,
                "count": 0,
                "available": False,
                "error": str(exc),
            }

    try:
        ioc_statistics = await ioc_kb.get_statistics()
    except Exception as exc:  # noqa: BLE001
        ioc_statistics = {"available": False, "error": str(exc), "total_count": 0}

    try:
        graph_statistics = knowledge_graph.get_statistics()
    except Exception as exc:  # noqa: BLE001
        graph_statistics = {"available": False, "error": str(exc)}

    return KnowledgeStatsResponse(
        vector_collections=collection_stats,
        ioc_statistics=ioc_statistics,
        graph_statistics=graph_statistics,
    )


@router.post("/query", response_model=RetrievalResult)
async def query_knowledge(
    body: KnowledgeQueryRequest,
    _: UserORM = Depends(require_permission("knowledge", "read")),
    retriever: UnifiedRetriever = Depends(get_unified_retriever),
) -> RetrievalResult:
    """Query the unified knowledge base."""
    return await retriever.retrieve(
        query=body.query,
        sources=body.sources,
        max_results=body.max_results,
    )


@router.get("/graph/stats")
async def graph_stats(
    _: UserORM = Depends(require_permission("knowledge", "read")),
    knowledge_graph: ForensicKnowledgeGraph = Depends(get_knowledge_graph),
) -> dict[str, object]:
    """Return knowledge graph statistics."""
    return knowledge_graph.get_statistics()


@router.get("/iocs", response_model=IOCSearchResponse)
async def search_iocs(
    query: str = Query(min_length=1),
    ioc_type: Optional[str] = Query(default=None),
    _: UserORM = Depends(require_permission("knowledge", "read")),
    ioc_kb: IOCKnowledgeBase = Depends(get_ioc_knowledge_base),
) -> IOCSearchResponse:
    """Search the IOC knowledge base."""
    matches = await ioc_kb.search(query, ioc_type=ioc_type)
    return IOCSearchResponse(
        query=query,
        ioc_type=ioc_type,
        matches=matches,
        total=len(matches),
    )


@router.get("/iocs/stats")
async def ioc_stats(
    _: UserORM = Depends(require_permission("knowledge", "read")),
    ioc_kb: IOCKnowledgeBase = Depends(get_ioc_knowledge_base),
) -> dict[str, object]:
    """Return IOC database statistics."""
    return await ioc_kb.get_statistics()
