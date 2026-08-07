"""AI operation logging, monitoring, and usage telemetry.

Logs metadata only — NEVER prompt content or evidence bodies — for forensic
audit compliance and performance monitoring.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.validation.hallucination_guard import HallucinationReport
from dfat.core.enums import PipelineStage

logger = logging.getLogger(__name__)

# Keys that must never appear in logged detail payloads.
_FORBIDDEN_DETAIL_KEYS = frozenset(
    {
        "prompt",
        "prompt_text",
        "prompt_content",
        "evidence",
        "evidence_data",
        "raw_data",
        "artefact_text",
        "context_text",
        "response_text",
        "full_text",
    }
)


class AuditLoggerPort(Protocol):
    """Minimal async audit logging port (satisfied by ``AuditService``)."""

    async def log_action(
        self,
        stage: PipelineStage,
        action: str,
        evidence_id: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Persist an audit action."""


class AIUsageStats(BaseModel):
    """Aggregated AI usage statistics for a monitoring window."""

    model_config = ConfigDict(frozen=False)

    total_requests: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    avg_response_time_ms: float = 0.0
    cache_hit_rate: float = 0.0
    hallucination_detections: int = 0
    avg_confidence: float = 0.0
    requests_by_type: dict[str, int] = Field(default_factory=dict)


class _RequestRecord(BaseModel):
    """Internal request telemetry record."""

    model_config = ConfigDict(frozen=False)

    request_id: str
    request_type: str
    model: str
    prompt_tokens: int = 0
    job_id: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completion_tokens: int = 0
    duration_ms: float = 0.0
    success: Optional[bool] = None
    cache_hit: bool = False
    completed: bool = False


class _EventRecord(BaseModel):
    """Internal generic AI event for aggregation."""

    model_config = ConfigDict(frozen=False)

    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confidence: Optional[float] = None
    details: dict[str, Any] = Field(default_factory=dict)


