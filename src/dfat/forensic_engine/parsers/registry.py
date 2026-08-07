"""Windows registry hive parser using ``python-registry``.

Artefact ``raw_data`` schema for ``REGISTRY_KEY`` (contract)::

    {
        "hive_name": str,
        "key_path": str,
        "value_name": str,
        "value_data": str,
        "value_type": str,
        "last_modified": ISO-8601 str | null,
    }

Known hive locations are listed in ``REGISTRY_HIVE_PATHS``.
"""

from __future__ import annotations

import fnmatch
import tempfile
from pathlib import Path
from typing import Any, Optional

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import DiskParsingError
from dfat.core.models.artefact import Artefact
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.disk_access import DiskImageAccessor, FileEntry
from dfat.forensic_engine.parsers.utils import (
    convert_timestamp,
    sanitise_path,
    truncate_data,
)
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.constants import MAX_ARTEFACTS_PER_CATEGORY

REGISTRY_HIVE_PATHS: list[str] = [
    "Windows/System32/config/SAM",
    "Windows/System32/config/SYSTEM",
    "Windows/System32/config/SOFTWARE",
    "Windows/System32/config/SECURITY",
    "Users/*/NTUSER.DAT",
]


class RegistryParser(BaseParser):
    """Extract registry key/value artefacts from disk images.

    Locates known hive paths via ``DiskImageAccessor``, extracts each hive to
    a temporary file, parses it with ``python-registry``, and emits
    ``REGISTRY_KEY`` artefacts. Missing or corrupt hives are skipped.
    """

    _parse_error_class = DiskParsingError

    def __init__(
        self,
        disk_accessor: DiskImageAccessor,
        audit_logger: ForensicAuditLogger,
        max_artefacts: int = MAX_ARTEFACTS_PER_CATEGORY,
    ) -> None:
        """Initialise the registry hive parser.

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
        return "RegistryParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return supported artefact categories."""
        return [ArtefactCategory.REGISTRY_KEY]

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return supported evidence types."""
        return [EvidenceType.DISK_IMAGE]

    def _do_parse(self, evidence: EvidenceImage) -> list[Artefact]:
        """Locate registry hives, extract to temp, and walk key/value trees."""
        registry_mod = self._safe_import(
            "Registry.Registry",
            "python-registry is required for registry parsing. Install with: "
            "pip install python-registry",
        )
        registry_cls = registry_mod.Registry
        key_not_found = getattr(
            registry_mod,
            "RegistryKeyNotFoundException",
            Exception,
        )

        img_info = self._disk_accessor.open_image(Path(evidence.file_path))
        artefacts: list[Artefact] = []
        temp_files: list[Path] = []
        temp_dir = Path(tempfile.mkdtemp(prefix="dfat_reg_"))
        try:
            fs_info = self._disk_accessor.get_filesystem(img_info)
            hive_entries = self._locate_hives(fs_info)
            for entry in hive_entries:
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
                artefacts.extend(
                    self._parse_hive_file(
                        temp_path,
                        entry,
                        evidence.evidence_id,
                        registry_cls,
                        key_not_found,
                        remaining=self._max_artefacts - len(artefacts),
                    )
                )
        finally:
            self._disk_accessor.close(img_info)
            self._cleanup_temps(temp_files, temp_dir)
        return artefacts

    def _locate_hives(self, fs_info: Any) -> list[FileEntry]:
        """Walk the filesystem and return entries matching known hive paths."""
        matches: list[FileEntry] = []
        seen_inodes: set[int] = set()
        for entry in self._disk_accessor.walk_filesystem(fs_info):
            if entry.file_type in {"directory", "unknown"}:
                continue
            if entry.inode and entry.inode in seen_inodes:
                continue
            if not self._path_matches_hive(entry.path):
                continue
            if entry.inode:
                seen_inodes.add(entry.inode)
            matches.append(entry)
        return matches

    @staticmethod
    def _path_matches_hive(path: str) -> bool:
        """Return whether ``path`` matches a known registry hive location."""
        normalised = sanitise_path(path).lstrip("/").lower()
        for pattern in REGISTRY_HIVE_PATHS:
            candidate = pattern.replace("\\", "/").lower()
            if fnmatch.fnmatch(normalised, candidate):
                return True
            # Also allow absolute-style and case-insensitive suffix matches.
            if fnmatch.fnmatch("/" + normalised, "/" + candidate):
                return True
            if "*" not in candidate and normalised.endswith(candidate):
                return True
        return False

    def _parse_hive_file(
        self,
        temp_path: Path,
        entry: FileEntry,
        evidence_id: str,
        registry_cls: Any,
        key_not_found: type[BaseException],
        remaining: int,
    ) -> list[Artefact]:
        """Parse an extracted hive file into artefacts."""
        artefacts: list[Artefact] = []
        hive_name = self._hive_name_from_path(entry.path)
        try:
            registry = registry_cls(str(temp_path))
            root = registry.root()
        except key_not_found:
            return artefacts
        except Exception:  # noqa: BLE001 — corrupt / unsupported hive
            return artefacts

        try:
            self._walk_key(
                root,
                root.path(),
                hive_name,
                entry.path,
                evidence_id,
                artefacts,
                remaining,
                key_not_found,
            )
        except key_not_found:
            return artefacts
        except Exception:  # noqa: BLE001
            return artefacts
        return artefacts

    def _walk_key(
        self,
        key: Any,
        key_path: str,
        hive_name: str,
        hive_path: str,
        evidence_id: str,
        artefacts: list[Artefact],
        remaining: int,
        key_not_found: type[BaseException],
    ) -> None:
        """Recursively walk registry keys collecting values."""
        if len(artefacts) >= remaining:
            return
        try:
            values = key.values()
        except key_not_found:
            values = []
        except Exception:  # noqa: BLE001
            values = []

        last_modified = self._format_timestamp(getattr(key, "timestamp", lambda: None)())
        for value in values:
            if len(artefacts) >= remaining:
                return
            try:
                artefacts.append(
                    self._create_artefact(
                        category=ArtefactCategory.REGISTRY_KEY,
                        evidence_id=evidence_id,
                        source_path=hive_path,
                        raw_data={
                            "hive_name": hive_name,
                            "key_path": key_path,
                            "value_name": str(value.name()),
                            "value_data": truncate_data(str(value.value())),
                            "value_type": str(value.value_type()),
                            "last_modified": last_modified,
                        },
                    )
                )
            except Exception:  # noqa: BLE001
                continue

        try:
            subkeys = key.subkeys()
        except key_not_found:
            return
        except Exception:  # noqa: BLE001
            return

        for subkey in subkeys:
            if len(artefacts) >= remaining:
                return
            try:
                self._walk_key(
                    subkey,
                    subkey.path(),
                    hive_name,
                    hive_path,
                    evidence_id,
                    artefacts,
                    remaining,
                    key_not_found,
                )
            except key_not_found:
                continue
            except Exception:  # noqa: BLE001
                continue

    @staticmethod
    def _hive_name_from_path(path: str) -> str:
        """Derive a short hive name from a filesystem path."""
        name = Path(sanitise_path(path)).name
        return name.upper() if name.upper() != "NTUSER.DAT" else "NTUSER.DAT"

    @staticmethod
    def _format_timestamp(value: Any) -> Optional[str]:
        """Convert a registry timestamp to ISO-8601 when possible."""
        converted = convert_timestamp(value)
        if converted is not None:
            return converted.isoformat()
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _cleanup_temps(temp_files: list[Path], temp_dir: Path) -> None:
        """Remove extracted hive files and the temporary directory."""
        for path in temp_files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
        try:
            temp_dir.rmdir()
        except OSError:
            # Directory may still contain unexpected files; best-effort wipe.
            try:
                for child in temp_dir.iterdir():
                    child.unlink(missing_ok=True)
                temp_dir.rmdir()
            except OSError:
                pass
