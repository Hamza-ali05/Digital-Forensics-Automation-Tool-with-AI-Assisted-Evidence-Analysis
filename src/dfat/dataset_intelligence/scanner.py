"""Recursive dataset scanner for dataset intelligence discovery."""

from __future__ import annotations

import asyncio
import os
import tarfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from dfat.core.enums import HashAlgorithm, PipelineStage
from dfat.dataset_intelligence.config import DatasetIntelligenceSettings
from dfat.dataset_intelligence.enums import (
    DatasetCategory,
    DatasetFormat,
    DatasetStatus,
)
from dfat.dataset_intelligence.models import (
    DatasetRecord,
    DatasetScanResult,
)
from dfat.evidence_management.mime_identifier import MIMEIdentifier
from dfat.shared.hashing import compute_file_hash

if TYPE_CHECKING:
    from dfat.services.audit_service import AuditService


class DatasetScanner:
    """Discover datasets recursively without mutating existing DFAT flows."""

    def __init__(
        self,
        settings: DatasetIntelligenceSettings,
        audit_service: AuditService,
        mime_identifier: MIMEIdentifier,
    ) -> None:
        self._settings = settings
        self._audit_service = audit_service
        self._mime_identifier = mime_identifier

    async def scan(self, scan_path: Optional[Path] = None) -> DatasetScanResult:
        """Recursively scan a dataset directory and return discovered records."""
        base_path = Path(scan_path or self._settings.datasets_dir)
        started = asyncio.get_running_loop().time()
        datasets: list[DatasetRecord] = []
        failed_count = 0

        if not base_path.exists() or not base_path.is_dir():
            result = DatasetScanResult(
                scan_path=base_path,
                discovered_count=0,
                new_count=0,
                updated_count=0,
                failed_count=0,
                duration_seconds=0.0,
                datasets=[],
            )
            await self._audit_service.log_action(
                stage=PipelineStage.EVALUATION,
                action="DATASET_SCAN_COMPLETED",
                evidence_id="dataset_scan",
                details={
                    "scan_path": str(base_path),
                    "discovered_count": 0,
                    "new_count": 0,
                    "updated_count": 0,
                    "failed_count": 0,
                },
            )
            return result

        for root, dirs, files in os.walk(base_path, topdown=True, followlinks=False):
            dirs[:] = [
                name
                for name in dirs
                if not self._is_hidden_name(name)
                and name not in {"__pycache__", ".git", "node_modules"}
            ]
            for file_name in files:
                if self._is_hidden_name(file_name):
                    continue
                file_path = Path(root) / file_name
                if self._should_skip(file_path):
                    continue
                try:
                    datasets.append(await self._scan_path(file_path, base_path))
                except Exception:  # noqa: BLE001
                    failed_count += 1

        duration_seconds = asyncio.get_running_loop().time() - started
        result = DatasetScanResult(
            scan_path=base_path,
            discovered_count=len(datasets),
            new_count=len(datasets),
            updated_count=0,
            failed_count=failed_count,
            duration_seconds=round(duration_seconds, 4),
            datasets=datasets,
        )
        await self._audit_service.log_action(
            stage=PipelineStage.EVALUATION,
            action="DATASET_SCAN_COMPLETED",
            evidence_id="dataset_scan",
            details={
                "scan_path": str(base_path),
                "discovered_count": result.discovered_count,
                "new_count": result.new_count,
                "updated_count": result.updated_count,
                "failed_count": result.failed_count,
                "duration_seconds": result.duration_seconds,
            },
        )
        return result

    async def scan_single(self, file_path: Path) -> DatasetRecord:
        """Scan and register a single file path."""
        path = Path(file_path)
        base_path = self._settings.datasets_dir if path.is_relative_to(self._settings.datasets_dir) else path.parent
        return await self._scan_path(path, base_path)

    async def _scan_path(self, file_path: Path, base_path: Path) -> DatasetRecord:
        stat = await asyncio.to_thread(file_path.stat)
        hash_sha256 = await asyncio.to_thread(
            compute_file_hash,
            file_path,
            HashAlgorithm.SHA256,
        )
        detected_format = self._detect_format(file_path)
        mime_type, detection_method = self._mime_identifier.identify(file_path)
        is_nested, nested_depth = self._compute_nesting_info(file_path, base_path)
        metadata = {
            "mime_detection_method": detection_method,
            "suffixes": file_path.suffixes,
        }
        archive_contents = await asyncio.to_thread(self._list_archive_contents, file_path)
        if archive_contents is not None:
            metadata["archive_contents"] = archive_contents

        return DatasetRecord(
            name=file_path.name,
            file_path=file_path,
            category=DatasetCategory.USER_UPLOADED,
            format=detected_format,
            status=DatasetStatus.DISCOVERED,
            file_size_bytes=stat.st_size,
            hash_sha256=hash_sha256,
            mime_type=mime_type,
            parent_directory=str(file_path.parent),
            is_nested=is_nested,
            nested_depth=nested_depth,
            metadata=metadata,
        )

    def _detect_format(self, file_path: Path) -> DatasetFormat:
        """Detect dataset format from extension and MIME hints."""
        suffixes = [suffix.lower() for suffix in file_path.suffixes]
        suffix = file_path.suffix.lower()
        mime_type, _ = self._mime_identifier.identify(file_path)

        if suffix in {".dd", ".e01", ".img", ".001"}:
            return DatasetFormat.DISK_IMAGE
        if suffix in {".raw", ".vmem", ".dmp", ".mem"}:
            return DatasetFormat.MEMORY_DUMP
        if suffix == ".pcap":
            return DatasetFormat.PCAP
        if suffix == ".evtx":
            return DatasetFormat.EVTX
        if suffix in {".hiv", ".dat"}:
            return DatasetFormat.REGISTRY_HIVE
        if suffix in {".db", ".sqlite", ".sqlite3"}:
            return DatasetFormat.SQLITE_DB
        if suffix == ".csv":
            return DatasetFormat.CSV
        if suffix == ".json":
            return DatasetFormat.JSON
        if suffix == ".xml":
            return DatasetFormat.XML
        if suffix in {".yar", ".yara"}:
            return DatasetFormat.YARA_RULES
        if suffix in {".sigma", ".yml", ".yaml"}:
            return DatasetFormat.SIGMA_RULES
        if suffix == ".stix":
            return DatasetFormat.STIX_BUNDLE
        if suffix in {".txt", ".log", ".md"}:
            return DatasetFormat.PLAIN_TEXT
        if suffix in {".zip", ".gz", ".tar"} or suffixes[-2:] == [".tar", ".gz"]:
            return DatasetFormat.ARCHIVE

        if mime_type in {"application/json", "text/json"}:
            return DatasetFormat.JSON
        if mime_type in {"application/xml", "text/xml"}:
            return DatasetFormat.XML
        if mime_type.startswith("text/"):
            return DatasetFormat.PLAIN_TEXT
        if mime_type == "application/zip":
            return DatasetFormat.ARCHIVE
        if mime_type == "application/vnd.tcpdump.pcap":
            return DatasetFormat.PCAP

        return DatasetFormat.BINARY if mime_type == "application/octet-stream" else DatasetFormat.UNKNOWN

    def _compute_nesting_info(self, file_path: Path, base_path: Path) -> tuple[bool, int]:
        """Return whether a file is nested and by how many directory levels."""
        relative_parent = file_path.parent.relative_to(base_path)
        parent_parts = [part for part in relative_parent.parts if part not in {"."}]
        depth = len(parent_parts)
        return depth > 0, depth

    def _should_skip(self, file_path: Path) -> bool:
        """Return whether a candidate file should be excluded from scanning."""
        if file_path.is_symlink():
            return True
        parts = {part.lower() for part in file_path.parts}
        if "__pycache__" in parts or ".git" in parts or "node_modules" in parts:
            return True
        if any(self._is_hidden_name(part) for part in file_path.parts):
            return True
        try:
            max_size_bytes = self._settings.max_dataset_size_gb * 1024 * 1024 * 1024
            return file_path.stat().st_size > max_size_bytes
        except OSError:
            return True

    @staticmethod
    def _is_hidden_name(name: str) -> bool:
        return name.startswith(".")

    @staticmethod
    def _list_archive_contents(file_path: Path) -> list[str] | None:
        """List archive members without extracting the archive."""
        suffix = file_path.suffix.lower()
        suffixes = [part.lower() for part in file_path.suffixes]
        try:
            if suffix == ".zip":
                with zipfile.ZipFile(file_path) as archive:
                    return archive.namelist()
            if suffix == ".tar" or suffixes[-2:] == [".tar", ".gz"] or suffix == ".gz":
                with tarfile.open(file_path, "r:*") as archive:
                    return archive.getnames()
        except (tarfile.TarError, zipfile.BadZipFile, OSError):
            return ["<unreadable archive contents>"]
        return None
