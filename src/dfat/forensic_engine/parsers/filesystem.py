"""Filesystem metadata parser using ``DiskImageAccessor``.

Artefact ``raw_data`` schema for ``FILESYSTEM_METADATA`` (contract)::

    {
        "filename": str,
        "path": str,
        "size": int,
        "created_time": ISO-8601 str | null,
        "modified_time": ISO-8601 str | null,
        "accessed_time": ISO-8601 str | null,
        "changed_time": ISO-8601 str | null,
        "is_deleted": bool,
        "is_allocated": bool,
        "file_type": str,   # "file" | "directory" | "deleted" | "unknown"
        "inode": int,
    }
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from dfat.core.enums import ArtefactCategory, EvidenceType
from dfat.core.exceptions import DiskParsingError
from dfat.core.models.artefact import Artefact
from dfat.core.models.evidence import EvidenceImage
from dfat.forensic_engine.parsers.base import BaseParser
from dfat.forensic_engine.parsers.disk_access import DiskImageAccessor, FileEntry
from dfat.infrastructure.logging.audit_logger import ForensicAuditLogger
from dfat.shared.constants import MAX_ARTEFACTS_PER_CATEGORY


class FileSystemParser(BaseParser):
    """Walk a disk image and extract file/directory metadata artefacts.

    Uses ``DiskImageAccessor`` for read-only pytsk3 access. Each yielded
    ``FileEntry`` becomes one ``FILESYSTEM_METADATA`` artefact whose
    ``raw_data`` follows the schema documented in the module docstring.
    """

    _parse_error_class = DiskParsingError

    def __init__(
        self,
        disk_accessor: DiskImageAccessor,
        audit_logger: ForensicAuditLogger,
        max_artefacts: int = MAX_ARTEFACTS_PER_CATEGORY,
    ) -> None:
        """Initialise the filesystem metadata parser.

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
        return "FileSystemParser"

    def supported_categories(self) -> list[ArtefactCategory]:
        """Return supported artefact categories."""
        return [ArtefactCategory.FILESYSTEM_METADATA]

    def supported_evidence_types(self) -> list[EvidenceType]:
        """Return supported evidence types."""
        return [EvidenceType.DISK_IMAGE]

    def _do_parse(self, evidence: EvidenceImage) -> list[Artefact]:
        """Walk the disk image filesystem and emit metadata artefacts.

        Args:
            evidence: Disk image evidence metadata.

        Returns:
            List of ``FILESYSTEM_METADATA`` artefacts (capped by limit).
        """
        img_info = self._disk_accessor.open_image(Path(evidence.file_path))
        artefacts: list[Artefact] = []
        try:
            fs_info = self._disk_accessor.get_filesystem(img_info)
            for entry in self._disk_accessor.walk_filesystem(fs_info):
                if not self._check_limit(len(artefacts)):
                    break
                artefacts.append(self._entry_to_artefact(entry, evidence.evidence_id))
        finally:
            self._disk_accessor.close(img_info)
        return artefacts

    def _entry_to_artefact(self, entry: FileEntry, evidence_id: str) -> Artefact:
        """Map a ``FileEntry`` to a ``FILESYSTEM_METADATA`` artefact."""
        return self._create_artefact(
            category=ArtefactCategory.FILESYSTEM_METADATA,
            evidence_id=evidence_id,
            source_path=entry.path,
            raw_data={
                "filename": entry.name,
                "path": entry.path,
                "size": entry.size,
                "created_time": self._iso_or_none(entry.created_time),
                "modified_time": self._iso_or_none(entry.modified_time),
                "accessed_time": self._iso_or_none(entry.accessed_time),
                "changed_time": self._iso_or_none(entry.changed_time),
                "is_deleted": entry.is_deleted,
                "is_allocated": entry.is_allocated,
                "file_type": entry.file_type,
                "inode": entry.inode,
            },
        )

    @staticmethod
    def _iso_or_none(value: Optional[datetime]) -> Optional[str]:
        """Serialize a timestamp to ISO-8601 or return ``None``."""
        if value is None:
            return None
        return value.isoformat()
