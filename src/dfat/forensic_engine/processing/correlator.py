"""Artefact correlation — cross-category relationship linking."""

from __future__ import annotations

import logging
import re
from pathlib import PureWindowsPath
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory
from dfat.core.models.artefact import Artefact, ArtefactSet
from dfat.forensic_engine.parsers.utils import sanitise_path

logger = logging.getLogger(__name__)

_PID_RE = re.compile(r"\b(?:pid|process\s*id)\s*[=:]\s*(\d+)\b", re.IGNORECASE)
_PATH_IN_VALUE_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"']+|\\\\[^\s\"']+|/[^\\s\"']+)",
)


class ArtefactCorrelator:
    """Identify relationships between artefacts across categories.

    Correlation rules:
        1. Process ↔ network (shared PID)
        2. Registry ↔ filesystem (path in registry value)
        3. Process ↔ injected code (shared PID)
        4. Event log ↔ process (PID / process name)
    """

    def correlate(self, artefact_set: ArtefactSet) -> ArtefactSet:
        """Build bidirectional correlation links and enrich metadata.

        Stores ``metadata["correlated_artefact_ids"]`` as a list of related
        artefact IDs (stable sorted, excluding self).

        Args:
            artefact_set: Deduplicated artefact collection.

        Returns:
            Enriched ``ArtefactSet`` with correlation metadata.
        """
        artefacts = list(artefact_set.artefacts)
        if not artefacts:
            return artefact_set

        by_category = self._group_by_category(artefacts)
        links: dict[str, set[str]] = {item.artefact_id: set() for item in artefacts}

        self._link_process_network(
            by_category.get(ArtefactCategory.RUNNING_PROCESS, []),
            by_category.get(ArtefactCategory.NETWORK_CONNECTION, []),
            links,
        )
        self._link_registry_filesystem(
            by_category.get(ArtefactCategory.REGISTRY_KEY, []),
            by_category.get(ArtefactCategory.FILESYSTEM_METADATA, []),
            links,
        )
        self._link_process_injection(
            by_category.get(ArtefactCategory.RUNNING_PROCESS, []),
            by_category.get(ArtefactCategory.INJECTED_CODE, []),
            links,
        )
        self._link_event_process(
            by_category.get(ArtefactCategory.EVENT_LOG, []),
            by_category.get(ArtefactCategory.RUNNING_PROCESS, []),
            links,
        )

        enriched: list[Artefact] = []
        total_edges = 0
        for artefact in artefacts:
            related = sorted(links.get(artefact.artefact_id, set()))
            total_edges += len(related)
            metadata = dict(artefact.metadata)
            metadata["correlated_artefact_ids"] = related
            enriched.append(artefact.model_copy(update={"metadata": metadata}))

        logger.info(
            "Correlated artefacts for evidence %s: %d directed links across %d artefacts",
            artefact_set.evidence_id,
            total_edges,
            len(enriched),
        )
        return artefact_set.model_copy(update={"artefacts": enriched})

    @staticmethod
    def _group_by_category(
        artefacts: list[Artefact],
    ) -> dict[ArtefactCategory, list[Artefact]]:
        """Bucket artefacts by category."""
        groups: dict[ArtefactCategory, list[Artefact]] = {}
        for artefact in artefacts:
            groups.setdefault(artefact.category, []).append(artefact)
        return groups

    def _link_process_network(
        self,
        processes: list[Artefact],
        connections: list[Artefact],
        links: dict[str, set[str]],
    ) -> None:
        """Match RUNNING_PROCESS ↔ NETWORK_CONNECTION on PID."""
        by_pid = self._index_by_pid(processes, pid_keys=("pid",))
        for conn in connections:
            pid = self._as_int(conn.raw_data.get("pid"))
            if pid is None:
                continue
            for process in by_pid.get(pid, []):
                self._link(links, process.artefact_id, conn.artefact_id)

    def _link_registry_filesystem(
        self,
        registry_keys: list[Artefact],
        files: list[Artefact],
        links: dict[str, set[str]],
    ) -> None:
        """Match REGISTRY_KEY value paths against FILESYSTEM_METADATA paths."""
        files_by_path = self._index_filesystem_paths(files)
        if not files_by_path:
            return
        for reg in registry_keys:
            for candidate in self._registry_path_candidates(reg.raw_data):
                normalised = self._normalise_path_key(candidate)
                matches = files_by_path.get(normalised, [])
                if not matches:
                    # Try basename match for relative registry values.
                    base = self._basename(normalised)
                    matches = files_by_path.get(base, [])
                for file_art in matches:
                    self._link(links, reg.artefact_id, file_art.artefact_id)

    def _link_process_injection(
        self,
        processes: list[Artefact],
        injections: list[Artefact],
        links: dict[str, set[str]],
    ) -> None:
        """Match RUNNING_PROCESS ↔ INJECTED_CODE on PID."""
        by_pid = self._index_by_pid(processes, pid_keys=("pid",))
        for inj in injections:
            pid = self._as_int(inj.raw_data.get("pid"))
            if pid is None:
                continue
            for process in by_pid.get(pid, []):
                self._link(links, process.artefact_id, inj.artefact_id)

    def _link_event_process(
        self,
        events: list[Artefact],
        processes: list[Artefact],
        links: dict[str, set[str]],
    ) -> None:
        """Match EVENT_LOG entries to RUNNING_PROCESS by PID or process name."""
        by_pid = self._index_by_pid(processes, pid_keys=("pid",))
        by_name = self._index_by_process_name(processes)
        for event in events:
            pids, names = self._extract_event_process_refs(event.raw_data)
            for pid in pids:
                for process in by_pid.get(pid, []):
                    self._link(links, event.artefact_id, process.artefact_id)
            for name in names:
                for process in by_name.get(name, []):
                    self._link(links, event.artefact_id, process.artefact_id)

    def _index_by_pid(
        self,
        artefacts: list[Artefact],
        pid_keys: tuple[str, ...],
    ) -> dict[int, list[Artefact]]:
        """Index artefacts by integer PID fields."""
        index: dict[int, list[Artefact]] = {}
        for artefact in artefacts:
            for key in pid_keys:
                pid = self._as_int(artefact.raw_data.get(key))
                if pid is not None:
                    index.setdefault(pid, []).append(artefact)
                    break
        return index

    def _index_by_process_name(
        self,
        processes: list[Artefact],
    ) -> dict[str, list[Artefact]]:
        """Index processes by lowercased image name."""
        index: dict[str, list[Artefact]] = {}
        for process in processes:
            name = process.raw_data.get("name") or process.raw_data.get("process_name")
            key = self._normalise_process_name(name)
            if key:
                index.setdefault(key, []).append(process)
        return index

    def _index_filesystem_paths(
        self,
        files: list[Artefact],
    ) -> dict[str, list[Artefact]]:
        """Index filesystem artefacts by normalised full path and basename."""
        index: dict[str, list[Artefact]] = {}
        for file_art in files:
            path = file_art.raw_data.get("path")
            filename = file_art.raw_data.get("filename")
            for candidate in (path, filename):
                if not candidate:
                    continue
                key = self._normalise_path_key(str(candidate))
                if not key:
                    continue
                index.setdefault(key, []).append(file_art)
                base = self._basename(key)
                if base and base != key:
                    index.setdefault(base, []).append(file_art)
        return index

    def _registry_path_candidates(self, raw_data: dict[str, Any]) -> list[str]:
        """Extract filesystem-like paths from registry value data."""
        value = raw_data.get("value_data")
        if value is None:
            return []
        text = str(value).strip()
        if not text:
            return []
        candidates: list[str] = []
        # Quoted executable paths: "C:\path\app.exe" -args
        if text.startswith('"'):
            end = text.find('"', 1)
            if end > 1:
                candidates.append(text[1:end])
        for match in _PATH_IN_VALUE_RE.findall(text):
            candidates.append(match)
        # Bare relative executable names
        if "\\" not in text and "/" not in text and text.lower().endswith(
            (".exe", ".dll", ".bat", ".cmd", ".ps1", ".vbs")
        ):
            candidates.append(text.split()[0])
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for item in candidates:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique

    def _extract_event_process_refs(
        self,
        raw_data: dict[str, Any],
    ) -> tuple[set[int], set[str]]:
        """Pull PID and process-name references from an event artefact."""
        pids: set[int] = set()
        names: set[str] = set()
        event_data = raw_data.get("event_data")
        if isinstance(event_data, dict):
            for key, value in event_data.items():
                key_l = str(key).lower()
                if key_l in {"processid", "newprocessid", "targetprocessid", "pid"}:
                    pid = self._as_int(value)
                    if pid is not None:
                        pids.add(pid)
                if key_l in {
                    "processname",
                    "newprocessname",
                    "image",
                    "subjectusername",
                } or key_l.endswith("processname"):
                    name = self._normalise_process_name(value)
                    if name and key_l != "subjectusername":
                        names.add(name)
                if key_l in {"image", "newprocessname", "processname"}:
                    # Image often includes full path — also keep basename.
                    path_name = self._basename(self._normalise_path_key(str(value)))
                    if path_name.endswith((".exe", ".dll", ".bin")):
                        names.add(path_name)

        message = raw_data.get("message")
        if isinstance(message, str):
            for match in _PID_RE.finditer(message):
                pids.add(int(match.group(1)))

        return pids, names

    @staticmethod
    def _link(links: dict[str, set[str]], left_id: str, right_id: str) -> None:
        """Create a bidirectional correlation edge (excluding self-links)."""
        if left_id == right_id:
            return
        links.setdefault(left_id, set()).add(right_id)
        links.setdefault(right_id, set()).add(left_id)

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
    def _normalise_process_name(value: Any) -> Optional[str]:
        """Lowercase basename of a process image name."""
        if value is None:
            return None
        text = str(value).strip().strip('"')
        if not text:
            return None
        text = text.replace("\\", "/").split("/")[-1]
        return text.lower() or None

    @staticmethod
    def _normalise_path_key(path: str) -> str:
        """Case-fold and slash-normalise a path for matching."""
        normalised = sanitise_path(path.strip().strip('"')).lower()
        if len(normalised) >= 2 and normalised[1] == ":":
            normalised = normalised[0].lower() + normalised[1:]
        return normalised

    @staticmethod
    def _basename(path: str) -> str:
        """Return the final path component."""
        if not path:
            return ""
        try:
            name = PureWindowsPath(path.replace("/", "\\")).name
        except Exception:  # noqa: BLE001
            name = path.rstrip("/\\").replace("\\", "/").rsplit("/", 1)[-1]
        return name.lower()
