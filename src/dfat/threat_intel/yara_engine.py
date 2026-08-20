"""YARA rule engine for malware signature matching against forensic artefacts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact

logger = logging.getLogger(__name__)

try:
    import yara  # type: ignore[import-untyped]

    _YARA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YARA_AVAILABLE = False


class YARAMatch(BaseModel):
    """Result of a single YARA rule match."""

    model_config = ConfigDict(frozen=False)

    rule_name: str
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    strings_matched: list[str] = Field(default_factory=list)
    artefact_id: Optional[str] = None
    matched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


_SCANNABLE_CATEGORIES = frozenset(
    {
        ArtefactCategory.FILESYSTEM_METADATA,
        ArtefactCategory.RUNNING_PROCESS,
        ArtefactCategory.INJECTED_CODE,
    }
)


class YARAEngine:
    """Compile and evaluate YARA rules against bytes, files, and artefacts."""

    def __init__(self, rules_dir: Path) -> None:
        self._rules_dir = Path(rules_dir)
        self._compiled: Any = None
        self._rule_count: int = 0

    def load_rules(self, rules_dir: Path | None = None) -> int:
        """Compile all ``.yar`` / ``.yara`` files from ``rules_dir`` (or default).

        Returns:
            Number of rule files compiled (0 when yara-python is missing).
        """
        if not _YARA_AVAILABLE:
            logger.warning("yara-python is not installed; YARA scanning disabled")
            return 0

        directory = Path(rules_dir) if rules_dir is not None else self._rules_dir
        directory.mkdir(parents=True, exist_ok=True)
        sources: dict[str, str] = {}
        for pattern in ("*.yar", "*.yara"):
            for rule_file in sorted(directory.glob(pattern)):
                try:
                    sources[rule_file.stem] = rule_file.read_text(encoding="utf-8")
                except OSError:
                    logger.warning("Could not read YARA rule file: %s", rule_file)

        if not sources:
            logger.info("No YARA rule files found in %s", directory)
            self._compiled = None
            self._rule_count = 0
            return 0

        try:
            self._compiled = yara.compile(sources=sources)
        except yara.Error:
            logger.exception("Failed to compile YARA rules from %s", directory)
            self._compiled = None
            self._rule_count = 0
            return 0

        self._rule_count = len(sources)
        logger.info("Compiled %d YARA rule file(s) from %s", self._rule_count, directory)
        return self._rule_count

    @property
    def rules_dir(self) -> Path:
        """Return the configured YARA rules directory."""
        return self._rules_dir

    def scan_bytes(self, data: bytes) -> list[YARAMatch]:
        """Match compiled YARA rules against raw bytes."""
        if self._compiled is None:
            return []
        try:
            hits = self._compiled.match(data=data)
        except Exception:
            logger.exception("YARA scan_bytes failed")
            return []
        return [_yara_hit_to_match(hit) for hit in hits]

    def scan_file(self, file_path: Path) -> list[YARAMatch]:
        """Match compiled YARA rules against a file on disk."""
        if self._compiled is None:
            return []
        path = Path(file_path)
        if not path.is_file():
            return []
        try:
            hits = self._compiled.match(filepath=str(path))
        except Exception:
            logger.exception("YARA scan_file failed for %s", path)
            return []
        return [_yara_hit_to_match(hit) for hit in hits]

    def scan_artefact(self, artefact: Artefact) -> list[YARAMatch]:
        """Scan relevant ``raw_data`` fields of a forensic artefact.

        Inspects ``hex_dump``, ``content``, ``data``, and ``source_path`` when
        the artefact belongs to a scannable category.
        """
        if self._compiled is None:
            return []
        if artefact.category not in _SCANNABLE_CATEGORIES:
            return []

        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        matches: list[YARAMatch] = []

        for field in ("hex_dump", "content", "data"):
            value = raw.get(field)
            if value is None:
                continue
            data = _as_bytes(value)
            if data:
                for match in self.scan_bytes(data):
                    match.artefact_id = artefact.artefact_id
                    matches.append(match)

        source = artefact.source_path or raw.get("path")
        if source:
            path = Path(str(source))
            if path.is_file():
                for match in self.scan_file(path):
                    match.artefact_id = artefact.artefact_id
                    matches.append(match)

        return matches

    def get_loaded_rules_count(self) -> int:
        """Return the number of compiled YARA rule files."""
        return self._rule_count

    def list_rule_files(self) -> list[str]:
        """Return YARA rule filenames discovered in the configured rules directory."""
        names: list[str] = []
        for pattern in ("*.yar", "*.yara"):
            names.extend(path.name for path in sorted(self._rules_dir.glob(pattern)))
        return sorted(set(names))


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        try:
            return bytes.fromhex(value.replace(" ", ""))
        except ValueError:
            return value.encode("utf-8", errors="replace")
    return b""


def _yara_hit_to_match(hit: Any) -> YARAMatch:
    strings_matched: list[str] = []
    if hasattr(hit, "strings"):
        for entry in hit.strings:
            try:
                if hasattr(entry, "instances"):
                    for inst in entry.instances:
                        strings_matched.append(str(inst))
                else:
                    strings_matched.append(str(entry))
            except Exception:
                strings_matched.append(repr(entry))

    return YARAMatch(
        rule_name=str(hit.rule),
        tags=list(getattr(hit, "tags", []) or []),
        meta=dict(getattr(hit, "meta", {}) or {}),
        strings_matched=strings_matched,
    )
