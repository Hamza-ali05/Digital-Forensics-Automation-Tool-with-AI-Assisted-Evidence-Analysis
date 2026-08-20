"""Sigma rule engine for log-based and process-creation detection."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact

logger = logging.getLogger(__name__)

try:
    from sigma.rule import SigmaRule as _PySigmaRule  # type: ignore[import-untyped]

    _PYSIGMA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PySigmaRule = None
    _PYSIGMA_AVAILABLE = False


class SigmaMatch(BaseModel):
    """Result of a single Sigma rule match."""

    model_config = ConfigDict(frozen=False)

    rule_name: str
    rule_id: str
    level: str
    description: str = ""
    mitre_techniques: list[str] = Field(default_factory=list)
    artefact_id: Optional[str] = None
    matched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class _ParsedSigmaRule:
    """Lightweight parsed Sigma rule used for built-in matching."""

    __slots__ = (
        "rule_id",
        "title",
        "level",
        "description",
        "mitre_techniques",
        "logsource",
        "detection",
    )

    def __init__(self, payload: dict[str, Any]) -> None:
        self.rule_id: str = str(payload.get("id") or "")
        self.title: str = str(payload.get("title") or "")
        self.level: str = str(payload.get("level") or "informational")
        self.description: str = str(payload.get("description") or "")
        tags = payload.get("tags") or []
        self.mitre_techniques: list[str] = [
            tag for tag in tags if isinstance(tag, str) and tag.startswith("attack.")
        ]
        self.logsource: dict[str, str] = payload.get("logsource") or {}
        self.detection: dict[str, Any] = payload.get("detection") or {}


class SigmaEngine:
    """Load and evaluate Sigma rules against event-log and process artefacts."""

    def __init__(self, rules_dir: Path) -> None:
        self._rules_dir = Path(rules_dir)
        self._rules: list[_ParsedSigmaRule] = []

    def load_rules(self, rules_dir: Path | None = None) -> int:
        """Parse all ``.yml`` / ``.yaml`` Sigma rule files from ``rules_dir`` (or default).

        Returns:
            Number of rules loaded.
        """
        directory = Path(rules_dir) if rules_dir is not None else self._rules_dir
        directory.mkdir(parents=True, exist_ok=True)
        loaded: list[_ParsedSigmaRule] = []
        for pattern in ("*.yml", "*.yaml"):
            for rule_file in sorted(directory.glob(pattern)):
                loaded.extend(self._load_file(rule_file))
        self._rules = loaded
        logger.info("Loaded %d Sigma rule(s) from %s", len(loaded), directory)
        return len(loaded)

    @property
    def rules_dir(self) -> Path:
        """Return the configured Sigma rules directory."""
        return self._rules_dir

    def get_loaded_rules_count(self) -> int:
        """Return the number of loaded Sigma rules."""
        return len(self._rules)

    def list_loaded_rules(self) -> list[dict[str, str]]:
        """Return metadata for currently loaded Sigma rules."""
        return [
            {
                "rule_id": rule.rule_id,
                "title": rule.title,
                "level": rule.level,
                "description": rule.description,
            }
            for rule in self._rules
        ]

    def match_event_log(self, artefact: Artefact) -> list[SigmaMatch]:
        """Match an ``EVENT_LOG`` artefact against all loaded Sigma rules."""
        if artefact.category is not ArtefactCategory.EVENT_LOG:
            return []
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        return self._evaluate(raw, artefact.artefact_id, logsource_filter="windows")

    def match_process(self, artefact: Artefact) -> list[SigmaMatch]:
        """Match a ``RUNNING_PROCESS`` artefact against process-creation rules."""
        if artefact.category not in {
            ArtefactCategory.RUNNING_PROCESS,
            ArtefactCategory.INJECTED_CODE,
        }:
            return []
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        return self._evaluate(raw, artefact.artefact_id, logsource_filter="process_creation")

    def _evaluate(
        self,
        fields: dict[str, Any],
        artefact_id: str,
        logsource_filter: str,
    ) -> list[SigmaMatch]:
        matches: list[SigmaMatch] = []
        for rule in self._rules:
            if not _logsource_applicable(rule.logsource, logsource_filter):
                continue
            if _detection_matches(rule.detection, fields):
                matches.append(
                    SigmaMatch(
                        rule_name=rule.title,
                        rule_id=rule.rule_id,
                        level=rule.level,
                        description=rule.description,
                        mitre_techniques=list(rule.mitre_techniques),
                        artefact_id=artefact_id,
                    )
                )
        return matches

    def _load_file(self, path: Path) -> list[_ParsedSigmaRule]:
        rules: list[_ParsedSigmaRule] = []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Could not read Sigma rule file: %s", path)
            return rules
        for document in yaml.safe_load_all(text):
            if not isinstance(document, dict):
                continue
            if "detection" not in document:
                continue
            rules.append(_ParsedSigmaRule(document))
        return rules


def _logsource_applicable(logsource: dict[str, str], desired: str) -> bool:
    """Return whether a Sigma rule's logsource matches the desired filter."""
    if not logsource:
        return True
    values = {str(value).lower() for value in logsource.values()}
    if desired == "process_creation":
        return "process_creation" in values or "process" in values
    if desired == "windows":
        return True
    return desired.lower() in values


