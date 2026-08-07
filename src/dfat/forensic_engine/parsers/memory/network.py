"""Volatility3 network connection parser (netscan).

Artefact ``raw_data`` schema for ``NETWORK_CONNECTION`` (contract)::

    {
        "protocol": str,
        "local_address": str,
        "local_port": int | null,
        "remote_address": str,
        "remote_port": int | null,
        "state": str,
        "pid": int | null,
        "owner_process": str | null,
        "created_time": ISO-8601 str | null,
        "is_external": bool,
    }

``is_external`` is ``True`` when ``remote_address`` is a public (non-private)
IPv4/IPv6 address.
"""

from __future__ import annotations

import asyncio
import ipaddress
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import MemoryParsingError
from dfat.core.models.artefact import Artefact
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.memory.plugin_executor import PluginExecutor
from dfat.forensic_engine.parsers.utils import convert_timestamp
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.constants import MAX_ARTEFACTS_PER_CATEGORY

_NETSCAN_MODULE = "volatility3.plugins.windows.netscan"


class NetworkArtefactParser(BaseParser):
    """Extract network connection artefacts from memory dumps via ``netscan``."""

    _parse_error_class = MemoryParsingError

    def __init__(
        self,
        plugin_executor: PluginExecutor,
        audit_logger: ForensicAuditLogger,
        max_artefacts: int = MAX_ARTEFACTS_PER_CATEGORY,
    ) -> None:
        """Initialise the network artefact parser.

        Args:
            plugin_executor: Async Volatility3 plugin executor.
            audit_logger: ACPO-compliant forensic audit logger.
            max_artefacts: Maximum artefacts retained for a single parse.
        """
        super().__init__(audit_logger=audit_logger, max_artefacts=max_artefacts)
        self._executor = plugin_executor

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

    def _do_parse(self, evidence: EvidenceImage) -> list[Artefact]:
        """Extract network connections using Volatility3 ``netscan``."""
        dump_path = Path(evidence.file_path)
        rows = self._await(
            self._executor.execute_plugin(
                dump_path,
                "NetScan",
                _NETSCAN_MODULE,
                evidence.evidence_id,
            )
        )
        artefacts: list[Artefact] = []
        for row in rows:
            if not self._check_limit(len(artefacts)):
                break
            artefacts.append(
                self._create_artefact(
                    category=ArtefactCategory.NETWORK_CONNECTION,
                    evidence_id=evidence.evidence_id,
                    source_path=str(dump_path),
                    raw_data=self._map_row(row),
                )
            )
        return artefacts

    def _map_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Map a Volatility ``netscan`` row to the ``NETWORK_CONNECTION`` schema."""
        local_addr = self._as_str(
            row.get("LocalAddr", row.get("local_address", row.get("LocalAddress")))
        )
        remote_addr = self._as_str(
            row.get(
                "ForeignAddr",
                row.get("remote_address", row.get("ForeignAddress", row.get("RemoteAddr"))),
            )
        )
        created = convert_timestamp(
            row.get("Created", row.get("created_time", row.get("CreateTime")))
        )
        return {
            "protocol": self._as_str(row.get("Proto", row.get("protocol"))),
            "local_address": local_addr,
            "local_port": self._as_int(row.get("LocalPort", row.get("local_port"))),
            "remote_address": remote_addr,
            "remote_port": self._as_int(
                row.get("ForeignPort", row.get("remote_port", row.get("RemotePort")))
            ),
            "state": self._as_str(row.get("State", row.get("state"))),
            "pid": self._as_int(row.get("PID", row.get("pid"))),
            "owner_process": self._as_str(
                row.get("Owner", row.get("owner_process", row.get("Process")))
            ),
            "created_time": created.isoformat() if created is not None else None,
            "is_external": self._is_external(remote_addr),
        }

    @staticmethod
    def _is_external(remote_address: Optional[str]) -> bool:
        """Return ``True`` when ``remote_address`` is outside private ranges.

        Private ranges covered via ``ipaddress`` (RFC 1918 / ULA): ``10.0.0.0/8``,
        ``172.16.0.0/12``, ``192.168.0.0/16``, plus loopback/link-local/unspecified.
        """
        host = NetworkArtefactParser._extract_host(remote_address)
        if host is None:
            return False
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
            return False
        if ip.is_multicast or ip.is_reserved:
            return False
        return True

    @staticmethod
    def _extract_host(address: Optional[str]) -> Optional[str]:
        """Extract host from an address that may include a port."""
        if address is None:
            return None
        text = str(address).strip()
        if not text or text in {"*", "-", "N/A", "None"}:
            return None
        if text.startswith("["):
            end = text.find("]")
            if end > 1:
                return text[1:end]
        # IPv4 or hostname with optional :port (not IPv6)
        if text.count(":") == 1:
            return text.rsplit(":", 1)[0]
        return text

    @staticmethod
    def _as_int(value: Any) -> Optional[int]:
        """Best-effort integer coercion."""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_str(value: Any) -> Optional[str]:
        """Best-effort string coercion."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _await(coro: Any) -> Any:
        """Run an async coroutine from sync ``_do_parse`` safely."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
