"""Volatility3 network connection parser (netscan).

Artefact ``raw_data`` schema for ``NETWORK_CONNECTION``:
    protocol, local_address, local_port, remote_address, remote_port,
    state, pid, owner_process
"""

from __future__ import annotations

from typing import Any

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import MemoryParsingError
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.memory import _volatility_utils


class NetworkArtefactParser(BaseParser):
    """Extract network connection artefacts from memory dumps."""

    @property
    def parser_name(self) -> str:
        """Return the stable parser identifier."""
        return "NetworkArtefactParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return supported artefact categories."""
        return [ArtefactCategory.NETWORK_CONNECTION]

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return supported evidence types."""
        return [EvidenceType.MEMORY_DUMP]

    def parse(self, evidence: EvidenceImage) -> ArtefactSet:
        """Extract network connections using Volatility3 netscan.

        Args:
            evidence: Memory dump evidence metadata.

        Returns:
            Artefact set of network connections.

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
                "windows.netscan.NetScan",
            ):
                if len(artefacts) >= self._max_artefacts:
                    break
                artefacts.append(
                    self._create_artefact(
                        category=ArtefactCategory.NETWORK_CONNECTION,
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
                f"NetworkArtefactParser failed for {evidence.file_path}",
                context={"evidence_id": evidence.evidence_id, "error": str(exc)},
            ) from exc

        artefacts = self._truncate(artefacts)
        result = self._to_artefact_set(evidence.evidence_id, artefacts)
        self._log_parse_end(evidence.evidence_id, len(artefacts))
        return result

    @staticmethod
    def _map_row(row: dict[str, Any]) -> dict[str, Any]:
        """Map a Volatility row to the NETWORK_CONNECTION schema."""
        return {
            "protocol": row.get("Proto", row.get("protocol")),
            "local_address": row.get("LocalAddr", row.get("local_address")),
            "local_port": row.get("LocalPort", row.get("local_port")),
            "remote_address": row.get("ForeignAddr", row.get("remote_address")),
            "remote_port": row.get("ForeignPort", row.get("remote_port")),
            "state": row.get("State", row.get("state")),
            "pid": row.get("PID", row.get("pid")),
            "owner_process": row.get("Owner", row.get("owner_process")),
        }
