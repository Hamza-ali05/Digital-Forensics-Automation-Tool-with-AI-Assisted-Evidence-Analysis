"""Filesystem-backed registry of trained ML model versions."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

from dfat.ml.trainer import TrainedModel

_INDEX_NAME = "index.json"
_METADATA_NAME = "metadata.json"


class ModelRegistry:
    """Persist ``TrainedModel`` metadata and load joblib-serialized estimators."""

    def __init__(self, models_dir: Path) -> None:
        self._models_dir = Path(models_dir)
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def register(self, model: TrainedModel) -> str:
        """Register a trained model version and return its ``model_id``."""
        with self._lock:
            if not model.version:
                model.version = self._next_version(model.model_name)
            catalog = self._load_index()
            catalog = [item for item in catalog if item.model_id != model.model_id]
            catalog.append(model)
            self._write_index(catalog)
            self._write_metadata(model)
        return model.model_id

    def get_latest(self, model_name: str) -> Optional[TrainedModel]:
        """Return the newest registered version of ``model_name``."""
        versions = [item for item in self.list_models() if item.model_name == model_name]
        if not versions:
            return None
        versions.sort(key=_version_sort_key, reverse=True)
        return versions[0]

    def get_version(self, model_name: str, version: str) -> Optional[TrainedModel]:
        """Return a specific registered version, if present."""
        for item in self.list_models():
            if item.model_name == model_name and item.version == version:
                return item
        return None

    def list_models(self) -> list[TrainedModel]:
        """Return all registered model versions."""
        with self._lock:
            return self._load_index()

    def load_model(self, model_id: str) -> Any:
        """Load the serialized sklearn estimator for ``model_id`` via joblib."""
        record = self._get_by_id(model_id)
        if record is None:
            raise KeyError(f"Model not found: {model_id}")
        path = Path(record.model_path)
        if not path.exists():
            raise FileNotFoundError(f"Serialized model missing: {path}")
        from joblib import load

        return load(path)

    def compare_versions(self, model_name: str) -> list[dict[str, Any]]:
        """Return metrics comparison rows across versions of ``model_name``."""
        rows: list[dict[str, Any]] = []
        for item in self.list_models():
            if item.model_name != model_name:
                continue
            rows.append(
                {
                    "model_id": item.model_id,
                    "model_name": item.model_name,
                    "version": item.version,
                    "metrics": dict(item.metrics),
                    "trained_at": item.trained_at.isoformat(),
                    "training_dataset": item.training_dataset,
                    "hyperparameters": dict(item.hyperparameters),
                }
            )
        rows.sort(key=lambda row: _version_sort_key_raw(str(row["version"])))
        return rows

    def _get_by_id(self, model_id: str) -> Optional[TrainedModel]:
        for item in self.list_models():
            if item.model_id == model_id:
                return item
        return None

    def _index_path(self) -> Path:
        return self._models_dir / _INDEX_NAME

    def _load_index(self) -> list[TrainedModel]:
        path = self._index_path()
        if not path.exists():
            return self._discover_from_disk()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        records: list[TrainedModel] = []
        if isinstance(payload, list):
            for item in payload:
                try:
                    records.append(TrainedModel.model_validate(item))
                except (TypeError, ValueError):
                    continue
        return records

    def _write_index(self, models: list[TrainedModel]) -> None:
        payload = [item.model_dump(mode="json") for item in models]
        self._index_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_metadata(self, model: TrainedModel) -> None:
        directory = Path(model.model_path).parent
        directory.mkdir(parents=True, exist_ok=True)
        (directory / _METADATA_NAME).write_text(
            json.dumps(model.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

    def _next_version(self, model_name: str) -> str:
        versions = [
            _parse_version(item.version)
            for item in self._load_index()
            if item.model_name == model_name
        ]
        numeric = [value for value in versions if value is not None]
        return str(max(numeric, default=0) + 1)

    def _discover_from_disk(self) -> list[TrainedModel]:
        records: list[TrainedModel] = []
        for metadata in self._models_dir.glob(f"*/*/{_METADATA_NAME}"):
            try:
                records.append(TrainedModel.model_validate_json(metadata.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return records


def _parse_version(version: str) -> Optional[int]:
    if version.isdigit():
        return int(version)
    return None


def _version_sort_key(model: TrainedModel) -> tuple[int, str]:
    return _version_sort_key_raw(model.version)


def _version_sort_key_raw(version: str) -> tuple[int, str]:
    parsed = _parse_version(version)
    if parsed is None:
        return (-1, version)
    return (parsed, version)
