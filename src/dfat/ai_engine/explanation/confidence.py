"""Confidence scoring for AI classification, summary, and explanation outputs.

Scores combine response-quality indicators, consistency with category heuristics,
and hallucination-risk penalties (Scanlon et al., 2023).
"""

from __future__ import annotations

import re
from typing import Optional

from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.explanation.explainer import ArtefactExplanation
from dfat.ai_engine.summarization.summarizer import SummaryResult
from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact

_FALLBACK_REASONINGS = frozenset(
    {
        "Classification failed — insufficient AI confidence.",
        "Not classified by AI",
    }
)

_HALLUCINATION_MARKERS = (
    "as an ai language model",
    "i cannot actually access",
    "i made up",
    "fabricated example",
)

# Category → suspicion levels a simple rule-based heuristic would expect.
_CATEGORY_HEURISTICS: dict[ArtefactCategory, frozenset[SuspicionLevel]] = {
    ArtefactCategory.INJECTED_CODE: frozenset(
        {SuspicionLevel.CRITICAL, SuspicionLevel.HIGH}
    ),
    ArtefactCategory.NETWORK_CONNECTION: frozenset(
        {SuspicionLevel.HIGH, SuspicionLevel.MEDIUM, SuspicionLevel.LOW}
    ),
    ArtefactCategory.REGISTRY_KEY: frozenset(
        {SuspicionLevel.HIGH, SuspicionLevel.MEDIUM, SuspicionLevel.LOW}
    ),
    ArtefactCategory.RUNNING_PROCESS: frozenset(
        {SuspicionLevel.MEDIUM, SuspicionLevel.LOW, SuspicionLevel.INFORMATIONAL}
    ),
    ArtefactCategory.EVENT_LOG: frozenset(
        {SuspicionLevel.HIGH, SuspicionLevel.MEDIUM, SuspicionLevel.LOW}
    ),
    ArtefactCategory.BROWSER_HISTORY: frozenset(
        {SuspicionLevel.MEDIUM, SuspicionLevel.LOW, SuspicionLevel.INFORMATIONAL}
    ),
    ArtefactCategory.FILESYSTEM_METADATA: frozenset(
        {SuspicionLevel.LOW, SuspicionLevel.INFORMATIONAL}
    ),
}

_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_ART_ID_RE = re.compile(r"\b(?:art|artefact)[-_][\w-]+\b", re.IGNORECASE)


