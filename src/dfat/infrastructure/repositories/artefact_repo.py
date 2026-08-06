"""JSON file-backed artefact set repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from dfat.core.interfaces.repository import IArtefactRepository
from dfat.core.models.artefact import ArtefactSet
from dfat.infrastructure.storage.local_storage import LocalFileStorage


class JSONArtefactRepository(IArtefactRepository):
    """Persist ``ArtefactSet`` documents as one JSON file per evidence ID."""

    def __init__(self, storage: LocalFileStorage, artefacts_dir: str = "artefacts") -> None:
        """Initialise the artefact repository.

        Args:
            storage: Local storage adapter.
            artefacts_dir: Relative directory for artefact JSON files.
        """
        self._storage = storage
        self._artefacts_dir = artefacts_dir

    def save(self, entity: ArtefactSet) -> str:
        """Persist an artefact set and return its evidence ID.

        Args:
            entity: Artefact set to store.

        Returns:
            Evidence identifier used as the storage key.
        """
        relative = Path(self._artefacts_dir) / f"{entity.evidence_id}.json"
        payload = json.dumps(entity.model_dump(mode="json"), indent=2).encode("utf-8")
        self._storage.write_file(relative, payload)
        return entity.evidence_id

    def get(self, entity_id: str) -> Optional[ArtefactSet]:
        """Load an artefact set by evidence identifier.

        Args:
            entity_id: Evidence identifier.

        Returns:
            Artefact set if present; otherwise None.
        """
        relative = Path(self._artefacts_dir) / f"{entity_id}.json"
        if not self._storage.file_exists(relative):
            return None
        raw = self._storage.read_file(relative)
        return ArtefactSet.model_validate(json.loads(raw.decode("utf-8")))

    def list_all(self) -> list[ArtefactSet]:
        """List all stored artefact sets.

        Returns:
            List of artefact sets.
        """
        directory = Path(self._artefacts_dir)
        results: list[ArtefactSet] = []
        for path in self._storage.list_files(directory, "*.json"):
            raw = self._storage.read_file(path.relative_to(self._storage.base_dir))
            results.append(ArtefactSet.model_validate(json.loads(raw.decode("utf-8"))))
        return results

    def delete(self, entity_id: str) -> bool:
        """Delete an artefact set by evidence identifier.

        Args:
            entity_id: Evidence identifier.

        Returns:
            True if deleted; otherwise False.
        """
        relative = Path(self._artefacts_dir) / f"{entity_id}.json"
        if not self._storage.file_exists(relative):
            return False
        (self._storage.base_dir / relative).unlink()
        return True
