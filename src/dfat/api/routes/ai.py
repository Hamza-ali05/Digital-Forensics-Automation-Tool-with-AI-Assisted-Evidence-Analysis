"""AI analysis API routes — classify, summarize, explain, Q&A, health, cache."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, status

from dfat.ai_engine.analyzer import LocalLLMClient
from dfat.ai_engine.assistance.investigator_qa import InvestigatorQAAssistant
from dfat.ai_engine.caching.response_cache import AIResponseCache
from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.fallback.rule_based import RuleBasedAnalyzer
from dfat.ai_engine.llm.config import PROMPT_VERSION
from dfat.ai_engine.llm.connection import LLMConnectionManager
from dfat.ai_engine.monitoring.ai_monitor import AIMonitor
from dfat.ai_engine.schemas import (
    AICacheClearResponse,
    AICacheStatsResponse,
    AIHealthResponse,
    AIStatsResponse,
    AskRequest,
    AskResponse,
    ClassifyRequest,
    ClassifyResponse,
    ExplainResponse,
    SummarizeRequest,
    SummarizeResponse,
)
from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.api.dependencies import (
    get_ai_analysis_repo,
    get_ai_monitor,
    get_ai_response_cache,
    get_artefact_repository,
    get_fallback_analyzer,
    get_llm_client,
    get_llm_connection_manager,
    get_qa_assistant,
    require_permission,
    require_role,
)
from dfat.core.enums import SuspicionLevel
from dfat.core.exceptions import EvidenceNotFoundError, LLMConnectionError
from dfat.core.models.artefact import Artefact, ArtefactSet, RankedArtefact
from dfat.database.models.ai_orm import AIAnalysisRecordORM
from dfat.database.models.user import UserORM
from dfat.database.repositories.ai_analysis_repo import SQLAlchemyAIAnalysisRepository
from dfat.database.repositories.artefact_repo import SQLAlchemyArtefactRepository

router = APIRouter(prefix="/ai", tags=["AI Analysis"])


def _as_ranked(artefacts: list[Artefact]) -> list[RankedArtefact]:
    """Promote plain artefacts to ranked items when triage fields are absent."""
    ranked: list[RankedArtefact] = []
    for item in artefacts:
        if isinstance(item, RankedArtefact):
            ranked.append(item)
            continue
        ranked.append(
            RankedArtefact(
                **item.model_dump(),
                suspicion_level=SuspicionLevel.INFORMATIONAL,
                relevance_score=0.0,
                classification_reasoning=None,
            )
        )
    return ranked


def _classifications_from_ranked(
    ranked: list[RankedArtefact],
) -> list[ClassificationResult]:
    """Map ranked artefacts to classification result DTOs."""
    return [
        ClassificationResult(
            artefact_id=item.artefact_id,
            suspicion_level=item.suspicion_level,
            reasoning=item.classification_reasoning or "",
            ioc_indicators=[],
            confidence=item.relevance_score,
        )
        for item in ranked
    ]


async def _require_artefact_set(
    artefact_repo: SQLAlchemyArtefactRepository,
    evidence_id: str,
) -> ArtefactSet:
    """Load artefacts for evidence or raise ``EvidenceNotFoundError``."""
    artefact_set = await artefact_repo.get(evidence_id)
    if artefact_set is None or not artefact_set.artefacts:
        raise EvidenceNotFoundError(
            f"No artefacts found for evidence_id={evidence_id}",
            context={"evidence_id": evidence_id},
        )
    return artefact_set


async def _persist_analysis(
    repo: SQLAlchemyAIAnalysisRepository,
    *,
    evidence_id: str,
    analysis_type: str,
    model_used: str,
    input_artefact_count: int,
    output_token_count: int,
    confidence_score: float,
    duration_ms: float,
    hallucination_risk: Optional[str] = None,
    cache_hit: bool = False,
    job_id: Optional[str] = None,
) -> AIAnalysisRecordORM:
    """Persist an AI analysis telemetry record."""
    record = AIAnalysisRecordORM(
        job_id=job_id or str(uuid.uuid4()),
        evidence_id=evidence_id,
        analysis_type=analysis_type,
        model_used=model_used,
        prompt_version=PROMPT_VERSION,
        input_artefact_count=input_artefact_count,
        output_token_count=output_token_count,
        confidence_score=confidence_score,
        duration_ms=duration_ms,
        hallucination_risk=hallucination_risk,
        cache_hit=cache_hit,
    )
    return await repo.save(record)


@router.post(
    "/classify",
    response_model=ClassifyResponse,
    status_code=status.HTTP_200_OK,
)
async def classify_artefacts(
    body: ClassifyRequest,
    _: UserORM = Depends(require_permission("analysis", "create")),
    llm_client: LocalLLMClient = Depends(get_llm_client),
    fallback: RuleBasedAnalyzer = Depends(get_fallback_analyzer),
    artefact_repo: SQLAlchemyArtefactRepository = Depends(get_artefact_repository),
    ai_repo: SQLAlchemyAIAnalysisRepository = Depends(get_ai_analysis_repo),
) -> ClassifyResponse:
    """Run AI (or rule-based) classification on an evidence artefact set."""
    artefact_set = await _require_artefact_set(artefact_repo, body.evidence_id)
    started = time.perf_counter()

    if body.use_fallback:
        ranked = fallback.analyze(artefact_set)
        model_used = fallback.analyzer_name
    else:
        if not llm_client.is_available():
            raise LLMConnectionError(
                "Local LLM is unavailable for classify()",
                context={"evidence_id": body.evidence_id},
            )
        ranked = await llm_client.analyze_async(artefact_set)
        model_used = llm_client.analyzer_name

    classifications = _classifications_from_ranked(ranked)
    avg_conf = (
        sum(item.confidence for item in classifications) / len(classifications)
        if classifications
        else 0.0
    )
    duration_ms = (time.perf_counter() - started) * 1000.0
    record = await _persist_analysis(
        ai_repo,
        evidence_id=body.evidence_id,
        analysis_type="classification",
        model_used=model_used,
        input_artefact_count=len(artefact_set.artefacts),
        output_token_count=len(classifications) * 16,
        confidence_score=avg_conf,
        duration_ms=duration_ms,
    )
    # Persist ranked triage fields onto artefact rows.
    await artefact_repo.save(
        ArtefactSet(
            evidence_id=artefact_set.evidence_id,
            artefacts=list(ranked),
            categories_present=artefact_set.categories_present,
            extraction_timestamp=artefact_set.extraction_timestamp,
        )
    )
    return ClassifyResponse(
        classifications=classifications,
        confidence=round(avg_conf, 4),
        model_used=model_used,
        analysis_record_id=record.id,
    )


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    status_code=status.HTTP_200_OK,
)
async def summarize_evidence(
    body: SummarizeRequest,
    _: UserORM = Depends(require_permission("analysis", "create")),
    llm_client: LocalLLMClient = Depends(get_llm_client),
    fallback: RuleBasedAnalyzer = Depends(get_fallback_analyzer),
    artefact_repo: SQLAlchemyArtefactRepository = Depends(get_artefact_repository),
    ai_repo: SQLAlchemyAIAnalysisRepository = Depends(get_ai_analysis_repo),
) -> SummarizeResponse:
    """Generate an investigative summary for an evidence artefact set."""
    artefact_set = await _require_artefact_set(artefact_repo, body.evidence_id)
    ranked = _as_ranked(list(artefact_set.artefacts))
    started = time.perf_counter()

    if body.use_fallback:
        text = fallback.summarize(ranked)
        model_used = fallback.analyzer_name
        summary = SummaryResult(
            full_text=text,
            executive_summary=text.split("\n", 1)[0][:500],
            model_used=model_used,
            prompt_version=PROMPT_VERSION,
            confidence_score=1.0,
        )
    else:
        if not llm_client.is_available():
            raise LLMConnectionError(
                "Local LLM is unavailable for summarize()",
                context={"evidence_id": body.evidence_id},
            )
        text = await llm_client.summarize_async(ranked)
        model_used = llm_client.analyzer_name
        summary = SummaryResult(
            full_text=text,
            executive_summary=text[:500],
            model_used=model_used,
            prompt_version=PROMPT_VERSION,
            confidence_score=0.7,
        )

    duration_ms = (time.perf_counter() - started) * 1000.0
    record = await _persist_analysis(
        ai_repo,
        evidence_id=body.evidence_id,
        analysis_type="summarization",
        model_used=model_used,
        input_artefact_count=len(ranked),
        output_token_count=max(1, len(summary.full_text) // 4),
        confidence_score=summary.confidence_score,
        duration_ms=duration_ms,
    )
    return SummarizeResponse(summary=summary, analysis_record_id=record.id)


@router.post(
    "/explain/{artefact_id}",
    response_model=ExplainResponse,
    status_code=status.HTTP_200_OK,
)
async def explain_artefact(
    artefact_id: str,
    _: UserORM = Depends(require_permission("analysis", "create")),
    llm_client: LocalLLMClient = Depends(get_llm_client),
    artefact_repo: SQLAlchemyArtefactRepository = Depends(get_artefact_repository),
    ai_repo: SQLAlchemyAIAnalysisRepository = Depends(get_ai_analysis_repo),
) -> ExplainResponse:
    """Explain a specific artefact via the local LLM explainer."""
    artefact = await artefact_repo.get_by_artefact_id(artefact_id)
    if artefact is None:
        raise EvidenceNotFoundError(
            f"Artefact not found: {artefact_id}",
            context={"artefact_id": artefact_id},
        )
    ranked = _as_ranked([artefact])[0]
    if not llm_client.is_available():
        raise LLMConnectionError(
            "Local LLM is unavailable for explain()",
            context={"artefact_id": artefact_id},
        )

    started = time.perf_counter()
    explanation = await llm_client.explain(ranked)
    duration_ms = (time.perf_counter() - started) * 1000.0
    record = await _persist_analysis(
        ai_repo,
        evidence_id=artefact.source_evidence_id,
        analysis_type="explanation",
        model_used=explanation.model_used or llm_client.analyzer_name,
        input_artefact_count=1,
        output_token_count=max(1, len(explanation.explanation_text) // 4),
        confidence_score=explanation.confidence,
        duration_ms=duration_ms,
    )
    return ExplainResponse(explanation=explanation, analysis_record_id=record.id)


@router.post(
    "/ask",
    response_model=AskResponse,
    status_code=status.HTTP_200_OK,
)
async def ask_question(
    body: AskRequest,
    _: UserORM = Depends(require_permission("analysis", "create")),
    llm_client: LocalLLMClient = Depends(get_llm_client),
    qa_assistant: InvestigatorQAAssistant = Depends(get_qa_assistant),
    artefact_repo: SQLAlchemyArtefactRepository = Depends(get_artefact_repository),
    ai_repo: SQLAlchemyAIAnalysisRepository = Depends(get_ai_analysis_repo),
) -> AskResponse:
    """Ask a natural-language question about evidence artefacts."""
    artefact_set = await _require_artefact_set(artefact_repo, body.evidence_id)
    ranked = _as_ranked(list(artefact_set.artefacts))
    started = time.perf_counter()
    qa = await qa_assistant.ask(
        body.question,
        artefact_set,
        ranked=ranked,
        conversation_history=body.conversation_history,
    )
    duration_ms = (time.perf_counter() - started) * 1000.0
    risk = (
        qa.hallucination_check.risk_level
        if qa.hallucination_check is not None
        else None
    )
    record = await _persist_analysis(
        ai_repo,
        evidence_id=body.evidence_id,
        analysis_type="qa",
        model_used=qa.model_used or llm_client.analyzer_name,
        input_artefact_count=len(artefact_set.artefacts),
        output_token_count=max(1, len(qa.answer) // 4),
        confidence_score=qa.confidence,
        duration_ms=duration_ms,
        hallucination_risk=risk,
    )
    return AskResponse(response=qa, analysis_record_id=record.id)


@router.get("/health", response_model=AIHealthResponse)
async def ai_health(
    connection_manager: LLMConnectionManager = Depends(get_llm_connection_manager),
) -> AIHealthResponse:
    """Check local LLM / Ollama health (no authentication required)."""
    status_result = await connection_manager.check_health()
    return AIHealthResponse.model_validate(status_result.model_dump())


@router.get("/stats", response_model=AIStatsResponse)
async def ai_stats(
    _: UserORM = Depends(require_role(["admin"])),
    monitor: AIMonitor = Depends(get_ai_monitor),
) -> AIStatsResponse:
    """Return aggregated AI usage statistics (admin only)."""
    stats = await monitor.get_ai_usage_stats()
    return AIStatsResponse.model_validate(stats.model_dump())


@router.get("/cache/stats", response_model=AICacheStatsResponse)
async def ai_cache_stats(
    _: UserORM = Depends(require_role(["admin"])),
    cache: AIResponseCache = Depends(get_ai_response_cache),
) -> AICacheStatsResponse:
    """Return AI response-cache statistics (admin only)."""
    stats = await cache.get_stats()
    return AICacheStatsResponse.model_validate(stats.model_dump())


@router.delete("/cache", response_model=AICacheClearResponse)
async def clear_ai_cache(
    _: UserORM = Depends(require_role(["admin"])),
    cache: AIResponseCache = Depends(get_ai_response_cache),
) -> AICacheClearResponse:
    """Clear the AI response cache (admin only)."""
    cleared = await cache.invalidate_all()
    return AICacheClearResponse(
        cleared_entries=cleared,
        cleared_at=datetime.now(UTC),
    )

