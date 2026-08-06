"""Filesystem-backed evidence metadata repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from dfat.core.interfaces.repository import IEvidenceRepository
from dfat.core.models.evidence import EvidenceImage
from dfat.infrastructure.storage.local_storage import LocalFileStorage


class FileSystemEvidenceRepository(IEvidenceRepository):
    """Persist ``EvidenceImage`` metadata as JSON via ``LocalFileStorage``."""

    def __init__(self, storage: LocalFileStorage, metadata_dir: str = "metadata") -> None:
        """Initialise the evidence repository.

        Args:
            storage: Local storage adapter constrained to a base directory.
            metadata_dir: Relative directory for metadata JSON files.
        """
        self._storage = storage
        self._metadata_dir = metadata_dir

    def save(self, entity: EvidenceImage) -> str:
        """Serialise evidence metadata to JSON and return its ID.

        Args:
            entity: Evidence metadata to persist.

        Returns:
            Persisted evidence identifier.
        """
        relative = Path(self._metadata_dir) / f"{entity.evidence_id}.json"
        payload = json.dumps(entity.model_dump(mode="json"), indent=2).encode("utf-8")
        self._storage.write_file(relative, payload)
        return entity.evidence_id

    def get(self, entity_id: str) -> Optional[EvidenceImage]:
        """Load evidence metadata by identifier.

        Args:
            entity_id: Evidence identifier.

        Returns:
            Evidence metadata if present; otherwise None.
        """
        relative = Path(self._metadata_dir) / f"{entity_id}.json"
        if not self._storage.file_exists(relative):
            return None
        raw = self._storage.read_file(relative)
        data = json.loads(raw.decode("utf-8"))
        return EvidenceImage.model_validate(data)

    def list_all(self) -> list[EvidenceImage]:
        """List all stored evidence metadata records.

        Returns:
            List of evidence metadata models.
        """
        directory = Path(self._metadata_dir)
        results: list[EvidenceImage] = []
        for path in self._storage.list_files(directory, "*.json"):
            raw = self._storage.read_file(path.relative_to(self._storage.base_dir))
            results.append(EvidenceImage.model_validate(json.loads(raw.decode("utf-8"))))
        return results

    def delete(self, entity_id: str) -> bool:
        """Delete evidence metadata by identifier.

        Args:
            entity_id: Evidence identifier.

        Returns:
            True if a record was deleted; otherwise False.
        """
        relative = Path(self._metadata_dir) / f"{entity_id}.json"
        if not self._storage.file_exists(relative):
            return False
        resolved = self._storage.base_dir / relative
        resolved.unlink()
        return True
