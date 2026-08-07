"""LLM investigative summary generation."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.llm.client import OllamaClient
from dfat.ai_engine.llm.config import LLMConfig
from dfat.ai_engine.llm.prompts import PROMPT_VERSION
from dfat.ai_engine.summarization.prompts import SummarizationPromptBuilder
from dfat.ai_engine.summarization.validator import SummaryResponseValidator
from dfat.core.enums import PipelineStage
from dfat.core.models.artefact import RankedArtefact
from dfat.forensic_engine.processing.timeline import Timeline
from dfat.forensic_engine.triage.aggregator import TriageSummary
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger

logger = logging.getLogger(__name__)


class SummaryResult(BaseModel):
    """Structured investigative summary produced by the LLM summarizer."""

    model_config = ConfigDict(frozen=False)

    full_text: str
    executive_summary: str
    key_findings: list[str] = Field(default_factory=list)
    timeline_narrative: Optional[str] = None
    iocs_identified: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    model_used: str
    prompt_version: str
    generation_params: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = 0.0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SummaryValidator(Protocol):
    """Protocol for summary response validators."""

    def validate(self, text: str) -> dict[str, object]:
        """Validate and structure summary text."""


class LLMInvestigativeSummarizer:
    """Generate structured investigative narratives via the local LLM."""

    def __init__(
        self,
        ollama_client: OllamaClient,
        prompt_builder: SummarizationPromptBuilder,
        response_validator: SummaryValidator,
        audit_logger: ForensicAuditLogger,
        config: LLMConfig,
    ) -> None:
        """Initialise the summarizer.

        Args:
            ollama_client: Low-level Ollama HTTP client.
            prompt_builder: Summarization prompt builder.
            response_validator: Summary response validator/structure extractor.
            audit_logger: Forensic audit logger (metadata only).
            config: LLM configuration.
        """
        self._ollama = ollama_client
        self._prompt_builder = prompt_builder
        self._validator = response_validator
        self._audit_logger = audit_logger
        self._config = config

    async def generate_summary(
        self,
        ranked: list[RankedArtefact],
        timeline: Optional[Timeline] = None,
        triage_summary: Optional[TriageSummary] = None,
    ) -> SummaryResult:
        """Generate a structured investigative summary.

        Args:
            ranked: Ranked artefacts.
            timeline: Optional timeline context.
            triage_summary: Optional triage aggregation context.

        Returns:
            ``SummaryResult`` with the five narrative sections and metadata.
        """
        started = time.perf_counter()
        prompt = self._prompt_builder.build_summary_prompt(
            ranked,
            timeline=timeline,
            triage_summary=triage_summary,
        )

        full_text = ""
        model_used = self._config.model
        try:
            response = await self._ollama.generate(prompt)
            full_text = response.text
            model_used = response.model or self._config.model
        except Exception as exc:  # noqa: BLE001 — soft failure with placeholder
            logger.warning("LLM summary generation failed: %s", exc)
            full_text = self._fallback_summary(ranked)

        structured = self._validator.validate(full_text)
        result = SummaryResult(
            full_text=full_text,
            executive_summary=str(structured.get("executive_summary") or ""),
            key_findings=list(structured.get("key_findings") or []),  # type: ignore[arg-type]
            timeline_narrative=(
                str(structured["timeline_narrative"])
                if structured.get("timeline_narrative")
                else None
            ),
            iocs_identified=list(structured.get("iocs_identified") or []),  # type: ignore[arg-type]
            recommended_actions=list(structured.get("recommended_actions") or []),  # type: ignore[arg-type]
            model_used=model_used,
            prompt_version=PROMPT_VERSION,
            generation_params={
                "temperature": self._config.temperature,
                "top_p": self._config.top_p,
                "num_predict": self._config.num_predict,
                "repeat_penalty": self._config.repeat_penalty,
            },
            confidence_score=float(structured.get("confidence_score") or 0.0),
            generated_at=datetime.now(UTC),
        )

        duration_ms = (time.perf_counter() - started) * 1000.0
        self._audit_logger.log_action(
            stage=PipelineStage.AI_TRIAGE,
            action="LLM_SUMMARY",
            evidence_id="n/a",
            details={
                "artefact_count": len(ranked),
                "model": result.model_used,
                "prompt_version": result.prompt_version,
                "confidence_score": result.confidence_score,
                "duration_ms": round(duration_ms, 2),
                "section_counts": {
                    "key_findings": len(result.key_findings),
                    "iocs": len(result.iocs_identified),
                    "actions": len(result.recommended_actions),
                },
            },
        )
        return result

    @staticmethod
    def _fallback_summary(ranked: list[RankedArtefact]) -> str:
        """Build a minimal structured summary when the LLM is unavailable."""
        critical = sum(
            1 for item in ranked if item.suspicion_level.value == "critical"
        )
        high = sum(1 for item in ranked if item.suspicion_level.value == "high")
        return (
            "1. EXECUTIVE SUMMARY\n"
            f"Triage covered {len(ranked)} artefacts "
            f"({critical} critical, {high} high). "
            "LLM summary unavailable; this is a rule/fallback narrative.\n\n"
            "2. KEY FINDINGS\n"
            "- Review CRITICAL and HIGH artefacts in the JSON evidential layer.\n\n"
            "3. TIMELINE OF EVENTS\n"
            "- Insufficient narrative timeline without LLM enrichment.\n\n"
            "4. INDICATORS OF COMPROMISE\n"
            "- See structured IOC detector output in the JSON report.\n\n"
            "5. RECOMMENDED NEXT STEPS\n"
            "- Validate HIGH+ findings manually and preserve chain of custody.\n"
        )
