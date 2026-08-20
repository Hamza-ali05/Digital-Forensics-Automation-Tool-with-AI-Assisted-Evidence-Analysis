"""Lightweight JSON-file experiment tracker for local ML runs."""

from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class ExperimentNotFoundError(KeyError):
    """Raised when an experiment JSON record cannot be located."""


class ExperimentRecord(BaseModel):
    """Persisted metadata for a single ML experiment run."""

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    experiment_id: str = Field(default_factory=lambda: str(uuid4()))
    model_name: str
    dataset_name: str
    hyperparameters: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    status: str = "running"
    artifact_paths: list[str] = Field(default_factory=list)


class ExperimentTracker:
    """Store experiment records as JSON files under ``experiments_dir/{model_name}/``."""

    def __init__(self, experiments_dir: Path) -> None:
        self._experiments_dir = Path(experiments_dir)
        self._experiments_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def start_experiment(
        self,
        model_name: str,
        dataset_name: str,
        hyperparameters: dict,
    ) -> str:
        """Create a running experiment record and return its identifier."""
        record = ExperimentRecord(
            model_name=model_name,
            dataset_name=dataset_name,
            hyperparameters=dict(hyperparameters),
            status="running",
        )
        with self._lock:
            self._write_record(record)
        return record.experiment_id

    def log_metric(self, experiment_id: str, metric_name: str, value: float) -> None:
        """Record or overwrite a single scalar metric on a running experiment."""
        with self._lock:
            record = self._read_record(experiment_id)
            record.metrics[metric_name] = float(value)
            self._write_record(record)

    def log_artifact(self, experiment_id: str, artifact_path: Path) -> None:
        """Attach an artifact path to an experiment record."""
        stored = str(Path(artifact_path))
        with self._lock:
            record = self._read_record(experiment_id)
            if stored not in record.artifact_paths:
                record.artifact_paths.append(stored)
            self._write_record(record)

    def complete_experiment(self, experiment_id: str, metrics: dict) -> None:
        """Mark an experiment completed and merge final metrics."""
        completed_at = datetime.now(UTC)
        with self._lock:
            record = self._read_record(experiment_id)
            merged = dict(record.metrics)
            merged.update({str(key): float(value) for key, value in metrics.items()})
            record.metrics = merged
            record.completed_at = completed_at
            record.duration_seconds = round(
                (completed_at - record.started_at).total_seconds(),
                4,
            )
            record.status = "completed"
            self._write_record(record)

    def get_experiment(self, experiment_id: str) -> ExperimentRecord:
        """Return a single experiment record by identifier."""
        with self._lock:
            return self._read_record(experiment_id)

    def list_experiments(self, model_name: Optional[str] = None) -> list[ExperimentRecord]:
        """List experiment records, optionally filtered by model name."""
        with self._lock:
            records = self._load_all(model_name)
        records.sort(key=lambda item: item.started_at, reverse=True)
        return records

    def get_best_experiment(self, model_name: str, metric: str) -> ExperimentRecord:
        """Return the completed experiment with the best (highest) ``metric`` value."""
        candidates = [
            item
            for item in self.list_experiments(model_name)
            if item.status == "completed" and metric in item.metrics
        ]
        if not candidates:
            raise ExperimentNotFoundError(
                f"No completed experiments for model {model_name!r} with metric {metric!r}"
            )
        return max(candidates, key=lambda item: float(item.metrics[metric]))

    def _model_dir(self, model_name: str) -> Path:
        safe_name = _UNSAFE_NAME.sub("_", model_name.strip()) or "unnamed_model"
        path = self._experiments_dir / safe_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _record_path(self, model_name: str, experiment_id: str) -> Path:
        return self._model_dir(model_name) / f"{experiment_id}.json"

    def _write_record(self, record: ExperimentRecord) -> None:
        path = self._record_path(record.model_name, record.experiment_id)
        path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

    def _read_record(self, experiment_id: str) -> ExperimentRecord:
        for path in self._experiments_dir.glob(f"*/{experiment_id}.json"):
            return ExperimentRecord.model_validate_json(path.read_text(encoding="utf-8"))
        raise ExperimentNotFoundError(f"Experiment not found: {experiment_id}")

    def _load_all(self, model_name: Optional[str]) -> list[ExperimentRecord]:
        if model_name is not None:
            directory = self._model_dir(model_name)
            paths = directory.glob("*.json")
        else:
            paths = self._experiments_dir.glob("*/*.json")
        records: list[ExperimentRecord] = []
        for path in paths:
            try:
                records.append(
                    ExperimentRecord.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError):
                continue
        return records
