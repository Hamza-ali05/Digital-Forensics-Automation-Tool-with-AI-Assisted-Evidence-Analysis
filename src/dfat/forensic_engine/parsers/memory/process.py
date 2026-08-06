"""Volatility3 process list parser (pslist).

Artefact ``raw_data`` schema for ``RUNNING_PROCESS``:
    pid, ppid, name, create_time, exit_time, session_id, handles, threads, wow64
"""

from __future__ import annotations

from typing import Any

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import MemoryParsingError
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.memory import _volatility_utils


class ProcessListParser(BaseParser):
    """Extract running process artefacts from memory dumps."""

    @property
    def parser_name(self) -> str:
        """Return the stable parser identifier."""
        return "ProcessListParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return supported artefact categories."""
        return [ArtefactCategory.RUNNING_PROCESS]

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return supported evidence types."""
        return [EvidenceType.MEMORY_DUMP]

    def parse(self, evidence: EvidenceImage) -> ArtefactSet:
        """Extract processes using Volatility3 pslist.

        Args:
            evidence: Memory dump evidence metadata.

        Returns:
            Artefact set of running processes.

        Raises:
            ImportError: If ``volatility3`` is not installed.
            MemoryParsingError: If Volatility execution fails.
        """
        self._log_parse_start(evidence.evidence_id)
        _volatility_utils.require_volatility3()
        artefacts: list[Artefact] = []
        try:
            for row in _volatility_utils.iter_plugin_rows(
                evidence.file_path,
                "windows.pslist.PsList",
            ):
                if len(artefacts) >= self._max_artefacts:
                    break
                artefacts.append(
                    self._create_artefact(
                        category=ArtefactCategory.RUNNING_PROCESS,
                        evidence_id=evidence.evidence_id,
                        source_path=str(evidence.file_path),
                        raw_data=self._map_row(row),
                    )
                )
        except ImportError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._log_parse_error(evidence.evidence_id, exc)
            raise MemoryParsingError(
                f"ProcessListParser failed for {evidence.file_path}",
                context={"evidence_id": evidence.evidence_id, "error": str(exc)},
            ) from exc

        artefacts = self._truncate(artefacts)
        result = self._to_artefact_set(evidence.evidence_id, artefacts)
        self._log_parse_end(evidence.evidence_id, len(artefacts))
        return result

    @staticmethod
    def _map_row(row: dict[str, Any]) -> dict[str, Any]:
        """Map a Volatility row to the RUNNING_PROCESS schema."""
        return {
            "pid": row.get("PID", row.get("pid", row.get("col_0"))),
            "ppid": row.get("PPID", row.get("ppid", row.get("col_1"))),
            "name": row.get("ImageFileName", row.get("name", row.get("col_2"))),
            "create_time": row.get("CreateTime", row.get("create_time")),
            "exit_time": row.get("ExitTime", row.get("exit_time")),
            "session_id": row.get("SessionId", row.get("session_id")),
            "handles": row.get("Handles", row.get("handles")),
            "threads": row.get("Threads", row.get("threads")),
            "wow64": row.get("Wow64", row.get("wow64")),
        }
