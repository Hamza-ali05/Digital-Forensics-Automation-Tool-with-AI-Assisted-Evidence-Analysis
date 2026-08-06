"""Filesystem-backed forensic report repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from dfat.core.interfaces.repository import IReportRepository
from dfat.core.models.report import ForensicReport
from dfat.infrastructure.storage.local_storage import LocalFileStorage


class FileSystemReportRepository(IReportRepository):
    """Persist ``ForensicReport`` documents as JSON files."""

    def __init__(self, storage: LocalFileStorage, reports_dir: str = "reports") -> None:
        """Initialise the report repository.

        Args:
            storage: Local storage adapter.
            reports_dir: Relative directory for report JSON files.
        """
        self._storage = storage
        self._reports_dir = reports_dir

    def save(self, entity: ForensicReport) -> str:
        """Persist a forensic report and return its report ID.

        Args:
            entity: Forensic report to store.

        Returns:
            Persisted report identifier.
        """
        relative = Path(self._reports_dir) / f"{entity.report_id}.json"
        payload = json.dumps(entity.model_dump(mode="json"), indent=2).encode("utf-8")
        self._storage.write_file(relative, payload)
        return entity.report_id

    def get(self, entity_id: str) -> Optional[ForensicReport]:
        """Load a forensic report by identifier.

        Args:
            entity_id: Report identifier.

        Returns:
            Forensic report if present; otherwise None.
        """
        relative = Path(self._reports_dir) / f"{entity_id}.json"
        if not self._storage.file_exists(relative):
            return None
        raw = self._storage.read_file(relative)
        return ForensicReport.model_validate(json.loads(raw.decode("utf-8")))

    def list_all(self) -> list[ForensicReport]:
        """List all stored forensic reports.

        Returns:
            List of forensic reports.
        """
        directory = Path(self._reports_dir)
        results: list[ForensicReport] = []
        for path in self._storage.list_files(directory, "*.json"):
            raw = self._storage.read_file(path.relative_to(self._storage.base_dir))
            results.append(ForensicReport.model_validate(json.loads(raw.decode("utf-8"))))
        return results

    def delete(self, entity_id: str) -> bool:
        """Delete a forensic report by identifier.

        Args:
            entity_id: Report identifier.

        Returns:
            True if deleted; otherwise False.
        """
        relative = Path(self._reports_dir) / f"{entity_id}.json"
        if not self._storage.file_exists(relative):
            return False
        (self._storage.base_dir / relative).unlink()
        return True
