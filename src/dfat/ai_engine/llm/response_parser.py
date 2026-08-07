"""Generic utilities for extracting structured data from LLM text output."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LLMResponseParser:
    """Generic utility for extracting structured data from LLM text output."""

    def clean_response(self, text: str) -> str:
        """Remove markdown fencing and trim whitespace.

        Args:
            text: Raw LLM response text.

        Returns:
            Cleaned text suitable for JSON extraction attempts.
        """
        cleaned = text.strip()
        cleaned = re.sub(
            r"```(?:json|JSON)?\s*",
            "",
            cleaned,
        )
        cleaned = cleaned.replace("```", "")
        return cleaned.strip()

    def extract_between_markers(self, text: str, start: str, end: str) -> str:
        """Return the substring between the first ``start`` and last ``end``.

        Args:
            text: Source text.
            start: Start marker.
            end: End marker.

        Returns:
            Extracted substring, or empty string when markers are absent.
        """
        start_idx = text.find(start)
        if start_idx < 0:
            return ""
        start_idx += len(start)
        end_idx = text.rfind(end)
        if end_idx < 0 or end_idx < start_idx:
            return ""
        return text[start_idx:end_idx].strip()

    def extract_json_array(self, text: str) -> list[dict[str, Any]]:
        """Extract a JSON array of objects from LLM text.

        Args:
            text: Raw or partially cleaned LLM text.

        Returns:
            List of dict items (non-dict elements skipped). Empty on failure.
        """
        candidates = self._array_candidates(text)
        for candidate in candidates:
            try:
                loaded = json.loads(candidate)
            except json.JSONDecodeError:
                repaired = self._repair_json(candidate)
                if repaired is None:
                    continue
                try:
                    loaded = json.loads(repaired)
                except json.JSONDecodeError:
                    continue
            if isinstance(loaded, list):
                return [item for item in loaded if isinstance(item, dict)]
            if isinstance(loaded, dict):
                nested = loaded.get("classifications") or loaded.get("results")
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
        # Line-by-line object accumulation
        line_objects = self._parse_line_objects(text)
        if line_objects:
            logger.warning("LLM JSON extraction fell back to line-by-line objects")
            return line_objects
        return []

    def extract_json_object(self, text: str) -> dict[str, Any]:
        """Extract a single JSON object from LLM text.

        Args:
            text: Raw LLM text.

        Returns:
            Parsed object, or empty dict on failure.
        """
        cleaned = self.clean_response(text)
        for candidate in (cleaned, self._slice_braces(cleaned)):
            if not candidate:
                continue
            try:
                loaded = json.loads(candidate)
            except json.JSONDecodeError:
                repaired = self._repair_json(candidate)
                if repaired is None:
                    continue
                try:
                    loaded = json.loads(repaired)
                except json.JSONDecodeError:
                    continue
            if isinstance(loaded, dict):
                return loaded
        return {}

    def _array_candidates(self, text: str) -> list[str]:
        """Build ordered candidate strings that may contain a JSON array."""
        cleaned = self.clean_response(text)
        candidates: list[str] = [cleaned]

        fenced = self.extract_between_markers(text, "```json", "```")
        if not fenced:
            fenced = self.extract_between_markers(text, "```JSON", "```")
        if not fenced:
            fenced = self.extract_between_markers(text, "```", "```")
        if fenced:
            candidates.append(fenced)
            candidates.append(self.clean_response(fenced))

        bracketed = self._slice_brackets(cleaned)
        if bracketed:
            candidates.append(bracketed)

        # Deduplicate while preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for item in candidates:
            if item and item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

    @staticmethod
    def _slice_brackets(text: str) -> str:
        """Return text between the first ``[`` and last ``]``."""
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end < 0 or end <= start:
            return ""
        return text[start : end + 1]

    @staticmethod
    def _slice_braces(text: str) -> str:
        """Return text between the first ``{`` and last ``}``."""
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0 or end <= start:
            return ""
        return text[start : end + 1]

    def _parse_line_objects(self, text: str) -> list[dict[str, Any]]:
        """Parse individual JSON objects appearing one per line."""
        results: list[dict[str, Any]] = []
        for line in text.splitlines():
            stripped = line.strip().rstrip(",")
            if not stripped.startswith("{"):
                continue
            try:
                loaded = json.loads(stripped)
            except json.JSONDecodeError:
                repaired = self._repair_json(stripped)
                if repaired is None:
                    continue
                try:
                    loaded = json.loads(repaired)
                except json.JSONDecodeError:
                    continue
            if isinstance(loaded, dict):
                results.append(loaded)
        return results

    def _repair_json(self, text: str) -> Optional[str]:
        """Attempt basic JSON repair for common LLM mistakes.

        Args:
            text: Broken JSON candidate.

        Returns:
            Repaired string, or ``None`` when repair is not applicable.
        """
        repaired = text.strip()
        if not repaired:
            return None

        # Single quotes → double quotes (naive but useful for LLM output)
        if "'" in repaired and '"' not in repaired:
            repaired = repaired.replace("'", '"')
        else:
            repaired = re.sub(r"'([^']*)'", r'"\1"', repaired)

        # Trailing commas before } or ]
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

        # Balance brackets / braces
        open_square = repaired.count("[")
        close_square = repaired.count("]")
        if open_square > close_square:
            repaired += "]" * (open_square - close_square)
            logger.warning("JSON repair: appended missing closing brackets")

        open_curly = repaired.count("{")
        close_curly = repaired.count("}")
        if open_curly > close_curly:
            repaired += "}" * (open_curly - close_curly)
            logger.warning("JSON repair: appended missing closing braces")

        return repaired


class StructuredOutputParser:
    """Extract structured JSON from LLM responses with surrounding text.

    Handles markdown fencing, malformed JSON, and free-form section headers.
    Extraction chain: direct → code block → bracket search → line-by-line → repair.
    """

    _CLASSIFICATION_FIELDS = (
        "artefact_id",
        "suspicion_level",
        "reasoning",
        "ioc_indicators",
    )
    _RANKING_FIELDS = ("artefact_id", "relevance_score", "priority_reasoning")

    _SECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "executive_summary",
            re.compile(
                r"(?:^|\n)\s*(?:#{1,3}\s*)?(?:1[.)]?\s*)?EXECUTIVE\s+SUMMARY\s*:?\s*"
                r"(.*?)(?=\n\s*(?:#{1,3}\s*)?(?:2[.)]?\s*)?KEY\s+FINDINGS|\Z)",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        (
            "key_findings",
            re.compile(
                r"(?:^|\n)\s*(?:#{1,3}\s*)?(?:2[.)]?\s*)?KEY\s+FINDINGS\s*:?\s*"
                r"(.*?)(?=\n\s*(?:#{1,3}\s*)?(?:3[.)]?\s*)?TIMELINE|\Z)",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        (
            "timeline",
            re.compile(
                r"(?:^|\n)\s*(?:#{1,3}\s*)?(?:3[.)]?\s*)?TIMELINE(?:\s+OF\s+EVENTS)?\s*:?\s*"
                r"(.*?)(?=\n\s*(?:#{1,3}\s*)?(?:4[.)]?\s*)?INDICATORS|\Z)",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        (
            "iocs",
            re.compile(
                r"(?:^|\n)\s*(?:#{1,3}\s*)?(?:4[.)]?\s*)?INDICATORS\s+OF\s+COMPROMISE\s*:?\s*"
                r"(.*?)(?=\n\s*(?:#{1,3}\s*)?(?:5[.)]?\s*)?RECOMMENDED|\Z)",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
        (
            "recommended_actions",
            re.compile(
                r"(?:^|\n)\s*(?:#{1,3}\s*)?(?:5[.)]?\s*)?RECOMMENDED\s+NEXT\s+STEPS\s*:?\s*"
                r"(.*?)\Z",
                re.IGNORECASE | re.DOTALL,
            ),
        ),
    )

    def __init__(self, base_parser: Optional[LLMResponseParser] = None) -> None:
        """Initialise with an optional shared ``LLMResponseParser``."""
        self._base = base_parser or LLMResponseParser()

    def parse_classification_array(self, text: str) -> list[dict[str, Any]]:
        """Extract classification objects from LLM text.

        Each item ideally includes: ``artefact_id``, ``suspicion_level``,
        ``reasoning``, ``ioc_indicators``.
        """
        loaded = self._try_extraction_chain(text)
        items = self._coerce_array(
            loaded,
            nested_keys=("classifications", "results"),
        )
        normalised: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if not self._validate_schema(item, ["artefact_id"]):
                continue
            row = {
                "artefact_id": str(item.get("artefact_id", "")).strip(),
                "suspicion_level": item.get("suspicion_level"),
                "reasoning": str(
                    item.get("reasoning") or item.get("priority_reasoning") or ""
                ),
                "ioc_indicators": item.get("ioc_indicators")
                if isinstance(item.get("ioc_indicators"), list)
                else [],
            }
            if row["artefact_id"]:
                normalised.append(row)
        return normalised

    def parse_ranking_array(self, text: str) -> list[dict[str, Any]]:
        """Extract ranking objects from LLM text.

        Each item ideally includes: ``artefact_id``, ``relevance_score``,
        ``priority_reasoning``.
        """
        loaded = self._try_extraction_chain(text)
        items = self._coerce_array(loaded, nested_keys=("rankings", "results"))
        normalised: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if not self._validate_schema(item, ["artefact_id", "relevance_score"]):
                # Allow missing relevance_score only if priority_reasoning present
                if "artefact_id" not in item:
                    continue
            artefact_id = str(item.get("artefact_id", "")).strip()
            if not artefact_id:
                continue
            score = item.get("relevance_score")
            try:
                score_f = float(score)
            except (TypeError, ValueError):
                continue
            normalised.append(
                {
                    "artefact_id": artefact_id,
                    "relevance_score": max(0.0, min(1.0, score_f)),
                    "priority_reasoning": str(
                        item.get("priority_reasoning") or item.get("reasoning") or ""
                    ),
                }
            )
        return normalised

    def parse_summary_sections(self, text: str) -> dict[str, str]:
        """Extract named summary sections from free-form LLM text.

        Supports numbered headers, markdown ``##`` headers, and plain titles.
        """
        sections: dict[str, str] = {
            "executive_summary": "",
            "key_findings": "",
            "timeline": "",
            "iocs": "",
            "recommended_actions": "",
        }
        if not text or not text.strip():
            return sections
        for name, pattern in self._SECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                sections[name] = match.group(1).strip()
        return sections

    def _try_extraction_chain(self, text: str) -> Optional[Any]:
        """Try ordered JSON extraction strategies with fallback logging."""
        if not text or not str(text).strip():
            return None

        # 1. Direct json.loads
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            logger.warning("StructuredOutputParser: direct json.loads failed")

        # 2. Markdown code block
        for marker in ("```json", "```JSON", "```"):
            fenced = self._base.extract_between_markers(text, marker, "```")
            if not fenced:
                continue
            try:
                loaded = json.loads(fenced.strip())
                logger.warning(
                    "StructuredOutputParser: extracted JSON from markdown code block"
                )
                return loaded
            except json.JSONDecodeError:
                repaired = self._base._repair_json(fenced)
                if repaired:
                    try:
                        loaded = json.loads(repaired)
                        logger.warning(
                            "StructuredOutputParser: repaired markdown-block JSON"
                        )
                        return loaded
                    except json.JSONDecodeError:
                        pass
        logger.warning("StructuredOutputParser: markdown code-block extraction failed")

        # 3. Bracket search (first [ … last ])
        bracketed = LLMResponseParser._slice_brackets(self._base.clean_response(text))
        if bracketed:
            try:
                loaded = json.loads(bracketed)
                logger.warning("StructuredOutputParser: extracted via bracket search")
                return loaded
            except json.JSONDecodeError:
                repaired = self._base._repair_json(bracketed)
                if repaired:
                    try:
                        loaded = json.loads(repaired)
                        logger.warning(
                            "StructuredOutputParser: repaired bracket-search JSON"
                        )
                        return loaded
                    except json.JSONDecodeError:
                        pass
        logger.warning("StructuredOutputParser: bracket search failed")

        # 4. Line-by-line objects
        line_objects = self._base._parse_line_objects(text)
        if line_objects:
            logger.warning("StructuredOutputParser: fell back to line-by-line objects")
            return line_objects

        # 5. Full-text repair then parse
        repaired = self._base._repair_json(self._base.clean_response(text))
        if repaired:
            try:
                loaded = json.loads(repaired)
                logger.warning("StructuredOutputParser: succeeded after full-text repair")
                return loaded
            except json.JSONDecodeError:
                pass

        logger.warning("StructuredOutputParser: all extraction strategies failed")
        return None

    def _validate_schema(self, data: Any, required_fields: list[str]) -> bool:
        """Return True when ``data`` is a dict containing all required fields."""
        if not isinstance(data, dict):
            return False
        return all(field in data for field in required_fields)

    @staticmethod
    def _coerce_array(
        loaded: Any,
        *,
        nested_keys: tuple[str, ...],
    ) -> list[Any]:
        """Normalise extraction output to a list of items."""
        if loaded is None:
            return []
        if isinstance(loaded, list):
            return loaded
        if isinstance(loaded, dict):
            for key in nested_keys:
                nested = loaded.get(key)
                if isinstance(nested, list):
                    return nested
            # Single object payload
            return [loaded]
        return []
