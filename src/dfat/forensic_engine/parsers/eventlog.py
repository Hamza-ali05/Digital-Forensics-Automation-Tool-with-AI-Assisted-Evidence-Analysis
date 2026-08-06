"""Windows Event Log (.evtx) parser using python-evtx.

Artefact ``raw_data`` schema for ``EVENT_LOG``:
    event_id, timestamp, source, level, computer_name, message_text, channel
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import DiskParsingError
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers import _tsk_utils
from dfat.forensic_engine.parsers.base import BaseParser


class EventLogParser(BaseParser):
    """Extract Windows event log artefacts from disk images."""

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

    def parse(self, evidence: EvidenceImage) -> ArtefactSet:
        """Locate and parse ``.evtx`` files from the disk image.

        Args:
            evidence: Disk image evidence metadata.

        Returns:
            Artefact set of event log entries.

        Raises:
            ImportError: If ``pytsk3`` or ``python-evtx`` is not installed.
            DiskParsingError: If parsing fails fatally.
        """
        self._log_parse_start(evidence.evidence_id)
        try:
            from Evtx.Evtx import Evtx
        except ImportError as exc:
            raise ImportError(
                "python-evtx is required for event log parsing. Install with: "
                "pip install python-evtx"
            ) from exc

        _tsk_utils.require_pytsk3()
        artefacts: list[Artefact] = []
        try:
            logs = _tsk_utils.find_files(
                evidence.file_path,
                predicate=lambda p: p.lower().endswith(".evtx"),
                limit=20,
            )
            for log_path, content in logs:
                if len(artefacts) >= self._max_artefacts:
                    break
                artefacts.extend(
                    self._parse_evtx(
                        content,
                        log_path,
                        evidence.evidence_id,
                        Evtx,
                        remaining=self._max_artefacts - len(artefacts),
                    )
                )
        except ImportError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._log_parse_error(evidence.evidence_id, exc)
            raise DiskParsingError(
                f"EventLogParser failed for {evidence.file_path}",
                context={"evidence_id": evidence.evidence_id, "error": str(exc)},
            ) from exc

        artefacts = self._truncate(artefacts)
        result = self._to_artefact_set(evidence.evidence_id, artefacts)
        self._log_parse_end(evidence.evidence_id, len(artefacts))
        return result

    def _parse_evtx(
        self,
        content: bytes,
        source_path: str,
        evidence_id: str,
        evtx_cls: Any,
        remaining: int,
    ) -> list[Artefact]:
        """Parse an EVTX blob from temporary storage.

        Args:
            content: EVTX file bytes.
            source_path: Path within the image.
            evidence_id: Evidence identifier.
            evtx_cls: ``Evtx`` class constructor.
            remaining: Remaining artefact capacity.

        Returns:
            List of event log artefacts.
        """
        artefacts: list[Artefact] = []
        with tempfile.NamedTemporaryFile(suffix=".evtx", delete=False) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        try:
            with evtx_cls(str(temp_path)) as log:
                for record in log.records():
                    if len(artefacts) >= remaining:
                        break
                    try:
                        xml = record.xml()
                        artefacts.append(
                            self._create_artefact(
                                category=ArtefactCategory.EVENT_LOG,
                                evidence_id=evidence_id,
                                source_path=source_path,
                                raw_data={
                                    "event_id": self._extract_tag(xml, "EventID"),
                                    "timestamp": str(record.timestamp()),
                                    "source": self._extract_tag(xml, "Provider"),
                                    "level": self._extract_tag(xml, "Level"),
                                    "computer_name": self._extract_tag(
                                        xml, "Computer"
                                    ),
                                    "message_text": xml[:2000],
                                    "channel": self._extract_tag(xml, "Channel"),
                                },
                            )
                        )
                    except Exception:  # noqa: BLE001
                        continue
        except Exception:  # noqa: BLE001 - skip corrupt logs
            return []
        finally:
            temp_path.unlink(missing_ok=True)
        return artefacts

    @staticmethod
    def _extract_tag(xml: str, tag: str) -> str | None:
        """Best-effort extraction of a simple XML tag value.

        Args:
            xml: Event XML string.
            tag: Tag name to locate.

        Returns:
            Tag text if found; otherwise None.
        """
        start = xml.find(f"<{tag}")
        if start < 0:
            return None
        start = xml.find(">", start)
        end = xml.find(f"</{tag}>", start)
        if start < 0 or end < 0:
            return None
        return xml[start + 1 : end].strip() or None
