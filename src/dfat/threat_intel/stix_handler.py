"""STIX 2.x bundle parsing and IOC extraction."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.knowledge.ioc_database import IOCEntry

logger = logging.getLogger(__name__)

try:
    import stix2  # type: ignore[import-untyped]

    _STIX2_AVAILABLE = True
except ImportError:  # pragma: no cover
    stix2 = None
    _STIX2_AVAILABLE = False

_ATTACK_PATTERN = "attack-pattern"
_INDICATOR = "indicator"
_MALWARE = "malware"
_RELATIONSHIP = "relationship"


class STIXObject(BaseModel):
    """Normalised STIX object extracted from a bundle."""

    model_config = ConfigDict(frozen=False)

    object_id: str
    object_type: str
    name: str = ""
    description: str = ""
    labels: list[str] = Field(default_factory=list)
    external_references: list[dict[str, Any]] = Field(default_factory=list)
    pattern: Optional[str] = None
    kill_chain_phases: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class STIXHandler:
    """Parse STIX bundles and convert indicators into IOC knowledge-base entries."""

    def __init__(self) -> None:
        self._objects: list[STIXObject] = []

    def parse_bundle(self, file_path: Path) -> list[STIXObject]:
        """Parse a STIX 2.x bundle JSON file and cache the extracted objects."""
        path = Path(file_path)
        if not path.is_file():
            logger.warning("STIX bundle not found: %s", path)
            self._objects = []
            return []

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read STIX bundle: %s", path)
            self._objects = []
            return []

        raw_objects = _extract_bundle_objects(payload)
        parsed = [_normalise_object(item, source=str(path)) for item in raw_objects]
        self._objects = parsed
        logger.info("Parsed %d STIX object(s) from %s", len(parsed), path)
        return parsed

    def extract_indicators(self, objects: list[STIXObject]) -> list[IOCEntry]:
        """Convert STIX indicators into ``IOCEntry`` records for the IOC KB."""
        entries: list[IOCEntry] = []
        for obj in objects:
            if obj.object_type != _INDICATOR:
                continue
            entry = _indicator_to_ioc(obj)
            if entry is not None:
                entries.append(entry)
        return entries

    def extract_attack_patterns(self) -> list[dict[str, Any]]:
        """Return attack-pattern objects from the most recently parsed bundle."""
        patterns: list[dict[str, Any]] = []
        for obj in self._objects:
            if obj.object_type != _ATTACK_PATTERN:
                continue
            technique_ids = _external_technique_ids(obj.external_references)
            patterns.append(
                {
                    "object_id": obj.object_id,
                    "name": obj.name,
                    "description": obj.description,
                    "technique_ids": technique_ids,
                    "tactics": _tactics_from_phases(obj.kill_chain_phases),
                    "labels": list(obj.labels),
                }
            )
        return patterns


def _extract_bundle_objects(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if payload.get("type") == "bundle":
        objects = payload.get("objects")
        if isinstance(objects, list):
            return [item for item in objects if isinstance(item, dict)]
    if payload.get("type") and payload.get("id"):
        return [payload]
    for key in ("objects", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _normalise_object(raw: dict[str, Any], *, source: str) -> STIXObject:
    if _STIX2_AVAILABLE:
        try:
            parsed = stix2.parse(raw, allow_custom=True)
            raw = dict(parsed) if hasattr(parsed, "items") else raw
        except Exception:
            logger.debug("stix2 parse failed for %s; using raw JSON", raw.get("id"))

    return STIXObject(
        object_id=str(raw.get("id") or ""),
        object_type=str(raw.get("type") or "unknown"),
        name=str(raw.get("name") or ""),
        description=str(raw.get("description") or ""),
        labels=[str(label) for label in raw.get("labels") or []],
        external_references=list(raw.get("external_references") or []),
        pattern=raw.get("pattern"),
        kill_chain_phases=list(raw.get("kill_chain_phases") or []),
        raw={**raw, "_source_bundle": source},
    )


def _indicator_to_ioc(obj: STIXObject) -> IOCEntry | None:
    value, ioc_type = _pattern_to_value(obj.pattern or "")
    if value is None:
        value = obj.name.strip() or None
        ioc_type = ioc_type or "indicator"
    if not value:
        return None

    confidence = "medium"
    for label in obj.labels:
        lowered = label.lower()
        if lowered in {"high", "medium", "low"}:
            confidence = lowered
            break

    return IOCEntry(
        ioc_type=ioc_type or "indicator",
        value=value,
        source_dataset=str(obj.raw.get("_source_bundle") or "stix_bundle"),
        confidence=confidence,
        description=obj.description or obj.name or None,
        tags=list(obj.labels),
        mitre_techniques=_external_technique_ids(obj.external_references),
        ingested_at=datetime.now(UTC),
    )


def _pattern_to_value(pattern: str) -> tuple[str | None, str | None]:
    if not pattern:
        return None, None
    text = pattern.strip()
    for ioc_type, regex in _PATTERN_REGEXES.items():
        match = regex.search(text)
        if match:
            return match.group(1), ioc_type
    if "=" in text:
        _, _, rhs = text.partition("=")
        cleaned = rhs.strip().strip("'\"")
        if cleaned:
            return cleaned, "indicator"
    return None, None


def _external_technique_ids(references: list[dict[str, Any]]) -> list[str]:
    technique_ids: list[str] = []
    for ref in references:
        source = str(ref.get("source_name") or "").lower()
        external_id = str(ref.get("external_id") or "")
        if source in {"mitre-attack", "mitre attack", "mitre"} and external_id.startswith("T"):
            technique_ids.append(external_id)
    return technique_ids


def _tactics_from_phases(phases: list[dict[str, Any]]) -> list[str]:
    tactics: list[str] = []
    for phase in phases:
        name = phase.get("phase_name") or phase.get("kill_chain_name")
        if name:
            tactics.append(str(name).replace("-", " ").title())
    return tactics


_PATTERN_REGEXES = {
    "domain": re.compile(r"domain-name:value\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE),
    "ip": re.compile(
        r"(?:ipv4-addr|ipv6-addr):value\s*=\s*['\"]([^'\"]+)['\"]",
        re.IGNORECASE,
    ),
    "hash": re.compile(
        r"file:hashes\.'(?:SHA-256|SHA-1|MD5)'\s*=\s*['\"]([^'\"]+)['\"]",
        re.IGNORECASE,
    ),
    "url": re.compile(r"url:value\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE),
    "process": re.compile(
        r"(?:process:name|file:name)\s*=\s*['\"]([^'\"]+)['\"]",
        re.IGNORECASE,
    ),
}
