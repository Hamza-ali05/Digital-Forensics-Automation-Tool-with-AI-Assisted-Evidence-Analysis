"""Windows Event Log (.evtx) parser using ``python-evtx``.

Artefact ``raw_data`` schema for ``EVENT_LOG`` (contract)::

    {
        "event_id": int,
        "timestamp": ISO-8601 str | null,
        "channel": str | null,
        "source": str | null,
        "level": str | null,
        "computer_name": str | null,
        "message": str,              # truncated event XML / summary
        "event_data": dict,          # name→value map from EventData
        "is_security_relevant": bool,
    }

Known log locations are listed in ``EVTX_PATHS``. Security-relevant Event IDs
are defined in ``SECURITY_EVENT_IDS``.
"""

from __future__ import annotations

import fnmatch
import logging
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import DiskParsingError
from dfat.core.models.artefact import Artefact
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.disk_access import DiskImageAccessor, FileEntry
from dfat.forensic_engine.parsers.utils import (
    convert_timestamp,
    sanitise_path,
    truncate_data,
)
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.constants import MAX_ARTEFACTS_PER_CATEGORY

logger = logging.getLogger(__name__)

EVTX_PATHS: list[str] = [
    "Windows/System32/winevt/Logs/*.evtx",
]

SECURITY_EVENT_IDS: dict[int, str] = {
    4624: "Logon",
    4625: "Failed Logon",
    4648: "Explicit Logon",
    4672: "Special Privileges",
    4688: "Process Created",
    4689: "Process Exited",
    4720: "User Created",
    4722: "User Enabled",
    4732: "Member Added to Group",
    7045: "Service Installed",
}

_EVENT_ID_RE = re.compile(
    r"<EventID(?:\s[^>]*)?>(\d+)</EventID>",
    re.IGNORECASE,
)
_CHANNEL_RE = re.compile(
    r"<Channel(?:\s[^>]*)?>([^<]*)</Channel>",
    re.IGNORECASE,
)
_COMPUTER_RE = re.compile(
    r"<Computer(?:\s[^>]*)?>([^<]*)</Computer>",
    re.IGNORECASE,
)
_LEVEL_RE = re.compile(
    r"<Level(?:\s[^>]*)?>([^<]*)</Level>",
    re.IGNORECASE,
)
_PROVIDER_NAME_RE = re.compile(
    r'<Provider[^>]*\bName="([^"]+)"',
    re.IGNORECASE,
)
_PROVIDER_TEXT_RE = re.compile(
    r"<Provider(?:\s[^>]*)?>([^<]*)</Provider>",
    re.IGNORECASE,
)
_EVENT_DATA_BLOCK_RE = re.compile(
    r"<EventData[^>]*>(.*?)</EventData>",
    re.IGNORECASE | re.DOTALL,
)
_DATA_NAMED_RE = re.compile(
    r'<Data\s+Name="([^"]+)"[^>]*>(.*?)</Data>',
    re.IGNORECASE | re.DOTALL,
)
_DATA_PLAIN_RE = re.compile(
    r"<Data(?:\s[^>]*)?>(.*?)</Data>",
    re.IGNORECASE | re.DOTALL,
)

_LEVEL_NAMES = {
    "0": "LogAlways",
    "1": "Critical",
    "2": "Error",
    "3": "Warning",
    "4": "Information",
    "5": "Verbose",
}


