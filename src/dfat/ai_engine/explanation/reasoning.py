"""Format AI reasoning chains into investigator-friendly explainable outputs.

Known limitation: narrative reasoning is advisory; structured JSON remains the
authoritative evidential record (Scanlon et al., 2023).
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.core.models.artefact import Artefact, RankedArtefact

_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_ART_ID_RE = re.compile(r"\b(?:art|artefact)[-_][\w-]+\b", re.IGNORECASE)
_UNCERTAIN_RE = re.compile(r"\[UNCERTAIN\]|uncertain|insufficient data", re.IGNORECASE)


class ExplainableOutput(BaseModel):
    """Investigator-facing explainable AI formatting result."""

    model_config = ConfigDict(frozen=False)

    formatted_text: str
    confidence: float = 0.0
    evidence_citations: list[str] = Field(default_factory=list)
    uncertainty_markers: list[str] = Field(default_factory=list)
    model_attribution: str = ""


class ReasoningChainFormatter:
    """Format classification, ranking, and summary reasoning for investigators."""

    def format_classification_reasoning(
        self,
        result: ClassificationResult,
        artefact: Artefact,
        confidence: float,
        *,
        model_attribution: str = "local-llama3",
    ) -> ExplainableOutput:
        """Structure classification reasoning with IOCs and confidence.

        Example shape::

            Artefact {id} classified as {level} because: {reasoning}.
            IOC indicators: {iocs}. Confidence: {confidence:.0%}.
        """
        level = result.suspicion_level.value.upper()
        reasoning = (result.reasoning or "").strip() or "No reasoning provided"
        iocs = result.ioc_indicators or []
        ioc_text = ", ".join(iocs) if iocs else "none identified"
        clamped = self._clamp(confidence)

        formatted = (
            f"Artefact {result.artefact_id} classified as {level} because: "
            f"{reasoning}. IOC indicators: {ioc_text}. "
            f"Confidence: {clamped:.0%}."
        )
        if artefact.source_path:
            formatted += f" Source path: {artefact.source_path}."

        citations = self._citations(
            [result.artefact_id, artefact.artefact_id],
            reasoning,
            " ".join(iocs),
        )
        markers = self._uncertainty_markers(reasoning)

        return ExplainableOutput(
            formatted_text=formatted,
            confidence=clamped,
            evidence_citations=citations,
            uncertainty_markers=markers,
            model_attribution=model_attribution,
        )

    def format_ranking_reasoning(
        self,
        ranked: RankedArtefact,
        *,
        model_attribution: str = "local-llama3",
    ) -> ExplainableOutput:
        """Format ranking score and classification reasoning."""
        level = ranked.suspicion_level.value.upper()
        reasoning = (ranked.classification_reasoning or "").strip() or (
            "No ranking reasoning provided"
        )
        formatted = (
            f"Artefact {ranked.artefact_id} ranked with score "
            f"{ranked.relevance_score:.2f} ({level}). Reasoning: {reasoning}."
        )
        citations = self._citations([ranked.artefact_id], reasoning)
        markers = self._uncertainty_markers(reasoning)

        return ExplainableOutput(
            formatted_text=formatted,
            confidence=self._clamp(ranked.relevance_score),
            evidence_citations=citations,
            uncertainty_markers=markers,
            model_attribution=model_attribution,
        )

    def format_summary_reasoning(
        self,
        summary: SummaryResult,
        *,
        model_attribution: Optional[str] = None,
    ) -> ExplainableOutput:
        """Format a full summary with confidence annotations and ID citations."""
        attribution = model_attribution or summary.model_used or "local-llama3"
        confidence = self._clamp(summary.confidence_score)

        parts: list[str] = [
            f"[AI confidence: {confidence:.0%} | model: {attribution} | "
            f"prompt {summary.prompt_version}]",
            "",
            "## Executive Summary",
            summary.executive_summary.strip() or "(empty)",
            "",
            "## Key Findings",
        ]
        if summary.key_findings:
            parts.extend(f"- {item}" for item in summary.key_findings)
        else:
            parts.append("- (none)")

        parts.extend(
            [
                "",
                "## Timeline of Events",
                (summary.timeline_narrative or "(unavailable)").strip(),
                "",
                "## Indicators of Compromise",
            ]
        )
        if summary.iocs_identified:
            parts.extend(f"- {item}" for item in summary.iocs_identified)
        else:
            parts.append("- (none)")

        parts.extend(["", "## Recommended Next Steps"])
        if summary.recommended_actions:
            parts.extend(f"- {item}" for item in summary.recommended_actions)
        else:
            parts.append("- (none)")

        parts.extend(
            [
                "",
                f"_Confidence annotation: {confidence:.0%}. "
                "Verify claims against the structured JSON artefact layer "
                "(Scanlon et al., 2023)._",
            ]
        )

        formatted = "\n".join(parts)
        blob = "\n".join(
            [
                summary.full_text,
                summary.executive_summary,
                " ".join(summary.key_findings),
                summary.timeline_narrative or "",
                " ".join(summary.iocs_identified),
                " ".join(summary.recommended_actions),
            ]
        )
        citations = self._citations([], blob)
        markers = self._uncertainty_markers(blob)

        return ExplainableOutput(
            formatted_text=formatted,
            confidence=confidence,
            evidence_citations=citations,
            uncertainty_markers=markers,
            model_attribution=attribution,
        )

    @staticmethod
    def _citations(*texts: str | list[str]) -> list[str]:
        """Collect unique artefact ID citations from text fragments."""
        found: list[str] = []
        for item in texts:
            if isinstance(item, list):
                for value in item:
                    if value and value not in found:
                        found.append(str(value))
                continue
            text = item or ""
            for match in _UUID_RE.findall(text):
                if match not in found:
                    found.append(match)
            for match in _ART_ID_RE.findall(text):
                if match not in found:
                    found.append(match)
            # Bare IDs passed directly
            if text and re.fullmatch(r"[\w-]+", text) and text not in found:
                if text.startswith(("art-", "art_", "artefact-")) or _UUID_RE.fullmatch(
                    text
                ):
                    found.append(text)
        return found

    @staticmethod
    def _uncertainty_markers(text: str) -> list[str]:
        """Extract uncertainty marker phrases from text."""
        markers: list[str] = []
        for match in _UNCERTAIN_RE.finditer(text or ""):
            token = match.group(0)
            if token not in markers:
                markers.append(token)
        return markers

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))
