"""Parse LLM ranking responses into score maps."""

from __future__ import annotations

import logging
from typing import Any, Optional

from dfat.ai_engine.llm.response_parser import LLMResponseParser

logger = logging.getLogger(__name__)


class RankingResponseParser:
    """Extract ``artefact_id → relevance_score`` (and reasoning) from LLM text."""

    def __init__(self, llm_parser: Optional[LLMResponseParser] = None) -> None:
        """Initialise the ranking response parser.

        Args:
            llm_parser: Shared generic LLM JSON extractor.
        """
        self._llm_parser = llm_parser or LLMResponseParser()

    def parse(
        self,
        response_text: str,
        artefact_ids: list[str],
    ) -> dict[str, tuple[float, str]]:
        """Parse ranking JSON into scores and priority reasoning.

        Args:
            response_text: Raw LLM ranking response.
            artefact_ids: Known artefact IDs (hallucinated IDs discarded).

        Returns:
            Mapping of ``artefact_id → (score, priority_reasoning)``.
        """
        known = set(artefact_ids)
        items = self._llm_parser.extract_json_array(response_text)
        if not items:
            # Also accept {"rankings": [...]}
            obj = self._llm_parser.extract_json_object(response_text)
            nested = obj.get("rankings") if isinstance(obj, dict) else None
            if isinstance(nested, list):
                items = [item for item in nested if isinstance(item, dict)]

        scores: dict[str, tuple[float, str]] = {}
        for item in items:
            artefact_id = str(item.get("artefact_id", "")).strip()
            if not artefact_id or artefact_id not in known:
                if artefact_id and artefact_id not in known:
                    logger.warning(
                        "Discarding hallucinated ranking artefact_id=%s",
                        artefact_id,
                    )
                continue
            score = self._parse_score(item.get("relevance_score"))
            if score is None:
                continue
            reasoning = str(
                item.get("priority_reasoning") or item.get("reasoning") or ""
            ).strip()
            scores[artefact_id] = (score, reasoning)
        return scores

    @staticmethod
    def _parse_score(value: Any) -> Optional[float]:
        """Parse and clamp a relevance score to ``[0.0, 1.0]``."""
        try:
            score = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, score))