class EventLogParser(BaseParser):
    """Extract Windows Event Log artefacts from ``.evtx`` files in disk images.

    Locates logs under ``EVTX_PATHS`` via ``DiskImageAccessor``, extracts each
    file to a temporary path, parses with ``python-evtx``, and emits
    ``EVENT_LOG`` artefacts. Corrupt logs are skipped after a warning.
    """

    _parse_error_class = DiskParsingError

    def __init__(
        self,
        disk_accessor: DiskImageAccessor,
        audit_logger: ForensicAuditLogger,
        max_artefacts: int = MAX_ARTEFACTS_PER_CATEGORY,
    ) -> None:
        """Initialise the event log parser.

        Args:
            disk_accessor: Low-level pytsk3 disk image accessor.
            audit_logger: ACPO-compliant forensic audit logger.
            max_artefacts: Maximum artefacts retained for a single parse.
        """
        super().__init__(audit_logger=audit_logger, max_artefacts=max_artefacts)
        self._disk_accessor = disk_accessor

    @property
    def parser_name(self) -> str:
        """Return the stable parser identifier."""
        return "EventLogParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return supported artefact categories."""
        return [ArtefactCategory.EVENT_LOG]

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return supported evidence types."""
        return [EvidenceType.DISK_IMAGE]

    def _do_parse(self, evidence: EvidenceImage) -> list[Artefact]:
        """Locate ``.evtx`` files, extract to temp, and parse event records."""
        evtx_mod = self._safe_import(
            "Evtx.Evtx",
            "python-evtx is required for event log parsing. Install with: "
            "pip install python-evtx",
        )
        evtx_cls = getattr(evtx_mod, "Evtx")

        img_info = self._disk_accessor.open_image(Path(evidence.file_path))
        artefacts: list[Artefact] = []
        temp_files: list[Path] = []
        temp_dir = Path(tempfile.mkdtemp(prefix="dfat_evtx_"))
        try:
            fs_info = self._disk_accessor.get_filesystem(img_info)
            for entry in self._locate_evtx_files(fs_info):
                if not self._check_limit(len(artefacts)):
                    break
                temp_path = self._disk_accessor.extract_file_to_temp(
                    fs_info,
                    entry.inode,
                    temp_dir,
                )
                if temp_path is None:
                    continue
                temp_files.append(temp_path)
                try:
                    artefacts.extend(
                        self._parse_evtx_file(
                            temp_path,
                            entry,
                            evidence.evidence_id,
                            evtx_cls,
                            remaining=self._max_artefacts - len(artefacts),
                        )
                    )
                except Exception as exc:  # noqa: BLE001 — corrupt EVTX
                    logger.warning(
                        "Skipping corrupt event log %s: %s",
                        entry.path,
                        exc,
                    )
                    continue
        finally:
            self._disk_accessor.close(img_info)
            self._cleanup_temps(temp_files, temp_dir)
        return artefacts

    def _locate_evtx_files(self, fs_info: Any) -> list[FileEntry]:
        """Return filesystem entries matching ``EVTX_PATHS`` patterns."""
        matches: list[FileEntry] = []
        seen: set[int] = set()
        for entry in self._disk_accessor.walk_filesystem(fs_info):
            if entry.file_type in {"directory", "unknown"}:
                continue
            if entry.inode and entry.inode in seen:
                continue
            if not self._path_matches_evtx(entry.path):
                continue
            if entry.inode:
                seen.add(entry.inode)
            matches.append(entry)
        return matches

    @staticmethod
    def _path_matches_evtx(path: str) -> bool:
        """Return whether ``path`` matches a known EVTX location."""
        normalised = sanitise_path(path).lstrip("/").lower()
        for pattern in EVTX_PATHS:
            candidate = pattern.replace("\\", "/").lower()
            if fnmatch.fnmatch(normalised, candidate):
                return True
            if fnmatch.fnmatch("/" + normalised, "/" + candidate):
                return True
            if normalised.endswith(".evtx") and "winevt/logs" in normalised:
                return True
        return False

    def _parse_evtx_file(
        self,
        temp_path: Path,
        entry: FileEntry,
        evidence_id: str,
        evtx_cls: Any,
        remaining: int,
    ) -> list[Artefact]:
        """Parse an extracted ``.evtx`` file into artefacts."""
        artefacts: list[Artefact] = []
        try:
            with evtx_cls(str(temp_path)) as log:
                for record in log.records():
                    if len(artefacts) >= remaining:
                        break
                    try:
                        artefact = self._record_to_artefact(
                            record,
                            entry.path,
                            evidence_id,
                        )
                    except Exception:  # noqa: BLE001 — skip bad records
                        continue
                    if artefact is not None:
                        artefacts.append(artefact)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to parse event log %s: %s",
                entry.path,
                exc,
            )
            return []
        return artefacts

    def _record_to_artefact(
        self,
        record: Any,
        source_path: str,
        evidence_id: str,
    ) -> Optional[Artefact]:
        """Convert a single EVTX record into an ``EVENT_LOG`` artefact."""
        xml = record.xml()
        event_id = self._parse_event_id(xml)
        if event_id is None:
            return None

        ts = convert_timestamp(record.timestamp())
        level_raw = self._match_group(_LEVEL_RE, xml)
        source = self._extract_provider(xml)
        channel = self._match_group(_CHANNEL_RE, xml)
        computer = self._match_group(_COMPUTER_RE, xml)
        event_data = self._parse_event_data(xml)
        if event_id in SECURITY_EVENT_IDS:
            event_data.setdefault(
                "security_event_label",
                SECURITY_EVENT_IDS[event_id],
            )

        return self._create_artefact(
            category=ArtefactCategory.EVENT_LOG,
            evidence_id=evidence_id,
            source_path=source_path,
            raw_data={
                "event_id": event_id,
                "timestamp": ts.isoformat() if ts is not None else None,
                "channel": channel,
                "source": source,
                "level": _LEVEL_NAMES.get(level_raw or "", level_raw),
                "computer_name": computer,
                "message": truncate_data(xml, 2000),
                "event_data": event_data,
                "is_security_relevant": event_id in SECURITY_EVENT_IDS,
            },
        )

    @staticmethod
    def _parse_event_id(xml: str) -> Optional[int]:
        """Extract integer Event ID from record XML."""
        match = _EVENT_ID_RE.search(xml)
        if match is None:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _extract_provider(xml: str) -> Optional[str]:
        """Extract provider/source name from record XML."""
        match = _PROVIDER_NAME_RE.search(xml)
        if match is not None:
            return match.group(1).strip() or None
        match = _PROVIDER_TEXT_RE.search(xml)
        if match is not None:
            return match.group(1).strip() or None
        return None

    @staticmethod
    def _parse_event_data(xml: str) -> dict[str, str]:
        """Parse ``EventData`` name/value pairs from record XML."""
        block = _EVENT_DATA_BLOCK_RE.search(xml)
        if block is None:
            return {}
        body = block.group(1)
        named = _DATA_NAMED_RE.findall(body)
        if named:
            return {
                name: truncate_data(value.strip(), 1000)
                for name, value in named
            }
        plain = _DATA_PLAIN_RE.findall(body)
        return {
            f"data_{index}": truncate_data(value.strip(), 1000)
            for index, value in enumerate(plain)
            if value.strip()
        }

    @staticmethod
    def _match_group(pattern: re.Pattern[str], xml: str) -> Optional[str]:
        """Return the first regex capture group, or ``None``."""
        match = pattern.search(xml)
        if match is None:
            return None
        text = match.group(1).strip()
        return text or None

    @staticmethod
    def _cleanup_temps(temp_files: list[Path], temp_dir: Path) -> None:
        """Remove extracted EVTX files and the temporary directory."""
        for path in temp_files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
        try:
            temp_dir.rmdir()
        except OSError:
            try:
                for child in temp_dir.iterdir():
                    child.unlink(missing_ok=True)
                temp_dir.rmdir()
            except OSError:
                pass
