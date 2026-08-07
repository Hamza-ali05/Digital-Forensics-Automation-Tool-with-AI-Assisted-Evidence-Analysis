"""Evidence metadata extraction and consistency comparison."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from dfat.core.exceptions import EvidenceNotFoundError
from dfat.core.validators import SUPPORTED_DISK_EXTENSIONS, SUPPORTED_MEMORY_EXTENSIONS
from dfat.database.repositories.evidence_status_repo import EvidenceMetadataRepository
from dfat.evidence_management.hash_service import MultiHashService
from dfat.evidence_management.mime_identifier import MIMEIdentifier
from dfat.evidence_management.models import EvidenceMetadataRecord, HashSet


class EvidenceMetadataService:
    """Extract, load, and compare forensic evidence metadata records."""

    def __init__(
        self,
        metadata_repo: EvidenceMetadataRepository,
        hash_service: MultiHashService,
        mime_identifier: MIMEIdentifier,
    ) -> None:
        """Initialise the metadata service.

        Args:
            metadata_repo: Metadata persistence repository.
            hash_service: Multi-algorithm hash service.
            mime_identifier: MIME detection helper.
        """
        self._metadata_repo = metadata_repo
        self._hash_service = hash_service
        self._mime = mime_identifier

    def extract_metadata(
        self,
        evidence_id: str,
        file_path: Path | str,
    ) -> EvidenceMetadataRecord:
        """Extract MIME, hashes, timestamps, and format notes from a file.

        Args:
            evidence_id: Evidence identifier.
            file_path: Path to the evidence file (read-only).

        Returns:
            Fresh ``EvidenceMetadataRecord`` (not automatically persisted).
        """
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise EvidenceNotFoundError(
                f"Evidence file not found: {path}",
                context={"evidence_id": evidence_id, "path": str(path)},
            )

        mime_type, detection_method = self._mime.identify(path)
        extension = path.suffix.lower()
        file_size = path.stat().st_size
        hash_set = self._hash_service.compute_hash_set(path, evidence_id)
        created_at, modified_at, accessed_at = self._extract_timestamps(path)

        notes: list[str] = [
            f"MIME detected via {detection_method}: {mime_type}",
        ]
        is_valid = extension in (SUPPORTED_DISK_EXTENSIONS | SUPPORTED_MEMORY_EXTENSIONS)
        if not is_valid:
            notes.append(f"Extension {extension!r} is not in supported forensic formats")

        return EvidenceMetadataRecord(
            evidence_id=evidence_id,
            mime_type=mime_type,
            mime_detected_from=detection_method,
            file_extension=extension,
            file_size_bytes=file_size,
            file_created_at=created_at,
            file_modified_at=modified_at,
            file_accessed_at=accessed_at,
            hash_set=hash_set,
            is_valid_format=is_valid,
            validation_notes=notes,
            extracted_at=datetime.now(UTC),
        )

    async def get_metadata(
        self,
        evidence_id: str,
    ) -> Optional[EvidenceMetadataRecord]:
        """Load persisted metadata for an evidence item."""
        return await self._metadata_repo.get_metadata(evidence_id)

    async def compare_metadata(
        self,
        evidence_id: str,
        file_path: Path | str,
    ) -> dict[str, Any]:
        """Compare stored metadata against a fresh extraction from disk.

        Args:
            evidence_id: Evidence identifier.
            file_path: Path to the evidence file (read-only).

        Returns:
            Dict with ``matches``, ``discrepancies``, and ``is_consistent``.
        """
        stored = await self._metadata_repo.get_metadata(evidence_id)
        current = self.extract_metadata(evidence_id, file_path)

        if stored is None:
            return {
                "matches": {},
                "discrepancies": {
                    "stored_metadata": "No stored metadata found for comparison"
                },
                "is_consistent": False,
                "current": current.model_dump(mode="json"),
                "stored": None,
            }

        matches: dict[str, Any] = {}
        discrepancies: dict[str, Any] = {}

        def _compare(field: str, expected: Any, actual: Any) -> None:
            if expected == actual:
                matches[field] = expected
            else:
                discrepancies[field] = {"expected": expected, "actual": actual}

        _compare("mime_type", stored.mime_type, current.mime_type)
        _compare("file_extension", stored.file_extension, current.file_extension)
        _compare("file_size_bytes", stored.file_size_bytes, current.file_size_bytes)
        _compare("hash_md5", stored.hash_set.md5.lower(), current.hash_set.md5.lower())
        _compare("hash_sha1", stored.hash_set.sha1.lower(), current.hash_set.sha1.lower())
        _compare(
            "hash_sha256",
            stored.hash_set.sha256.lower(),
            current.hash_set.sha256.lower(),
        )

        return {
            "matches": matches,
            "discrepancies": discrepancies,
            "is_consistent": len(discrepancies) == 0,
            "current": current.model_dump(mode="json"),
            "stored": stored.model_dump(mode="json"),
        }

    @staticmethod
    def _extract_timestamps(
        path: Path,
    ) -> tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
        """Extract created/modified/accessed timestamps from ``os.stat``."""
        try:
            stat_result = os.stat(path)
        except OSError:
            return None, None, None

        def _from_ts(value: float) -> Optional[datetime]:
            try:
                return datetime.fromtimestamp(value, tz=UTC)
            except (OverflowError, OSError, ValueError):
                return None

        created = _from_ts(getattr(stat_result, "st_birthtime", stat_result.st_ctime))
        modified = _from_ts(stat_result.st_mtime)
        accessed = _from_ts(stat_result.st_atime)
        return created, modified, accessed
