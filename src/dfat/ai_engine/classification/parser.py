"""Parse and validate LLM classification responses."""

from __future__ import annotations

import logging
from typing import Any, Optional

from dfat.ai_engine.classification.models import ClassificationResult
from dfat.ai_engine.llm.response_parser import LLMResponseParser
from dfat.core.enums import SuspicionLevel

logger = logging.getLogger(__name__)

_MISSING_REASONING = "Not classified by AI"
_EMPTY_REASONING_FALLBACK = "Classification failed — insufficient AI confidence."


class ClassificationResponseParser:
    """Parse and validate LLM classification responses into results."""

    def __init__(self, llm_parser: Optional[LLMResponseParser] = None) -> None:
        """Initialise the parser.

        Args:
            llm_parser: Optional shared generic LLM response parser.
        """
        self._llm_parser = llm_parser or LLMResponseParser()

    def parse(
        self,
        response_text: str,
        artefact_ids: list[str],
    ) -> list[ClassificationResult]:
        """Parse a classification response covering all input artefact IDs.

        Args:
            response_text: Raw LLM response text.
            artefact_ids: Expected artefact identifiers (output order preserved).

        Returns:
            One ``ClassificationResult`` per input ID. Unknown/hallucinated IDs
            from the model are discarded. Missing IDs default to INFORMATIONAL.
        """
        known = list(artefact_ids)
        known_set = set(known)
        items = self._extract_json(response_text)

        by_id: dict[str, ClassificationResult] = {}
        for item in items:
            artefact_id = str(item.get("artefact_id", "")).strip()
            if not artefact_id:
                continue
            if artefact_id not in known_set:
                logger.warning(
                    "Discarding hallucinated classification artefact_id=%s",
                    artefact_id,
                )
                continue

            suspicion = self._parse_suspicion(item.get("suspicion_level"))
            reasoning = str(
                item.get("reasoning") or item.get("priority_reasoning") or ""
            ).strip()
            if not reasoning:
                reasoning = _EMPTY_REASONING_FALLBACK
                suspicion = SuspicionLevel.INFORMATIONAL

            iocs = item.get("ioc_indicators", [])
            if not isinstance(iocs, list):
                iocs = []

            by_id[artefact_id] = ClassificationResult(
                artefact_id=artefact_id,
                suspicion_level=suspicion,
                reasoning=reasoning,
                ioc_indicators=[str(x) for x in iocs],
                raw_llm_response=response_text,
            )

        results: list[ClassificationResult] = []
        for artefact_id in known:
            if artefact_id in by_id:
                results.append(by_id[artefact_id])
            else:
                results.append(
                    ClassificationResult(
                        artefact_id=artefact_id,
                        suspicion_level=SuspicionLevel.INFORMATIONAL,
                        reasoning=_MISSING_REASONING,
                        ioc_indicators=[],
                        raw_llm_response=response_text,
                    )
                )
        return results

    def _extract_json(self, text: str) -> list[dict[str, Any]]:
        """Extract classification objects using multiple strategies.

        Strategies:
            a. Direct ``json.loads``
            b. Markdown `` ```json `` blocks
            c. First ``[`` … last ``]``
            d. Line-by-line JSON objects
        """
        # a/b/c/d are implemented inside LLMResponseParser.extract_json_array
        # with progressive fallbacks and repair.
        try:
            import json

            loaded = json.loads(text.strip())
            if isinstance(loaded, list):
                return [item for item in loaded if isinstance(item, dict)]
            if isinstance(loaded, dict):
                nested = loaded.get("classifications") or loaded.get("results")
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
        except Exception:  # noqa: BLE001 — fall through to strategies
            logger.warning("Classification JSON: direct json.loads failed; trying fallbacks")

        items = self._llm_parser.extract_json_array(text)
        if items:
            return items

        repaired = self._repair_json(text)
        if repaired:
            items = self._llm_parser.extract_json_array(repaired)
            if items:
                logger.warning("Classification JSON: succeeded after _repair_json")
                return items

        logger.warning("Classification JSON: all extraction strategies failed")
        return []

    def _repair_json(self, text: str) -> Optional[str]:
        """Attempt basic JSON repair via the shared LLM response parser."""
        return self._llm_parser._repair_json(self._llm_parser.clean_response(text))

    def parse_suspicion(self, value: Any) -> SuspicionLevel:
        """Parse a suspicion level with INFORMATIONAL fallback."""
        return self._parse_suspicion(value)

    @staticmethod
    def _parse_suspicion(value: Any) -> SuspicionLevel:
        """Parse a suspicion level with INFORMATIONAL fallback."""
        if value is None:
            return SuspicionLevel.INFORMATIONAL
        try:
            return SuspicionLevel(str(value).strip().lower())
        except Exception:  # noqa: BLE001
            logger.warning(
                "Unknown suspicion level %r; defaulting to INFORMATIONAL",
                value,
            )
            return SuspicionLevel.INFORMATIONAL
