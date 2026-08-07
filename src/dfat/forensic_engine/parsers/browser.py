"""Browser history parser for Chrome, Edge, and Firefox SQLite databases.

Artefact ``raw_data`` schema for ``BROWSER_HISTORY`` (contract)::

    {
        "url": str,
        "title": str,
        "visit_count": int,
        "last_visit_time": ISO-8601 str | null,
        "browser_type": str,   # "chrome" | "firefox" | "edge"
        "profile": str,
    }

Known database locations are listed in ``BROWSER_DB_PATHS``.
Chrome/Edge timestamps are WebKit (µs since 1601-01-01).
Firefox timestamps are PRTime (µs since Unix epoch).
"""

from __future__ import annotations

import fnmatch
import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import DiskParsingError
from dfat.core.models.artefact import Artefact
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.disk_access import DiskImageAccessor, FileEntry
from dfat.forensic_engine.parsers.utils import convert_timestamp, sanitise_path
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.constants import MAX_ARTEFACTS_PER_CATEGORY

logger = logging.getLogger(__name__)

BROWSER_DB_PATHS: dict[str, list[str]] = {
    "chrome": [
        "Users/*/AppData/Local/Google/Chrome/User Data/Default/History",
    ],
    "firefox": [
        "Users/*/AppData/Roaming/Mozilla/Firefox/Profiles/*/places.sqlite",
    ],
    "edge": [
        "Users/*/AppData/Local/Microsoft/Edge/User Data/Default/History",
    ],
}

CHROME_HISTORY_QUERY = (
    "SELECT url, title, visit_count, last_visit_time FROM urls "
    "ORDER BY last_visit_time DESC"
)
FIREFOX_HISTORY_QUERY = (
    "SELECT url, title, visit_count, last_visit_date FROM moz_places "
    "ORDER BY last_visit_date DESC"
)


class BrowserHistoryParser(BaseParser):
    """Extract browser history artefacts from disk images.

    Locates Chrome/Edge ``History`` and Firefox ``places.sqlite`` databases via
    ``DiskImageAccessor``, extracts them to temporary files, queries with
    stdlib ``sqlite3`` in read-only mode, and emits ``BROWSER_HISTORY``
    artefacts. Corrupt databases are skipped after a warning log.
    """

    _parse_error_class = DiskParsingError

    def __init__(
        self,
        disk_accessor: DiskImageAccessor,
        audit_logger: ForensicAuditLogger,
        max_artefacts: int = MAX_ARTEFACTS_PER_CATEGORY,
    ) -> None:
        """Initialise the browser history parser.

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
        return "BrowserHistoryParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return supported artefact categories."""
        return [ArtefactCategory.BROWSER_HISTORY]

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return supported evidence types."""
        return [EvidenceType.DISK_IMAGE]

    def _do_parse(self, evidence: EvidenceImage) -> list[Artefact]:
        """Locate browser history databases and extract visit artefacts."""
        img_info = self._disk_accessor.open_image(Path(evidence.file_path))
        artefacts: list[Artefact] = []
        temp_files: list[Path] = []
        temp_dir = Path(tempfile.mkdtemp(prefix="dfat_browser_"))
        try:
            fs_info = self._disk_accessor.get_filesystem(img_info)
            db_entries = self._locate_browser_dbs(fs_info)
            for entry, browser_type in db_entries:
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
                        self._parse_database(
                            temp_path,
                            entry,
                            evidence.evidence_id,
                            browser_type,
                            remaining=self._max_artefacts - len(artefacts),
                        )
                    )
                except Exception as exc:  # noqa: BLE001 — corrupt DB, continue
                    logger.warning(
                        "Skipping corrupt browser database %s (%s): %s",
                        entry.path,
                        browser_type,
                        exc,
                    )
                    continue
        finally:
            self._disk_accessor.close(img_info)
            self._cleanup_temps(temp_files, temp_dir)
        return artefacts

    def _locate_browser_dbs(
        self,
        fs_info: Any,
    ) -> list[tuple[FileEntry, str]]:
        """Walk the filesystem and return matching browser DB entries."""
        matches: list[tuple[FileEntry, str]] = []
        seen: set[int] = set()
        for entry in self._disk_accessor.walk_filesystem(fs_info):
            if entry.file_type in {"directory", "unknown"}:
                continue
            if entry.inode and entry.inode in seen:
                continue
            browser = self._browser_for_path(entry.path)
            if browser is None:
                continue
            if entry.inode:
                seen.add(entry.inode)
            matches.append((entry, browser))
        return matches

    @staticmethod
    def _browser_for_path(path: str) -> Optional[str]:
        """Return browser type for a path, or ``None`` if not a known DB."""
        normalised = sanitise_path(path).lstrip("/").lower()
        for browser, patterns in BROWSER_DB_PATHS.items():
            for pattern in patterns:
                candidate = pattern.replace("\\", "/").lower()
                if fnmatch.fnmatch(normalised, candidate):
                    return browser
                if fnmatch.fnmatch("/" + normalised, "/" + candidate):
                    return browser
        return None

    def _parse_database(
        self,
        temp_path: Path,
        entry: FileEntry,
        evidence_id: str,
        browser_type: str,
        remaining: int,
    ) -> list[Artefact]:
        """Query an extracted SQLite history database."""
        artefacts: list[Artefact] = []
        profile = self._profile_from_path(entry.path, browser_type)
        uri = f"file:{temp_path.as_posix()}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
        except sqlite3.Error as exc:
            logger.warning(
                "Failed to open browser database %s: %s",
                entry.path,
                exc,
            )
            return artefacts

        conn.row_factory = sqlite3.Row
        try:
            query = (
                FIREFOX_HISTORY_QUERY
                if browser_type == "firefox"
                else CHROME_HISTORY_QUERY
            )
            try:
                rows = conn.execute(f"{query} LIMIT ?", (max(0, remaining),))
            except sqlite3.Error as exc:
                logger.warning(
                    "Failed to query browser database %s: %s",
                    entry.path,
                    exc,
                )
                return artefacts

            time_column = (
                "last_visit_date" if browser_type == "firefox" else "last_visit_time"
            )
            for row in rows:
                if len(artefacts) >= remaining:
                    break
                raw_ts = row[time_column]
                converted = convert_timestamp(raw_ts)
                artefacts.append(
                    self._create_artefact(
                        category=ArtefactCategory.BROWSER_HISTORY,
                        evidence_id=evidence_id,
                        source_path=entry.path,
                        raw_data={
                            "url": row["url"],
                            "title": row["title"],
                            "visit_count": int(row["visit_count"] or 0),
                            "last_visit_time": (
                                converted.isoformat() if converted is not None else None
                            ),
                            "browser_type": browser_type,
                            "profile": profile,
                        },
                    )
                )
        finally:
            conn.close()
        return artefacts

    @staticmethod
    def _profile_from_path(path: str, browser_type: str) -> str:
        """Best-effort profile name extraction from the DB path."""
        parts = [p for p in sanitise_path(path).split("/") if p]
        lowered = [p.lower() for p in parts]
        if browser_type == "firefox":
            try:
                idx = lowered.index("profiles")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
            except ValueError:
                pass
        if browser_type in {"chrome", "edge"}:
            try:
                idx = lowered.index("user data")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
            except ValueError:
                pass
        return "Default"

    @staticmethod
    def _cleanup_temps(temp_files: list[Path], temp_dir: Path) -> None:
        """Remove extracted database files and the temporary directory."""
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
