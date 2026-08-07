"""Validate and structure investigative summary LLM responses."""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_HALLUCINATION_MARKERS = (
    "as an ai language model",
    "i cannot actually access",
    "i made up",
    "fabricated example",
)

_SECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "executive_summary",
        re.compile(
            r"(?:^|\n)\s*(?:1[.)]?\s*)?EXECUTIVE\s+SUMMARY\s*:?\s*(.*?)(?=\n\s*(?:2[.)]?\s*)?KEY\s+FINDINGS|\n\s*#{0,3}\s*KEY\s+FINDINGS|\Z)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "key_findings",
        re.compile(
            r"(?:^|\n)\s*(?:2[.)]?\s*)?KEY\s+FINDINGS\s*:?\s*(.*?)(?=\n\s*(?:3[.)]?\s*)?TIMELINE|\Z)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "timeline_narrative",
        re.compile(
            r"(?:^|\n)\s*(?:3[.)]?\s*)?TIMELINE(?:\s+OF\s+EVENTS)?\s*:?\s*(.*?)(?=\n\s*(?:4[.)]?\s*)?INDICATORS|\Z)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "iocs",
        re.compile(
            r"(?:^|\n)\s*(?:4[.)]?\s*)?INDICATORS\s+OF\s+COMPROMISE\s*:?\s*(.*?)(?=\n\s*(?:5[.)]?\s*)?RECOMMENDED|\Z)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "recommended_actions",
        re.compile(
            r"(?:^|\n)\s*(?:5[.)]?\s*)?RECOMMENDED\s+NEXT\s+STEPS\s*:?\s*(.*?)\Z",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)


class SummaryResponseValidator:
    """Validate summary text and extract the five required narrative sections."""

    def validate(self, text: str) -> dict[str, object]:
        """Validate and structure a summary response.

        Args:
            text: Raw LLM summary text.

        Returns:
            Dict with section fields, ``confidence_score``, and ``warnings``.
        """
        cleaned = (text or "").strip()
        warnings: list[str] = []
        lowered = cleaned.lower()
        for marker in _HALLUCINATION_MARKERS:
            if marker in lowered:
                warnings.append(f"Possible hallucination marker: {marker}")
                logger.warning("Possible hallucination marker detected: %s", marker)

        sections = {name: self._extract(pattern, cleaned) for name, pattern in _SECTION_PATTERNS}
        # Fallback: if headings missing, use whole text as executive summary.
        if not any(sections.values()) and cleaned:
            sections["executive_summary"] = cleaned
            warnings.append("Summary missing explicit section headings; used full text")

        key_findings = self._to_bullets(str(sections.get("key_findings") or ""))
        iocs = self._to_bullets(str(sections.get("iocs") or ""))
        actions = self._to_bullets(str(sections.get("recommended_actions") or ""))
        timeline = str(sections.get("timeline_narrative") or "").strip() or None
        executive = str(sections.get("executive_summary") or "").strip()

        present = sum(
            1
            for value in (
                executive,
                key_findings,
                timeline,
                iocs,
                actions,
            )
            if value
        )
        confidence = max(0.2, min(1.0, present / 5.0))
        if warnings:
            confidence = max(0.1, confidence - 0.2 * len(warnings))

        return {
            "executive_summary": executive,
            "key_findings": key_findings,
            "timeline_narrative": timeline,
            "iocs_identified": iocs,
            "recommended_actions": actions,
            "confidence_score": round(confidence, 3),
            "warnings": warnings,
        }

    @staticmethod
    def _extract(pattern: re.Pattern[str], text: str) -> str:
        match = pattern.search(text)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _to_bullets(block: str) -> list[str]:
        """Split a section into bullet-like lines."""
        if not block.strip():
            return []
        items: list[str] = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            stripped = re.sub(r"^[-*•]\s+", "", stripped)
            stripped = re.sub(r"^\d+[.)]\s+", "", stripped)
            if stripped:
                items.append(stripped)
        if not items and block.strip():
            items.append(block.strip())
        return items