class AIMonitor:
    """Comprehensive logging of AI operations for audit and telemetry."""

    def __init__(
        self,
        audit_service: AuditLoggerPort,
        app_logger: Optional[logging.Logger] = None,
    ) -> None:
        """Initialise the AI monitor.

        Args:
            audit_service: Dual-write audit service (or compatible port).
            app_logger: Application logger for operational diagnostics.
        """
        self._audit = audit_service
        self._log = app_logger or logger
        self._requests: dict[str, _RequestRecord] = {}
        self._events: list[_EventRecord] = []
        self._hallucination_count = 0
        self._confidence_samples: list[float] = []

    async def log_llm_request(
        self,
        request_type: str,
        model: str,
        prompt_tokens: int,
        job_id: Optional[str] = None,
    ) -> str:
        """Log an LLM request (metadata only) and return a correlation ID.

        NEVER logs prompt content or evidence data.

        Args:
            request_type: Operation type (e.g. ``generate``, ``classify``).
            model: Model identifier.
            prompt_tokens: Estimated or reported prompt token count.
            job_id: Optional pipeline job identifier.

        Returns:
            ``request_id`` for correlating the matching response log.
        """
        request_id = str(uuid.uuid4())
        record = _RequestRecord(
            request_id=request_id,
            request_type=request_type,
            model=model,
            prompt_tokens=max(0, int(prompt_tokens)),
            job_id=job_id,
        )
        self._requests[request_id] = record
        details = self._safe_details(
            {
                "request_id": request_id,
                "request_type": request_type,
                "model": model,
                "prompt_tokens": record.prompt_tokens,
                "job_id": job_id,
            }
        )
        await self._audit.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="AI_LLM_REQUEST",
            evidence_id=job_id or "system",
            details=details,
        )
        self._log.info(
            "AI request id=%s type=%s model=%s tokens_in=%s",
            request_id,
            request_type,
            model,
            record.prompt_tokens,
        )
        return request_id

    async def log_llm_response(
        self,
        request_id: str,
        completion_tokens: int,
        duration_ms: float,
        success: bool,
        cache_hit: bool,
    ) -> None:
        """Log an LLM response correlated to ``request_id``."""
        record = self._requests.get(request_id)
        if record is None:
            record = _RequestRecord(
                request_id=request_id,
                request_type="unknown",
                model="unknown",
            )
            self._requests[request_id] = record

        record.completion_tokens = max(0, int(completion_tokens))
        record.duration_ms = float(duration_ms)
        record.success = bool(success)
        record.cache_hit = bool(cache_hit)
        record.completed = True

        details = self._safe_details(
            {
                "request_id": request_id,
                "request_type": record.request_type,
                "model": record.model,
                "completion_tokens": record.completion_tokens,
                "duration_ms": round(record.duration_ms, 2),
                "success": record.success,
                "cache_hit": record.cache_hit,
                "job_id": record.job_id,
            }
        )
        await self._audit.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="AI_LLM_RESPONSE",
            evidence_id=record.job_id or "system",
            details=details,
        )
        self._log.info(
            "AI response id=%s success=%s cache_hit=%s duration_ms=%.1f tokens_out=%s",
            request_id,
            success,
            cache_hit,
            duration_ms,
            completion_tokens,
        )

    async def log_classification(
        self,
        job_id: str,
        artefact_count: int,
        results_count: int,
        avg_confidence: float,
        duration_ms: float,
    ) -> None:
        """Log a classification batch telemetry event."""
        self._confidence_samples.append(float(avg_confidence))
        self._events.append(
            _EventRecord(
                event_type="classification",
                confidence=float(avg_confidence),
                details={
                    "job_id": job_id,
                    "artefact_count": artefact_count,
                    "results_count": results_count,
                    "duration_ms": duration_ms,
                },
            )
        )
        await self._audit.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="AI_CLASSIFICATION",
            evidence_id=job_id,
            details=self._safe_details(
                {
                    "job_id": job_id,
                    "artefact_count": artefact_count,
                    "results_count": results_count,
                    "avg_confidence": round(float(avg_confidence), 4),
                    "duration_ms": round(float(duration_ms), 2),
                }
            ),
        )

    async def log_summarization(
        self,
        job_id: str,
        summary_length: int,
        confidence: float,
        duration_ms: float,
    ) -> None:
        """Log a summarization telemetry event."""
        self._confidence_samples.append(float(confidence))
        self._events.append(
            _EventRecord(
                event_type="summarization",
                confidence=float(confidence),
                details={
                    "job_id": job_id,
                    "summary_length": summary_length,
                    "duration_ms": duration_ms,
                },
            )
        )
        await self._audit.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="AI_SUMMARIZATION",
            evidence_id=job_id,
            details=self._safe_details(
                {
                    "job_id": job_id,
                    "summary_length": summary_length,
                    "confidence": round(float(confidence), 4),
                    "duration_ms": round(float(duration_ms), 2),
                }
            ),
        )

    async def log_hallucination_detected(
        self,
        request_id: str,
        report: HallucinationReport,
    ) -> None:
        """Log a hallucination detection event (IDs/terms counts only)."""
        self._hallucination_count += 1
        self._events.append(
            _EventRecord(
                event_type="hallucination",
                details={
                    "request_id": request_id,
                    "risk_level": report.risk_level,
                },
            )
        )
        await self._audit.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="AI_HALLUCINATION_DETECTED",
            evidence_id="system",
            details=self._safe_details(
                {
                    "request_id": request_id,
                    "risk_level": report.risk_level,
                    "hallucinated_id_count": len(report.hallucinated_ids),
                    "fabricated_term_count": len(report.fabricated_terms),
                    "unsupported_assertion_count": len(report.unsupported_assertions),
                }
            ),
        )
        self._log.warning(
            "AI hallucination detected request_id=%s risk=%s ids=%s terms=%s",
            request_id,
            report.risk_level,
            len(report.hallucinated_ids),
            len(report.fabricated_terms),
        )

    async def get_ai_usage_stats(
        self,
        since: Optional[datetime] = None,
    ) -> AIUsageStats:
        """Aggregate AI usage statistics, optionally since ``since`` (UTC)."""
        since_ts = since or datetime.fromtimestamp(0, tz=UTC)
        if since_ts.tzinfo is None:
            since_ts = since_ts.replace(tzinfo=UTC)

        requests = [
            item
            for item in self._requests.values()
            if item.started_at >= since_ts
        ]
        events = [item for item in self._events if item.timestamp >= since_ts]

        total_requests = len(requests)
        tokens_in = sum(item.prompt_tokens for item in requests)
        tokens_out = sum(
            item.completion_tokens for item in requests if item.completed
        )
        completed = [item for item in requests if item.completed]
        avg_latency = (
            sum(item.duration_ms for item in completed) / len(completed)
            if completed
            else 0.0
        )
        cache_completed = [item for item in completed if item.success is not None]
        cache_hits = sum(1 for item in cache_completed if item.cache_hit)
        cache_rate = (
            cache_hits / len(cache_completed) if cache_completed else 0.0
        )

        by_type: dict[str, int] = {}
        for item in requests:
            by_type[item.request_type] = by_type.get(item.request_type, 0) + 1

        hallu = sum(1 for item in events if item.event_type == "hallucination")
        # Prefer in-window confidence samples from events; fall back to all samples.
        conf_values = [
            float(item.confidence)
            for item in events
            if item.confidence is not None
        ]
        if not conf_values:
            conf_values = list(self._confidence_samples)
        avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0

        return AIUsageStats(
            total_requests=total_requests,
            total_tokens_in=tokens_in,
            total_tokens_out=tokens_out,
            avg_response_time_ms=round(avg_latency, 2),
            cache_hit_rate=round(cache_rate, 4),
            hallucination_detections=hallu or (
                self._hallucination_count if since is None else hallu
            ),
            avg_confidence=round(avg_conf, 4),
            requests_by_type=by_type,
        )

    @staticmethod
    def _safe_details(details: dict[str, Any]) -> dict[str, Any]:
        """Strip forbidden keys that might contain prompt/evidence content."""
        safe: dict[str, Any] = {}
        for key, value in details.items():
            lowered = key.lower()
            if lowered in _FORBIDDEN_DETAIL_KEYS or "prompt" in lowered:
                continue
            if isinstance(value, str) and len(value) > 500:
                # Avoid accidentally logging large blobs
                safe[key] = f"<omitted:{len(value)} chars>"
                continue
            safe[key] = value
        return safe
