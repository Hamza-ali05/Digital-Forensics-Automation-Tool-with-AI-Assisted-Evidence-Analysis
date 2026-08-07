"""Volatility3 in-memory registry parser (hivelist + printkey).

Artefact ``raw_data`` schema for ``REGISTRY_KEY`` (contract)::

    {
        "hive_name": str,
        "key_path": str,
        "value_name": str,
        "value_data": str,
        "value_type": str,
        "last_modified": ISO-8601 str | null,
        "source": "memory",
    }

Matches the disk :class:`~dfat.forensic_engine.parsers.registry.RegistryParser`
contract and adds ``source=\"memory\"`` to distinguish provenance.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import MemoryParsingError
from dfat.core.models.artefact import Artefact
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.memory.plugin_executor import PluginExecutor
from dfat.forensic_engine.parsers.utils import convert_timestamp, truncate_data
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.constants import MAX_ARTEFACTS_PER_CATEGORY

logger = logging.getLogger(__name__)

_HIVELIST_MODULE = "volatility3.plugins.windows.registry.hivelist"
_PRINTKEY_MODULE = "volatility3.plugins.windows.registry.printkey"


class MemoryRegistryParser(BaseParser):
    """Extract registry key/value artefacts from memory dumps.

    Runs Volatility3 ``HiveList`` to locate loaded hives, then ``PrintKey``
    (with ``recurse=True``) for each hive offset. Failed per-hive dumps are
    skipped so one corrupt hive does not abort the parse.
    """

    _parse_error_class = MemoryParsingError

    def __init__(
        self,
        plugin_executor: PluginExecutor,
        audit_logger: ForensicAuditLogger,
        max_artefacts: int = MAX_ARTEFACTS_PER_CATEGORY,
    ) -> None:
        """Initialise the memory registry parser.

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
        return "MemoryRegistryParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return supported artefact categories."""
        return [ArtefactCategory.REGISTRY_KEY]

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return supported evidence types."""
        return [EvidenceType.MEMORY_DUMP]

    def _do_parse(self, evidence: EvidenceImage) -> list[Artefact]:
        """Run ``hivelist`` then ``printkey`` for each discovered hive."""
        dump_path = Path(evidence.file_path)
        hive_rows = self._await(
            self._executor.execute_plugin(
                dump_path,
                "HiveList",
                _HIVELIST_MODULE,
                evidence.evidence_id,
            )
        )
        artefacts: list[Artefact] = []
        for hive in hive_rows:
            if not self._check_limit(len(artefacts)):
                break
            offset = self._as_int(hive.get("Offset", hive.get("offset")))
            if offset is None:
                continue
            hive_name = self._hive_name_from_row(hive)
            hive_path = self._as_str(
                hive.get("FileFullPath", hive.get("Name", hive.get("file_path")))
            ) or hive_name

            try:
                key_rows = self._await(
                    self._executor.execute_plugin(
                        dump_path,
                        "PrintKey",
                        _PRINTKEY_MODULE,
                        evidence.evidence_id,
                        config={"offset": offset, "recurse": True},
                    )
                )
            except Exception as exc:  # noqa: BLE001 — skip corrupt hive
                logger.warning(
                    "printkey failed for hive offset %#x (%s) on %s: %s",
                    offset,
                    hive_name,
                    evidence.evidence_id,
                    exc,
                )
                continue

            for row in key_rows:
                if not self._check_limit(len(artefacts)):
                    break
                mapped = self._map_value_row(row, hive_name)
                if mapped is None:
                    continue
                artefacts.append(
                    self._create_artefact(
                        category=ArtefactCategory.REGISTRY_KEY,
                        evidence_id=evidence.evidence_id,
                        source_path=str(hive_path),
                        raw_data=mapped,
                    )
                )
        return artefacts

    def _map_value_row(
        self,
        row: dict[str, Any],
        hive_name: str,
    ) -> Optional[dict[str, Any]]:
        """Map a ``PrintKey`` value row to the ``REGISTRY_KEY`` schema.

        Rows that describe keys (Type ``Key``) rather than values are skipped
        so the contract matches the disk registry parser.
        """
        value_type = self._as_str(row.get("Type", row.get("value_type")))
        if value_type is not None and value_type.lower() == "key":
            return None

        last_modified = convert_timestamp(
            row.get("Last Write Time", row.get("last_modified", row.get("LastWrite")))
        )
        value_data = row.get("Data", row.get("value_data"))
        if value_data is None:
            value_data = ""
        return {
            "hive_name": hive_name,
            "key_path": self._as_str(row.get("Key", row.get("key_path"))) or "",
            "value_name": self._as_str(row.get("Name", row.get("value_name"))) or "",
            "value_data": truncate_data(str(value_data)),
            "value_type": value_type or "",
            "last_modified": last_modified.isoformat() if last_modified else None,
            "source": "memory",
        }

    @staticmethod
    def _hive_name_from_row(row: dict[str, Any]) -> str:
        """Derive a short hive name from a ``HiveList`` row."""
        path = row.get("FileFullPath", row.get("Name", row.get("file_path")))
        if path is None or str(path).strip() in {"", "-", "None"}:
            offset = row.get("Offset", row.get("offset"))
            return f"hive_{offset}" if offset is not None else "unknown"
        text = str(path).replace("\\", "/").rstrip("/")
        name = text.rsplit("/", 1)[-1]
        return name or text

    @staticmethod
    def _as_int(value: Any) -> Optional[int]:
        """Best-effort integer coercion (including Volatility Hex hints)."""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            text = str(value).strip()
            try:
                if text.lower().startswith("0x"):
                    return int(text, 16)
                return int(text)
            except ValueError:
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
