"""Volatility3 injected-code parser (malfind).

Artefact ``raw_data`` schema for ``INJECTED_CODE``:
    pid, process_name, vad_start, vad_end, protection, tag, hex_dump_preview
"""

from __future__ import annotations

from typing import Any

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import MemoryParsingError
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.memory import _volatility_utils


class CodeInjectionParser(BaseParser):
    """Detect injected code artefacts from memory dumps via malfind."""

    @property
    def parser_name(self) -> str:
        """Return the stable parser identifier."""
        return "CodeInjectionParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return supported artefact categories."""
        return [ArtefactCategory.INJECTED_CODE]

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return supported evidence types."""
        return [EvidenceType.MEMORY_DUMP]

    def parse(self, evidence: EvidenceImage) -> ArtefactSet:
        """Extract injected-code findings using Volatility3 malfind.

        Args:
            evidence: Memory dump evidence metadata.

        Returns:
            Artefact set of injected-code findings.

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
                "windows.malfind.Malfind",
            ):
                if len(artefacts) >= self._max_artefacts:
                    break
                artefacts.append(
                    self._create_artefact(
                        category=ArtefactCategory.INJECTED_CODE,
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
                f"CodeInjectionParser failed for {evidence.file_path}",
                context={"evidence_id": evidence.evidence_id, "error": str(exc)},
            ) from exc

        artefacts = self._truncate(artefacts)
        result = self._to_artefact_set(evidence.evidence_id, artefacts)
        self._log_parse_end(evidence.evidence_id, len(artefacts))
        return result

    @staticmethod
    def _map_row(row: dict[str, Any]) -> dict[str, Any]:
        """Map a Volatility row to the INJECTED_CODE schema."""
        hex_preview = row.get("Hexdump", row.get("hex_dump_preview", ""))
        if isinstance(hex_preview, (bytes, bytearray)):
            hex_preview = bytes(hex_preview)[:64].hex()
        elif isinstance(hex_preview, str):
            hex_preview = hex_preview[:128]
        return {
            "pid": row.get("PID", row.get("pid")),
            "process_name": row.get("Process", row.get("process_name")),
            "vad_start": row.get("Start VPN", row.get("vad_start")),
            "vad_end": row.get("End VPN", row.get("vad_end")),
            "protection": row.get("Protection", row.get("protection")),
            "tag": row.get("Tag", row.get("tag")),
            "hex_dump_preview": hex_preview,
        }
