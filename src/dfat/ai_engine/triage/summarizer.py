"""Investigative summary generation via local LLM."""

from __future__ import annotations

import logging
import re

from dfat.ai_engine.llm.client import LocalLLMClient
from dfat.core.models.artefact import RankedArtefact

logger = logging.getLogger(__name__)

_HALLUCINATION_MARKERS = (
    "as an ai language model",
    "i cannot actually access",
    "i made up",
    "fabricated example",
)


class InvestigativeSummarizer:
    """Generate and lightly validate investigative narrative summaries."""

    def __init__(self, llm_client: LocalLLMClient) -> None:
        """Initialise the summarizer.

        Args:
            llm_client: Local LLaMA-3 client.
        """
        self._llm_client = llm_client

    def generate_summary(self, ranked: list[RankedArtefact]) -> str:
        """Generate an investigative summary for ranked artefacts.

        Args:
            ranked: Triaged artefacts.

        Returns:
            Validated narrative summary string.
        """
        summary = self._llm_client.summarize(ranked)
        return self._validate_summary(summary)

    def _validate_summary(self, summary: str) -> str:
        """Validate summary length and obvious hallucination markers.

        Args:
            summary: Candidate summary text.

        Returns:
            Cleaned summary, or a conservative placeholder when invalid.
        """
        cleaned = summary.strip()
        if not cleaned:
            logger.warning("Empty LLM summary; returning placeholder")
            return "Summary unavailable: empty model response."
        if len(cleaned) > 50_000:
            logger.warning("LLM summary excessively long; truncating")
            cleaned = cleaned[:50_000] + "\n\n[truncated]"
        lowered = cleaned.lower()
        for marker in _HALLUCINATION_MARKERS:
            if marker in lowered:
                logger.warning("Possible hallucination marker detected: %s", marker)
                cleaned = (
                    cleaned
                    + "\n\n[Note: Potential model disclaimer detected; "
                    "treat narrative as advisory only.]"
                )
                break
        # Collapse extreme whitespace while preserving paragraphs.
        cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
        return cleaned