class ConfidenceScorer:
    """Compute confidence scores for AI triage outputs."""

    def score_classification(
        self,
        result: ClassificationResult,
        artefact: Artefact,
    ) -> float:
        """Score a classification result in ``[0.0, 1.0]``.

        Factors:
            - Reasoning length (short → lower base)
            - Artefact ID referenced in reasoning (+0.2)
            - IOC indicator specificity (+0.1 each)
            - Consistency with category heuristics (+0.2)
            - Parseable / non-fallback response (+0.1)
            - Invalid ID references in reasoning (penalty)
        """
        reasoning = (result.reasoning or "").strip()
        if not reasoning or reasoning in _FALLBACK_REASONINGS:
            return 0.1

        score = self._reasoning_length_base(reasoning)

        if artefact.artefact_id and artefact.artefact_id in reasoning:
            score += 0.2

        score += 0.1 * len(result.ioc_indicators or [])

        expected = _CATEGORY_HEURISTICS.get(artefact.category)
        if expected and result.suspicion_level in expected:
            score += 0.2

        if result.raw_llm_response and reasoning not in _FALLBACK_REASONINGS:
            score += 0.1

        valid_ids = {artefact.artefact_id}
        _valid, invalid = self._check_artefact_id_references(reasoning, valid_ids)
        if invalid:
            score -= 0.15 * invalid

        if "[UNCERTAIN]" in reasoning.upper():
            score -= 0.1

        return self._clamp(score)

    def score_summary(self, summary: SummaryResult, artefact_count: int) -> float:
        """Score a summary result in ``[0.0, 1.0]``.

        Factors:
            - Each of 5 sections present (+0.2 each)
            - Artefact ID references (+0.1 each, max +0.3)
            - No hallucination markers (+0.2)
            - Reasonable length (+0.1)
            - Invalid ID references (penalty)
        """
        score = 0.0
        if summary.executive_summary.strip():
            score += 0.2
        if summary.key_findings:
            score += 0.2
        if summary.timeline_narrative and str(summary.timeline_narrative).strip():
            score += 0.2
        if summary.iocs_identified:
            score += 0.2
        if summary.recommended_actions:
            score += 0.2

        text = summary.full_text or ""
        # Without known IDs, treat UUID/art-* mentions as references up to cap.
        valid_ids: set[str] = set()
        for match in _UUID_RE.findall(text):
            valid_ids.add(match)
        for match in _ART_ID_RE.findall(text):
            valid_ids.add(match)
        # Prefer counting references against an empty known set using presence:
        # when artefact_count > 0, reward by how many ID-like tokens appear.
        id_hits = len(_UUID_RE.findall(text)) + len(_ART_ID_RE.findall(text))
        score += min(0.3, 0.1 * id_hits)

        lowered = text.lower()
        if not any(marker in lowered for marker in _HALLUCINATION_MARKERS):
            score += 0.2
        else:
            score -= 0.2

        word_count = len(text.split())
        # Reasonable band scales lightly with artefact_count.
        lower = max(40, min(80, artefact_count * 2))
        upper = max(400, artefact_count * 40)
        if lower <= word_count <= upper:
            score += 0.1

        # Hallucinated IDs: references that look like IDs but aren't in valid set
        # when a non-empty known set is provided via key findings context.
        known_from_findings = set(_ART_ID_RE.findall(" ".join(summary.key_findings)))
        known_from_findings.update(_UUID_RE.findall(" ".join(summary.key_findings)))
        if known_from_findings:
            _valid, invalid = self._check_artefact_id_references(text, known_from_findings)
            if invalid:
                score -= 0.1 * invalid

        return self._clamp(score)

    def score_explanation(self, explanation: ArtefactExplanation) -> float:
        """Score an explanation based on completeness and specificity."""
        text = (explanation.explanation_text or "").strip()
        if not text:
            return 0.1

        score = self._reasoning_length_base(text)

        if (explanation.forensic_significance or "").strip():
            score += 0.2
        if explanation.suggested_actions:
            score += 0.1 * min(3, len(explanation.suggested_actions))

        valid_ids = {explanation.artefact_id} if explanation.artefact_id else set()
        valid_refs, invalid_refs = self._check_artefact_id_references(text, valid_ids)
        if explanation.artefact_id and (
            explanation.artefact_id in text or valid_refs > 0
        ):
            score += 0.2
        if invalid_refs:
            score -= 0.15 * invalid_refs

        if explanation.related_artefact_ids:
            score += min(0.1, 0.05 * len(explanation.related_artefact_ids))

        if "[UNCERTAIN]" in text.upper():
            score -= 0.1

        # Prefer provided confidence as a soft prior (do not dominate).
        if explanation.confidence > 0:
            score = (0.7 * score) + (0.3 * explanation.confidence)

        return self._clamp(score)

    def _check_artefact_id_references(
        self,
        text: str,
        valid_ids: set[str],
    ) -> tuple[int, int]:
        """Count valid and invalid artefact ID references in ``text``.

        Returns:
            ``(valid_references, invalid_references)``. Invalid references
            suggest hallucination.
        """
        if not text:
            return (0, 0)

        found: list[str] = []
        found.extend(_UUID_RE.findall(text))
        found.extend(_ART_ID_RE.findall(text))

        # Also count exact valid ID substrings that may not match the regexes.
        for artefact_id in valid_ids:
            if artefact_id and artefact_id in text and artefact_id not in found:
                found.append(artefact_id)

        valid_count = 0
        invalid_count = 0
        seen: set[str] = set()
        for item in found:
            if item in seen:
                continue
            seen.add(item)
            if item in valid_ids:
                valid_count += 1
            else:
                invalid_count += 1
        return (valid_count, invalid_count)

    @staticmethod
    def _reasoning_length_base(text: str) -> float:
        """Map reasoning length to a conservative base score."""
        length = len(text.strip())
        if length < 20:
            return 0.15
        if length < 40:
            return 0.25
        if length < 80:
            return 0.35
        if length < 160:
            return 0.45
        return 0.5

    @staticmethod
    def _clamp(value: float) -> float:
        """Clamp ``value`` to ``[0.0, 1.0]``."""
        return max(0.0, min(1.0, float(value)))

    def score(self, result: ClassificationResult, artefact: Optional[Artefact] = None) -> float:
        """Compatibility helper for classifiers that call ``score(result)``.

        When ``artefact`` is omitted, a minimal placeholder is synthesised from
        the classification result alone (no category consistency bonus).
        """
        if artefact is None:
            artefact = Artefact(
                artefact_id=result.artefact_id,
                category=ArtefactCategory.FILESYSTEM_METADATA,
                source_evidence_id="n/a",
                raw_data={},
            )
        return self.score_classification(result, artefact)