def _detection_matches(detection: dict[str, Any], fields: dict[str, Any]) -> bool:
    """Evaluate a Sigma detection block against flattened event fields.

    Supports the ``selection`` + ``condition: selection`` pattern and simple
    keyword lists. Complex boolean conditions are not fully parsed; the engine
    falls back to checking any named selection that partially matches.
    """
    if not detection:
        return False

    condition = str(detection.get("condition") or "").strip().lower()

    named_selections = {
        key: value
        for key, value in detection.items()
        if key not in {"condition", "timeframe"}
    }

    if not named_selections:
        return False

    if "not" in condition and "and not" in condition:
        parts = condition.split("and not", 1)
        include_name = parts[0].strip()
        exclude_name = parts[1].strip()
        inc = named_selections.get(include_name)
        exc = named_selections.get(exclude_name)
        if inc is not None and _selection_matches(inc, fields):
            if exc is not None and _selection_matches(exc, fields):
                return False
            return True
        return False

    if " or " in condition:
        for name, sel in named_selections.items():
            if name in condition and _selection_matches(sel, fields):
                return True
        return False

    for name, sel in named_selections.items():
        if name == "condition":
            continue
        if _selection_matches(sel, fields):
            return True
    return False


def _selection_matches(selection: Any, fields: dict[str, Any]) -> bool:
    """Check whether a single named Sigma selection matches ``fields``."""
    if isinstance(selection, dict):
        return _dict_selection_matches(selection, fields)
    if isinstance(selection, list):
        return any(_item_matches_fields(item, fields) for item in selection)
    return False


def _dict_selection_matches(selection: dict[str, Any], fields: dict[str, Any]) -> bool:
    for key, expected in selection.items():
        field_key, modifier = _parse_field_modifier(key)
        actual = _resolve_field(fields, field_key)
        if not _value_matches(actual, expected, modifier):
            return False
    return True


def _item_matches_fields(item: Any, fields: dict[str, Any]) -> bool:
    if isinstance(item, dict):
        return _dict_selection_matches(item, fields)
    if isinstance(item, str):
        text_pool = " ".join(str(value) for value in fields.values())
        return _wildcard_match(item, text_pool)
    return False


def _parse_field_modifier(key: str) -> tuple[str, str]:
    """Split ``FieldName|modifier`` into (field, modifier) or (field, '')."""
    if "|" in key:
        parts = key.split("|", 1)
        return parts[0], parts[1]
    return key, ""


def _resolve_field(fields: dict[str, Any], key: str) -> Any:
    if key in fields:
        return fields[key]
    lowered = {k.lower(): v for k, v in fields.items()}
    return lowered.get(key.lower())


def _value_matches(actual: Any, expected: Any, modifier: str) -> bool:
    if actual is None:
        return False

    if modifier in ("contains", "contains|all"):
        if isinstance(expected, list):
            if "all" in modifier:
                return all(_substring_match(actual, item) for item in expected)
            return any(_substring_match(actual, item) for item in expected)
        return _substring_match(actual, expected)

    if modifier in ("startswith",):
        return _string_of(actual).lower().startswith(_string_of(expected).lower())

    if modifier in ("endswith",):
        return _string_of(actual).lower().endswith(_string_of(expected).lower())

    if modifier == "re":
        try:
            return bool(re.search(str(expected), _string_of(actual), re.IGNORECASE))
        except re.error:
            return False

    if isinstance(expected, list):
        return any(_scalar_match(actual, item) for item in expected)

    return _scalar_match(actual, expected)


def _substring_match(actual: Any, needle: Any) -> bool:
    return _string_of(needle).lower() in _string_of(actual).lower()


def _scalar_match(actual: Any, expected: Any) -> bool:
    if isinstance(expected, str) and ("*" in expected or "?" in expected):
        return _wildcard_match(expected, _string_of(actual))
    return _string_of(actual).lower() == _string_of(expected).lower()


def _wildcard_match(pattern: str, text: str) -> bool:
    regex = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    try:
        return bool(re.search(regex, text, re.IGNORECASE))
    except re.error:
        return False


def _string_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
