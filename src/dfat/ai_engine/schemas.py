"""API request/response schemas for AI analysis endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.assistance.investigator_qa import QAResponse
from dfat.ai_engine.caching.response_cache import CacheStats
from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.explanation.explainer import ArtefactExplanation
from dfat.ai_engine.llm.connection import LLMHealthStatus
from dfat.ai_engine.monitoring.ai_monitor import AIUsageStats
from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.api.schemas.base import API_JSON_ENCODERS


class ClassifyRequest(BaseModel):
    """Request body for ``POST /ai/classify``."""

    model_config = ConfigDict(frozen=False, json_encoders=API_JSON_ENCODERS)

    evidence_id: str
    use_fallback: bool = False


class ClassifyResponse(BaseModel):
    """Classification outcomes for an evidence artefact set."""

    model_config = ConfigDict(frozen=False, json_encoders=API_JSON_ENCODERS)

    classifications: list[ClassificationResult] = Field(default_factory=list)
    confidence: float = 0.0
    model_used: str
    analysis_record_id: Optional[str] = None


class SummarizeRequest(BaseModel):
    """Request body for ``POST /ai/summarize``."""

    model_config = ConfigDict(frozen=False, json_encoders=API_JSON_ENCODERS)

    evidence_id: str
    use_fallback: bool = False


class SummarizeResponse(BaseModel):
    """Investigative summary payload."""

    model_config = ConfigDict(frozen=False, json_encoders=API_JSON_ENCODERS)

    summary: SummaryResult
    analysis_record_id: Optional[str] = None


class ExplainResponse(BaseModel):
    """Per-artefact explanation payload."""

    model_config = ConfigDict(frozen=False, json_encoders=API_JSON_ENCODERS)

    explanation: ArtefactExplanation
    analysis_record_id: Optional[str] = None


class AskRequest(BaseModel):
    """Request body for ``POST /ai/ask``."""

    model_config = ConfigDict(frozen=False, json_encoders=API_JSON_ENCODERS)

    evidence_id: str
    question: str
    conversation_history: Optional[list[dict[str, str]]] = None


class AskResponse(BaseModel):
    """Investigator Q&A payload."""

    model_config = ConfigDict(frozen=False, json_encoders=API_JSON_ENCODERS)

    response: QAResponse
    analysis_record_id: Optional[str] = None


class AIHealthResponse(LLMHealthStatus):
    """AI engine health probe response (extends ``LLMHealthStatus``)."""


class AIStatsResponse(AIUsageStats):
    """AI usage statistics response (extends ``AIUsageStats``)."""


class AICacheStatsResponse(CacheStats):
    """AI response-cache statistics response."""


class AICacheClearResponse(BaseModel):
    """Result of clearing the AI response cache."""

    model_config = ConfigDict(frozen=False, json_encoders=API_JSON_ENCODERS)

    cleared_entries: int
    cleared_at: datetime

