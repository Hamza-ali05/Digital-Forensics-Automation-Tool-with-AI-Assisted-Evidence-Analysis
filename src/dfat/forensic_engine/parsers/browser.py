"""Browser history parser for Chrome/Firefox SQLite databases.

Artefact ``raw_data`` schema for ``BROWSER_HISTORY``:
    url, title, visit_count, last_visit_time, browser_type
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import DiskParsingError
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers import _tsk_utils
from dfat.forensic_engine.parsers.base import BaseParser


class BrowserHistoryParser(BaseParser):
    """Extract browser history artefacts from disk images."""

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

    def parse(self, evidence: EvidenceImage) -> ArtefactSet:
        """Locate and parse Chrome/Firefox history databases.

        Args:
            evidence: Disk image evidence metadata.

        Returns:
            Artefact set of browser history entries.

        Raises:
            ImportError: If ``pytsk3`` is not installed.
            DiskParsingError: If parsing fails fatally.
        """
        self._log_parse_start(evidence.evidence_id)
        _tsk_utils.require_pytsk3()
        artefacts: list[Artefact] = []
        try:
            histories = _tsk_utils.find_files(
                evidence.file_path,
                predicate=lambda p: p.lower().endswith("/history")
                or p.lower().endswith("\\history")
                or p.lower().endswith("places.sqlite"),
                limit=20,
            )
            for db_path, content in histories:
                if len(artefacts) >= self._max_artefacts:
                    break
                browser = (
                    "firefox"
                    if db_path.lower().endswith("places.sqlite")
                    else "chrome"
                )
                artefacts.extend(
                    self._parse_sqlite(
                        content,
                        db_path,
                        evidence.evidence_id,
                        browser,
                        remaining=self._max_artefacts - len(artefacts),
                    )
                )
        except ImportError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._log_parse_error(evidence.evidence_id, exc)
            raise DiskParsingError(
                f"BrowserHistoryParser failed for {evidence.file_path}",
                context={"evidence_id": evidence.evidence_id, "error": str(exc)},
            ) from exc

        artefacts = self._truncate(artefacts)
        result = self._to_artefact_set(evidence.evidence_id, artefacts)
        self._log_parse_end(evidence.evidence_id, len(artefacts))
        return result

    def _parse_sqlite(
        self,
        content: bytes,
        source_path: str,
        evidence_id: str,
        browser_type: str,
        remaining: int,
    ) -> list[Artefact]:
        """Parse a browser SQLite database blob.

        Args:
            content: Database bytes.
            source_path: Path within the image.
            evidence_id: Evidence identifier.
            browser_type: ``chrome`` or ``firefox``.
            remaining: Remaining artefact capacity.

        Returns:
            List of browser history artefacts.
        """
        artefacts: list[Artefact] = []
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        try:
            conn = sqlite3.connect(f"file:{temp_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                if browser_type == "firefox":
                    rows = conn.execute(
                        "SELECT url, title, visit_count, last_visit_date "
                        "AS last_visit_time FROM moz_places LIMIT ?",
                        (remaining,),
                    )
                else:
                    rows = conn.execute(
                        "SELECT url, title, visit_count, last_visit_time "
                        "FROM urls LIMIT ?",
                        (remaining,),
                    )
                for row in rows:
                    artefacts.append(
                        self._create_artefact(
                            category=ArtefactCategory.BROWSER_HISTORY,
                            evidence_id=evidence_id,
                            source_path=source_path,
                            raw_data={
                                "url": row["url"],
                                "title": row["title"],
                                "visit_count": row["visit_count"],
                                "last_visit_time": row["last_visit_time"],
                                "browser_type": browser_type,
                            },
                        )
                    )
            except sqlite3.Error:
                return []
            finally:
                conn.close()
        finally:
            temp_path.unlink(missing_ok=True)
        return artefacts
