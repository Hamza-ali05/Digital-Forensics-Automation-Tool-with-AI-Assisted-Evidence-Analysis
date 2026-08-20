"""Dataset validation routines for integrity and format sanity checks."""

from __future__ import annotations

import asyncio
import csv
import json
import tarfile
import zipfile
from pathlib import Path

import yaml

from dfat.dataset_intelligence.enums import DatasetFormat, DatasetStatus
from dfat.dataset_intelligence.models import DatasetRecord

try:
    import yara  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    yara = None


class DatasetValidator:
    """Validate discovered datasets before indexing or preprocessing."""

    async def validate(self, dataset: DatasetRecord) -> DatasetRecord:
        """Validate a dataset according to its detected format."""
        notes: list[str] = []

        try:
            await self._validate_by_format(dataset, notes)
        except Exception as exc:  # noqa: BLE001
            dataset.status = DatasetStatus.FAILED
            dataset.metadata = {
                **dataset.metadata,
                "validation_notes": [*notes, str(exc)],
                "validation_passed": False,
            }
            return dataset

        dataset.status = DatasetStatus.VALIDATED
        dataset.metadata = {
            **dataset.metadata,
            "validation_notes": notes or ["Validation succeeded."],
            "validation_passed": True,
        }
        return dataset

    async def _validate_by_format(
        self,
        dataset: DatasetRecord,
        notes: list[str],
    ) -> None:
        path = Path(dataset.file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Dataset file not found: {path}")

        if dataset.format in {DatasetFormat.DISK_IMAGE, DatasetFormat.MEMORY_DUMP}:
            stat = await asyncio.to_thread(path.stat)
            if stat.st_size <= 0:
                raise ValueError("Forensic image/dump is empty.")
            await asyncio.to_thread(self._ensure_readable, path)
            notes.append("Readable forensic image or memory dump.")
            return

        if dataset.format is DatasetFormat.CSV:
            row_count = await asyncio.to_thread(self._validate_csv, path)
            notes.append(f"CSV parsed successfully with {row_count} data rows.")
            return

        if dataset.format is DatasetFormat.JSON:
            object_count = await asyncio.to_thread(self._validate_json, path)
            notes.append(f"JSON parsed successfully with {object_count} top-level entries.")
            return

        if dataset.format is DatasetFormat.YARA_RULES:
            yara_status = await asyncio.to_thread(self._validate_yara, path)
            notes.append(yara_status)
            return

        if dataset.format is DatasetFormat.SIGMA_RULES:
            sigma_keys = await asyncio.to_thread(self._validate_sigma, path)
            notes.append(f"Sigma/YAML parsed successfully with {sigma_keys} top-level keys.")
            return

        if dataset.format is DatasetFormat.STIX_BUNDLE:
            stix_count = await asyncio.to_thread(self._validate_stix_bundle, path)
            notes.append(f"STIX bundle validated with {stix_count} objects.")
            return

        if dataset.format is DatasetFormat.ARCHIVE:
            members = await asyncio.to_thread(self._validate_archive, path)
            notes.append(f"Archive contents listed successfully with {members} members.")
            return

        await asyncio.to_thread(self._ensure_readable, path)
        notes.append("Generic readability validation succeeded.")

    @staticmethod
    def _ensure_readable(path: Path) -> None:
        with path.open("rb") as handle:
            handle.read(1)

    @staticmethod
    def _validate_csv(path: Path) -> int:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            rows = list(reader)
        if not rows:
            raise ValueError("CSV file is empty.")
        header = rows[0]
        if not header:
            raise ValueError("CSV header is empty.")
        return max(len(rows) - 1, 0)

    @staticmethod
    def _validate_json(path: Path) -> int:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload in ({}, [], None, ""):
            raise ValueError("JSON payload is empty.")
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            return len(payload)
        return 1

    @staticmethod
    def _validate_yara(path: Path) -> str:
        if yara is None:
            # Fallback still confirms the file is non-empty/readable in local-only mode.
            with path.open("r", encoding="utf-8") as handle:
                content = handle.read().strip()
            if not content:
                raise ValueError("YARA file is empty.")
            return "YARA syntax not compiled because yara-python is unavailable."

        yara.compile(filepath=str(path))
        return "YARA syntax compiled successfully."

    @staticmethod
    def _validate_sigma(path: Path) -> int:
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
        if payload in ({}, [], None, ""):
            raise ValueError("Sigma YAML payload is empty.")
        if isinstance(payload, dict):
            return len(payload)
        if isinstance(payload, list):
            return len(payload)
        return 1

    @staticmethod
    def _validate_stix_bundle(path: Path) -> int:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("STIX payload must be a JSON object.")
        objects = payload.get("objects")
        if payload.get("type") != "bundle" or not isinstance(objects, list) or not objects:
            raise ValueError("STIX bundle must contain a non-empty objects list.")
        invalid_objects = [obj for obj in objects if not isinstance(obj, dict) or "type" not in obj]
        if invalid_objects:
            raise ValueError("STIX bundle contains invalid STIX objects.")
        return len(objects)

    @staticmethod
    def _validate_archive(path: Path) -> int:
        suffixes = [suffix.lower() for suffix in path.suffixes]
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                return len(archive.namelist())
        with tarfile.open(path, "r:*") as archive:
            return len(archive.getnames())
