"""Scan configured directories for unregistered forensic evidence files."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import EvidenceType, PipelineStage
from dfat.core.validators import SUPPORTED_DISK_EXTENSIONS, SUPPORTED_MEMORY_EXTENSIONS
from dfat.database.repositories.evidence_repo import SQLAlchemyEvidenceRepository
from dfat.services.audit_service import AuditService
from dfat.settings import EvidenceSettings

_SUPPORTED_EXTENSIONS = frozenset(
    {ext.lower() for ext in SUPPORTED_DISK_EXTENSIONS}
    | {ext.lower() for ext in SUPPORTED_MEMORY_EXTENSIONS}
)
_DISK_EXTENSIONS = frozenset(ext.lower() for ext in SUPPORTED_DISK_EXTENSIONS)
_MEMORY_EXTENSIONS = frozenset(ext.lower() for ext in SUPPORTED_MEMORY_EXTENSIONS)


class DiscoveredEvidence(BaseModel):
    """Metadata for a forensic file found during a directory scan.

    Attributes:
        file_path: Absolute path to the discovered file.
        file_name: Base file name.
        file_size_bytes: Size of the file in bytes.
        file_extension: Lowercase file extension including the dot.
        inferred_type: Disk image or memory dump inferred from extension.
        already_registered: Whether the path is already in the evidence repo.
        discovered_at: UTC timestamp when the file was observed.
    """

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    file_path: Path
    file_name: str
    file_size_bytes: int
    file_extension: str
    inferred_type: EvidenceType
    already_registered: bool
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceDiscoveryService:
    """Discover unregistered forensic images and memory dumps on disk."""

    def __init__(
        self,
        evidence_settings: EvidenceSettings,
        evidence_repo: SQLAlchemyEvidenceRepository,
        audit_service: AuditService,
    ) -> None:
        """Initialise the discovery service.

        Args:
            evidence_settings: Evidence path and format settings.
            evidence_repo: SQLAlchemy evidence repository for registration checks.
            audit_service: Dual-write audit trail service.
        """
        self._settings = evidence_settings
        self._evidence_repo = evidence_repo
        self._audit = audit_service

    async def discover(
        self,
        scan_path: Optional[Path] = None,
    ) -> list[DiscoveredEvidence]:
        """Recursively scan for supported evidence files that are not registered.

        Symlinks are never followed. Already-registered paths are skipped.
        Files are reported only — nothing is registered.

        Args:
            scan_path: Directory to scan; defaults to ``evidence_dir``.

        Returns:
            Unregistered discovered evidence files (``already_registered=False``).
        """
        root = Path(scan_path) if scan_path is not None else Path(self._settings.evidence_dir)
        registered_paths = await self._registered_path_keys()
        found: list[DiscoveredEvidence] = []
        scanned_files = 0
        skipped_registered = 0

        if root.exists() and not root.is_symlink():
            for file_path in self._iter_files_no_follow(root):
                extension = file_path.suffix.lower()
                if extension not in _SUPPORTED_EXTENSIONS:
                    continue
                scanned_files += 1
                path_key = self._path_key(file_path)
                already = path_key in registered_paths
                if already:
                    skipped_registered += 1
                    continue
                try:
                    size = file_path.stat().st_size
                except OSError:
                    continue
                found.append(
                    DiscoveredEvidence(
                        file_path=file_path,
                        file_name=file_path.name,
                        file_size_bytes=size,
                        file_extension=extension,
                        inferred_type=self._infer_type(extension),
                        already_registered=False,
                    )
                )

        await self._audit.log_action(
            stage=PipelineStage.ACQUISITION,
            action="EVIDENCE_DISCOVERY_SCAN",
            details={
                "scan_path": str(root),
                "supported_files_seen": scanned_files,
                "unregistered_found": len(found),
                "skipped_registered": skipped_registered,
            },
        )
        return found

    async def discover_in_dataset_dir(self) -> list[DiscoveredEvidence]:
        """Scan ``data/datasets/`` for DFRWS/CFReDS benchmark evidence files.

        Resolves the datasets directory as a sibling of ``evidence_dir``
        (``…/data/datasets``) when ``evidence_dir`` ends with ``evidence``.

        Returns:
            Unregistered discovered evidence files under the datasets tree.
        """
        evidence_dir = Path(self._settings.evidence_dir)
        dataset_dir = Path(os.path.abspath(str(evidence_dir))).parent / "datasets"
        return await self.discover(dataset_dir)

    async def _registered_path_keys(self) -> set[str]:
        """Return normalised absolute path keys for registered evidence."""
        records = await self._evidence_repo.list_all()
        return {self._path_key(record.file_path) for record in records}

    @staticmethod
    def _path_key(path: Path) -> str:
        """Normalise a path for registration comparison without resolving symlinks."""
        return os.path.normcase(os.path.abspath(str(path)))

    @staticmethod
    def _infer_type(extension: str) -> EvidenceType:
        """Infer evidence type from extension (disk preferred for shared ``.raw``)."""
        if extension in _DISK_EXTENSIONS:
            return EvidenceType.DISK_IMAGE
        if extension in _MEMORY_EXTENSIONS:
            return EvidenceType.MEMORY_DUMP
        return EvidenceType.DISK_IMAGE

    @staticmethod
    def _iter_files_no_follow(root: Path) -> list[Path]:
        """Yield files under ``root`` without following directory or file symlinks."""
        results: list[Path] = []
        stack: list[Path] = [root]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        # Never follow symlinks (files or directories).
                        if entry.is_symlink():
                            continue
                        entry_path = Path(entry.path)
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry_path)
                        elif entry.is_file(follow_symlinks=False):
                            results.append(entry_path)
            except OSError:
                continue
        return results
