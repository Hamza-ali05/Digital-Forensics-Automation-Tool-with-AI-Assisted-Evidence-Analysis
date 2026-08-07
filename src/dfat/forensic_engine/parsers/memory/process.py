"""Volatility3 process list parser (pslist / pstree).

Artefact ``raw_data`` schema for ``RUNNING_PROCESS`` (contract)::

    {
        "pid": int,
        "ppid": int,
        "name": str,
        "create_time": ISO-8601 str | null,
        "exit_time": ISO-8601 str | null,
        "session_id": int | null,
        "handles": int | null,
        "threads": int | null,
        "wow64": bool | null,
        "command_line": str | null,
        "parent_name": str | null,
    }
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
from dfat.forensic_engine.parsers.utils import convert_timestamp
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.constants import MAX_ARTEFACTS_PER_CATEGORY

logger = logging.getLogger(__name__)

_PSLIST_MODULE = "volatility3.plugins.windows.pslist"
_PSTREE_MODULE = "volatility3.plugins.windows.pstree"


class ProcessListParser(BaseParser):
    """Extract running process artefacts from memory dumps via Volatility3.

    Primary source is ``pslist``. ``pstree`` is run optionally to enrich
    parent process names when available.
    """

    _parse_error_class = MemoryParsingError

    def __init__(
        self,
        plugin_executor: PluginExecutor,
        audit_logger: ForensicAuditLogger,
        max_artefacts: int = MAX_ARTEFACTS_PER_CATEGORY,
        *,
        run_pstree: bool = True,
    ) -> None:
        """Initialise the process list parser.

        Args:
            plugin_executor: Async Volatility3 plugin executor.
            audit_logger: ACPO-compliant forensic audit logger.
            max_artefacts: Maximum artefacts retained for a single parse.
            run_pstree: When ``True``, also run ``pstree`` for parent names.
        """
        super().__init__(audit_logger=audit_logger, max_artefacts=max_artefacts)
        self._executor = plugin_executor
        self._run_pstree = run_pstree

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

    def _do_parse(self, evidence: EvidenceImage) -> list[Artefact]:
        """Extract processes using Volatility3 ``pslist`` (and optional ``pstree``)."""
        dump_path = Path(evidence.file_path)
        pslist_rows = self._await(
            self._executor.execute_plugin(
                dump_path,
                "PsList",
                _PSLIST_MODULE,
                evidence.evidence_id,
            )
        )

        parent_names: dict[int, str] = {}
        if self._run_pstree:
            try:
                pstree_rows = self._await(
                    self._executor.execute_plugin(
                        dump_path,
                        "PsTree",
                        _PSTREE_MODULE,
                        evidence.evidence_id,
                    )
                )
                parent_names = self._parent_names_from_pstree(pstree_rows)
            except Exception as exc:  # noqa: BLE001 — pstree is optional enrichment
                logger.warning(
                    "pstree enrichment failed for %s: %s",
                    evidence.evidence_id,
                    exc,
                )

        artefacts: list[Artefact] = []
        for row in pslist_rows:
            if not self._check_limit(len(artefacts)):
                break
            raw = self._map_row(row, parent_names)
            artefacts.append(
                self._create_artefact(
                    category=ArtefactCategory.RUNNING_PROCESS,
                    evidence_id=evidence.evidence_id,
                    source_path=str(dump_path),
                    raw_data=raw,
                )
            )
        return artefacts

    def _map_row(
        self,
        row: dict[str, Any],
        parent_names: dict[int, str],
    ) -> dict[str, Any]:
        """Map a Volatility row to the ``RUNNING_PROCESS`` schema."""
        pid = self._as_int(row.get("PID", row.get("pid", row.get("col_0"))))
        ppid = self._as_int(row.get("PPID", row.get("ppid", row.get("col_1"))))
        name = row.get("ImageFileName", row.get("Name", row.get("name", row.get("col_2"))))
        create = convert_timestamp(
            row.get("CreateTime", row.get("create_time", row.get("Created")))
        )
        exit_t = convert_timestamp(
            row.get("ExitTime", row.get("exit_time", row.get("Exited")))
        )
        parent_name = None
        if ppid is not None:
            parent_name = parent_names.get(ppid)
        if parent_name is None:
            parent_name = row.get("Parent", row.get("parent_name"))

        cmdline = row.get("CommandLine", row.get("command_line", row.get("Cmd")))
        wow64 = row.get("Wow64", row.get("wow64"))
        if isinstance(wow64, str):
            wow64 = wow64.strip().lower() in {"true", "1", "yes"}

        return {
            "pid": pid,
            "ppid": ppid,
            "name": str(name) if name is not None else None,
            "create_time": create.isoformat() if create is not None else None,
            "exit_time": exit_t.isoformat() if exit_t is not None else None,
            "session_id": self._as_int(
                row.get("SessionId", row.get("session_id", row.get("Session")))
            ),
            "handles": self._as_int(row.get("Handles", row.get("handles"))),
            "threads": self._as_int(row.get("Threads", row.get("threads"))),
            "wow64": wow64 if isinstance(wow64, bool) else None,
            "command_line": str(cmdline) if cmdline not in (None, "") else None,
            "parent_name": str(parent_name) if parent_name not in (None, "") else None,
        }

    @staticmethod
    def _parent_names_from_pstree(rows: list[dict[str, Any]]) -> dict[int, str]:
        """Build PID → process name map from ``pstree`` rows for parent lookup."""
        names: dict[int, str] = {}
        for row in rows:
            pid = ProcessListParser._as_int(
                row.get("PID", row.get("pid", row.get("col_0")))
            )
            name = row.get(
                "ImageFileName",
                row.get("Name", row.get("name", row.get("col_2"))),
            )
            if pid is not None and name not in (None, ""):
                names[pid] = str(name)
        return names

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
    def _await(coro: Any) -> Any:
        """Run an async coroutine from sync ``_do_parse`` safely."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        # Already inside an event loop (or nested): run in a fresh thread.
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
