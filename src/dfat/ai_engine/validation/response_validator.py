"""Validate AI classification, summary, and explanation responses."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.explanation.confidence import ConfidenceScorer
from dfat.ai_engine.explanation.explainer import ArtefactExplanation
from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.ai_engine.validation.hallucination_guard import (
    HallucinationGuard,
    HallucinationReport,
)
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, RankedArtefact


class ValidationResult(BaseModel):
    """Outcome of validating an AI module response."""

    model_config = ConfigDict(frozen=False)

    is_valid: bool
    confidence: float = 0.0
    hallucination_report: Optional[HallucinationReport] = None
    warnings: list[str] = Field(default_factory=list)
    corrections_applied: list[str] = Field(default_factory=list)


class AIResponseValidator:
    """Validate AI outputs using hallucination checks and confidence scoring."""

    def __init__(
        self,
        hallucination_guard: HallucinationGuard,
        confidence_scorer: ConfidenceScorer,
    ) -> None:
        """Initialise the validator.

        Args:
            hallucination_guard: Reference/assertion hallucination detector.
            confidence_scorer: Confidence scoring helper.
        """
        self._guard = hallucination_guard
        self._confidence = confidence_scorer

    def validate_classification(
        self,
        results: list[ClassificationResult],
        artefacts: list[Artefact],
    ) -> ValidationResult:
        """Validate classification results against source artefacts."""
        by_id = {item.artefact_id: item for item in artefacts}
        warnings: list[str] = []
        corrections: list[str] = []
        texts: list[str] = []
        confidences: list[float] = []

        known_facts = self._collect_known_facts(artefacts)
        guard = self._guard.with_known_facts(known_facts)

        for result in results:
            artefact = by_id.get(result.artefact_id)
            if artefact is None:
                warnings.append(
                    f"Classification references unknown artefact_id={result.artefact_id}"
                )
                continue
            confidences.append(self._confidence.score_classification(result, artefact))
            blob = " ".join(
                [
                    result.reasoning or "",
                    " ".join(result.ioc_indicators or []),
                    result.raw_llm_response or "",
                ]
            )
            texts.append(blob)
            if result.artefact_id not in {
                item.artefact_id for item in artefacts
            }:
                corrections.append(f"Dropped unknown classification {result.artefact_id}")

        report = guard.check_response("\n".join(texts))
        warnings.extend(self._warnings_from_report(report))
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        if report.risk_level == "high":
            confidence = min(confidence, 0.3)
            is_valid = False
        elif report.risk_level == "medium":
            confidence = min(confidence, 0.6)
            is_valid = len(report.hallucinated_ids) == 0
        else:
            is_valid = True

        if report.hallucinated_ids:
            corrections.append(
                "Marked hallucinated artefact IDs in aggregated classification text"
            )

        return ValidationResult(
            is_valid=is_valid,
            confidence=max(0.0, min(1.0, confidence)),
            hallucination_report=report,
            warnings=warnings,
            corrections_applied=corrections,
        )

    def validate_summary(
        self,
        summary: SummaryResult,
        ranked: list[RankedArtefact],
    ) -> ValidationResult:
        """Validate an investigative summary against ranked artefacts."""
        known_facts = self._collect_known_facts(ranked)
        guard = HallucinationGuard(
            valid_artefact_ids={item.artefact_id for item in ranked}
            | set(getattr(self._guard, "_valid_ids", set())),
            valid_categories=set(getattr(self._guard, "_valid_categories", set())),
            valid_suspicion_levels=set(getattr(self._guard, "_valid_levels", set())),
            known_facts=known_facts,
        )
        report = guard.check_response(summary.full_text)
        confidence = self._confidence.score_summary(summary, artefact_count=len(ranked))
        warnings = self._warnings_from_report(report)
        corrections: list[str] = []
        if report.hallucinated_ids or report.fabricated_terms:
            corrections.append("Produced cleaned summary text with hallucination markers")
            # Caller may replace full_text with report.clean_response
        if report.risk_level == "high":
            confidence = min(confidence, 0.3)
            is_valid = False
        elif report.risk_level == "medium":
            confidence = min(confidence, 0.65)
            is_valid = len(report.hallucinated_ids) == 0
        else:
            is_valid = True

        return ValidationResult(
            is_valid=is_valid,
            confidence=max(0.0, min(1.0, confidence)),
            hallucination_report=report,
            warnings=warnings,
            corrections_applied=corrections,
        )

    def validate_explanation(
        self,
        explanation: ArtefactExplanation,
        artefact: RankedArtefact,
    ) -> ValidationResult:
        """Validate a per-artefact explanation."""
        known_facts = self._collect_known_facts([artefact])
        guard = HallucinationGuard(
            valid_artefact_ids={artefact.artefact_id} | set(explanation.related_artefact_ids),
            valid_categories=set(self._guard._valid_categories),
            valid_suspicion_levels=set(self._guard._valid_levels),
            known_facts=known_facts,
        )
        report = guard.check_response(explanation.explanation_text)
        # Related IDs claimed but not in ranked context beyond self are already
        # handled if they appear as hallucinated when not in valid set — allow
        # related_artefact_ids declared on the explanation object.
        confidence = self._confidence.score_explanation(explanation)
        warnings = self._warnings_from_report(report)
        corrections: list[str] = []
        if report.hallucinated_ids:
            corrections.append("Marked hallucinated IDs in explanation text")
        if report.risk_level == "high":
            confidence = min(confidence, 0.3)
            is_valid = False
        else:
            is_valid = report.risk_level == "low" or not report.hallucinated_ids

        return ValidationResult(
            is_valid=is_valid,
            confidence=max(0.0, min(1.0, confidence)),
            hallucination_report=report,
            warnings=warnings,
            corrections_applied=corrections,
        )

    @staticmethod
    def default_guard(
        artefact_ids: Optional[set[str]] = None,
    ) -> HallucinationGuard:
        """Build a guard seeded with DFAT category and suspicion vocabularies."""
        return HallucinationGuard(
            valid_artefact_ids=set(artefact_ids or set()),
            valid_categories={item.value for item in ArtefactCategory},
            valid_suspicion_levels={item.value for item in SuspicionLevel},
        )

    @staticmethod
    def _warnings_from_report(report: HallucinationReport) -> list[str]:
        warnings: list[str] = []
        if report.hallucinated_ids:
            warnings.append(
                "Hallucinated artefact IDs: " + ", ".join(report.hallucinated_ids)
            )
        if report.fabricated_terms:
            warnings.append(
                "Fabricated terms: " + ", ".join(report.fabricated_terms)
            )
        if report.unsupported_assertions:
            warnings.append(
                f"{len(report.unsupported_assertions)} unsupported assertion(s)"
            )
        if report.risk_level != "low":
            warnings.append(f"Hallucination risk_level={report.risk_level}")
        return warnings

    @staticmethod
    def _collect_known_facts(artefacts: list[Any]) -> set[str]:
        """Extract IP/domain/hash-like tokens from artefact raw_data."""
        facts: set[str] = set()
        ip_re = re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        )
        domain_re = re.compile(
            r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,})\b",
            re.IGNORECASE,
        )
        hash_re = re.compile(
            r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b"
        )
        for artefact in artefacts:
            raw = getattr(artefact, "raw_data", {}) or {}
            blob = json.dumps(raw, default=str)
            facts.update(ip.lower() for ip in ip_re.findall(blob))
            facts.update(d.lower() for d in domain_re.findall(blob))
            facts.update(h.lower() for h in hash_re.findall(blob))
            for value in raw.values():
                if isinstance(value, str) and value.strip():
                    facts.add(value.strip().lower())
        return facts
