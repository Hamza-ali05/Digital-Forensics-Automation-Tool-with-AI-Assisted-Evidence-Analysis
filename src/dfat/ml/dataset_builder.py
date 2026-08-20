"""Build labelled train/validation/test datasets from registered forensic datasets."""

from __future__ import annotations

import csv
import json
import logging
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.enums import ArtefactCategory, SuspicionLevel
from dfat.core.models.artefact import Artefact, RankedArtefact
from dfat.dataset_intelligence.enums import DatasetFormat
from dfat.dataset_intelligence.exceptions import DatasetNotFoundError
from dfat.dataset_intelligence.models import DatasetRecord
from dfat.dataset_intelligence.registry import DatasetRegistry
from dfat.ml.config import MLSettings
from dfat.ml.feature_engineering import ALL_FEATURE_NAMES, ForensicFeatureExtractor

logger = logging.getLogger(__name__)

_IMBALANCE_RATIO = 1.5
_POSITIVE_LABELS = frozenset({"suspicious", "malicious", "positive", "true", "1", "high", "critical"})
_NEGATIVE_LABELS = frozenset({"benign", "normal", "negative", "false", "0", "low", "informational", "clean"})
_SKIP_FORMATS = frozenset(
    {
        DatasetFormat.DISK_IMAGE,
        DatasetFormat.MEMORY_DUMP,
        DatasetFormat.PCAP,
        DatasetFormat.BINARY,
        DatasetFormat.YARA_RULES,
        DatasetFormat.SIGMA_RULES,
        DatasetFormat.UNKNOWN,
    }
)


class EmptyTrainingDatasetError(ValueError):
    """Raised when no labelled artefacts could be collected for training."""


class TrainingDataset(BaseModel):
    """ML-ready feature matrix, labels, and stratified split indices."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    name: str
    feature_matrix: Any
    labels: Any
    feature_names: list[str]
    train_indices: list[int]
    val_indices: list[int]
    test_indices: list[int]
    class_distribution: dict[str, int]
    total_samples: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MLDatasetBuilder:
    """Collect artefacts from registered datasets and produce a training split."""

    def __init__(
        self,
        feature_extractor: ForensicFeatureExtractor,
        dataset_registry: DatasetRegistry,
        settings: MLSettings | None = None,
    ) -> None:
        self._extractor = feature_extractor
        self._registry = dataset_registry
        self._settings = settings or MLSettings()

    async def build_training_dataset(
        self,
        model_name: str,
        source_datasets: list[str] | None = None,
    ) -> TrainingDataset:
        """Extract features, split, and balance a labelled training dataset."""
        datasets = await self._resolve_datasets(source_datasets)
        artefacts = await self._collect_artefacts(datasets)
        rows: list[list[float]] = []
        labels: list[int] = []
        class_names: dict[int, str] = {0: "benign", 1: "suspicious"}

        for artefact in artefacts:
            features = self._extractor.extract_all(artefact)
            label_name = self._label_for(artefact, features)
            label_id = self._encode_label(label_name, class_names)
            rows.append([float(features[name]) for name in ALL_FEATURE_NAMES])
            labels.append(label_id)

        if not rows:
            raise EmptyTrainingDatasetError(
                f"No labelled artefacts available for model {model_name!r}"
            )

        train_idx, val_idx, test_idx = self._split_indices(labels)
        train_idx, rows, labels = self._balance_training_split(train_idx, rows, labels)

        class_distribution = {
            class_names.get(label, str(label)): count
            for label, count in sorted(Counter(labels).items())
        }
        return TrainingDataset(
            name=model_name,
            feature_matrix=_as_array(rows, dtype="float"),
            labels=_as_array(labels, dtype="int"),
            feature_names=list(ALL_FEATURE_NAMES),
            train_indices=train_idx,
            val_indices=val_idx,
            test_indices=test_idx,
            class_distribution=class_distribution,
            total_samples=len(rows),
        )

    async def _resolve_datasets(self, source_datasets: list[str] | None) -> list[DatasetRecord]:
        registered = await self._registry.list_datasets()
        if not source_datasets:
            return list(registered)
        resolved: list[DatasetRecord] = []
        for key in source_datasets:
            match = next((item for item in registered if _dataset_matches(item, key)), None)
            if match is None:
                raise DatasetNotFoundError(f"Dataset not found: {key}")
            resolved.append(match)
        return resolved

    async def _collect_artefacts(self, datasets: list[DatasetRecord]) -> list[Artefact]:
        artefacts: list[Artefact] = []
        for dataset in datasets:
            if dataset.format in _SKIP_FORMATS:
                logger.debug("Skipping non-tabular dataset %s (%s)", dataset.name, dataset.format.value)
                continue
            loaded = await self._load_dataset_artefacts(dataset)
            artefacts.extend(loaded)
        return artefacts

    async def _load_dataset_artefacts(self, dataset: DatasetRecord) -> list[Artefact]:
        path = Path(dataset.file_path)
        if not path.exists() or not path.is_file():
            logger.warning("Dataset file missing: %s", path)
            return []
        if dataset.format is DatasetFormat.CSV or path.suffix.lower() == ".csv":
            return _artefacts_from_csv(path, dataset.name)
        if dataset.format in {DatasetFormat.JSON, DatasetFormat.STIX_BUNDLE} or path.suffix.lower() == ".json":
            return _artefacts_from_json(path, dataset.name)
        return []

    def _split_indices(self, labels: list[int]) -> tuple[list[int], list[int], list[int]]:
        settings = self._settings
        rng = random.Random(settings.random_seed)
        by_class: dict[int, list[int]] = {}
        for index, label in enumerate(labels):
            by_class.setdefault(label, []).append(index)

        train: list[int] = []
        val: list[int] = []
        test: list[int] = []
        for indices in by_class.values():
            rng.shuffle(indices)
            count = len(indices)
            n_test = int(round(count * settings.test_split))
            n_val = int(round(count * settings.validation_split))
            if count >= 3:
                n_test = min(max(n_test, 1), count - 2)
                n_val = min(max(n_val, 1), count - n_test - 1)
            else:
                n_test = 0
                n_val = 0
            test.extend(indices[:n_test])
            val.extend(indices[n_test : n_test + n_val])
            train.extend(indices[n_test + n_val :])

        rng.shuffle(train)
        rng.shuffle(val)
        rng.shuffle(test)
        return train, val, test

    def _balance_training_split(
        self,
        train_indices: list[int],
        rows: list[list[float]],
        labels: list[int],
    ) -> tuple[list[int], list[list[float]], list[int]]:
        if len(train_indices) < 4:
            return train_indices, rows, labels

        train_labels = [labels[index] for index in train_indices]
        counts = Counter(train_labels)
        if len(counts) < 2:
            return train_indices, rows, labels

        majority_label, majority_count = counts.most_common(1)[0]
        minority_label, minority_count = counts.most_common()[-1]
        if minority_count == 0 or majority_count / minority_count <= _IMBALANCE_RATIO:
            return train_indices, rows, labels

        rng = random.Random(self._settings.random_seed)
        if majority_count >= 200:
            balanced = self._undersample(train_indices, labels, majority_label, minority_count, rng)
            return balanced, rows, labels

        added_rows, added_labels = self._smote_or_oversample(
            rows,
            labels,
            train_indices,
            minority_label,
            majority_count - minority_count,
            rng,
        )
        start = len(rows)
        rows.extend(added_rows)
        labels.extend(added_labels)
        train_indices = list(train_indices) + list(range(start, start + len(added_rows)))
        return train_indices, rows, labels

    @staticmethod
    def _undersample(
        train_indices: list[int],
        labels: list[int],
        majority_label: int,
        target: int,
        rng: random.Random,
    ) -> list[int]:
        majority = [index for index in train_indices if labels[index] == majority_label]
        kept = [index for index in train_indices if labels[index] != majority_label]
        kept.extend(rng.sample(majority, min(target, len(majority))))
        rng.shuffle(kept)
        return kept

    @staticmethod
    def _smote_or_oversample(
        rows: list[list[float]],
        labels: list[int],
        train_indices: list[int],
        minority_label: int,
        needed: int,
        rng: random.Random,
    ) -> tuple[list[list[float]], list[int]]:
        minority = [index for index in train_indices if labels[index] == minority_label]
        synthetic_rows: list[list[float]] = []
        synthetic_labels: list[int] = []
        if len(minority) >= 2:
            for _ in range(needed):
                left, right = rng.sample(minority, 2)
                alpha = rng.random()
                interpolated = [
                    value + alpha * (rows[right][column] - value)
                    for column, value in enumerate(rows[left])
                ]
                synthetic_rows.append(interpolated)
                synthetic_labels.append(minority_label)
            return synthetic_rows, synthetic_labels

        source = rows[minority[0]]
        for _ in range(needed):
            synthetic_rows.append(list(source))
            synthetic_labels.append(minority_label)
        return synthetic_rows, synthetic_labels

    def _label_for(self, artefact: Artefact, features: dict[str, Any]) -> str:
        raw = artefact.raw_data if isinstance(artefact.raw_data, dict) else {}
        metadata = artefact.metadata if isinstance(artefact.metadata, dict) else {}
        for bag in (metadata, raw):
            for key in ("label", "class", "target", "y"):
                value = bag.get(key)
                if value is not None and str(value).strip():
                    return _normalise_label(str(value))
            suspicion = bag.get("suspicion_level")
            if suspicion is not None:
                return _label_from_suspicion(str(suspicion))
        if isinstance(artefact, RankedArtefact):
            return _label_from_suspicion(artefact.suspicion_level.value)
        if (
            features.get("has_suspicious_name")
            or features.get("is_autorun")
            or (features.get("is_external") and features.get("port_is_suspicious"))
        ):
            return "suspicious"
        return "benign"

    @staticmethod
    def _encode_label(label_name: str, class_names: dict[int, str]) -> int:
        reversed_map = {name: label_id for label_id, name in class_names.items()}
        if label_name in reversed_map:
            return reversed_map[label_name]
        next_id = max(class_names) + 1 if class_names else 0
        class_names[next_id] = label_name
        return next_id


def _dataset_matches(dataset: DatasetRecord, key: str) -> bool:
    path = Path(dataset.file_path)
    return key in {dataset.dataset_id, dataset.name, path.stem, path.name, str(path)}


def _artefacts_from_csv(path: Path, dataset_name: str) -> list[Artefact]:
    artefacts: list[Artefact] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            artefact = _mapping_to_artefact(row, dataset_name, index)
            if artefact is not None:
                artefacts.append(artefact)
    return artefacts


def _artefacts_from_json(path: Path, dataset_name: str) -> list[Artefact]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    records = _json_records(payload)
    artefacts: list[Artefact] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        artefact = _mapping_to_artefact(record, dataset_name, index)
        if artefact is not None:
            artefacts.append(artefact)
    return artefacts


def _json_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("artefacts", "items", "records", "data", "objects"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return [payload]


def _mapping_to_artefact(record: dict[str, Any], dataset_name: str, index: int) -> Artefact | None:
    raw = record.get("raw_data")
    expected = record.get("expected_data")
    if isinstance(raw, dict):
        payload = dict(raw)
    elif isinstance(expected, dict):
        payload = dict(expected)
    else:
        reserved = {
            "artefact_id",
            "category",
            "source_evidence_id",
            "source_path",
            "metadata",
            "label",
            "class",
            "target",
            "y",
            "suspicion_level",
            "identifier",
            "description",
            "expected_data",
            "raw_data",
        }
        payload = {key: value for key, value in record.items() if key not in reserved}

    identifier = record.get("identifier")
    if identifier and "name" not in payload and "path" not in payload:
        text = str(identifier)
        if "\\" in text or "/" in text:
            payload.setdefault("path", text)
            payload.setdefault("filename", Path(text).name)
            payload.setdefault("key_path", text)
        else:
            payload.setdefault("name", text)

    category = _parse_category(record.get("category"))
    if category is None:
        category = _infer_category(payload)
    if category is None:
        return None

    _apply_category_defaults(category, payload, record)
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    label = record.get("label") or record.get("class") or record.get("target")
    if label is not None:
        metadata = {**metadata, "label": str(label)}
    suspicion = record.get("suspicion_level")
    if suspicion is not None:
        metadata = {**metadata, "suspicion_level": str(suspicion)}
    if record.get("identifier") and "label" not in metadata and "suspicion_level" not in metadata:
        # Ground-truth expected artefacts are treated as the positive class.
        metadata = {**metadata, "label": "suspicious"}

    return Artefact(
        artefact_id=str(record.get("artefact_id") or f"{dataset_name}:{index}"),
        category=category,
        source_evidence_id=str(record.get("source_evidence_id") or dataset_name),
        raw_data=payload,
        source_path=record.get("source_path") or record.get("identifier"),
        metadata=metadata,
    )


def _parse_category(value: Any) -> ArtefactCategory | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return ArtefactCategory(text)
    except ValueError:
        aliases = {
            "process": ArtefactCategory.RUNNING_PROCESS,
            "file": ArtefactCategory.FILESYSTEM_METADATA,
            "filesystem": ArtefactCategory.FILESYSTEM_METADATA,
            "network": ArtefactCategory.NETWORK_CONNECTION,
            "registry": ArtefactCategory.REGISTRY_KEY,
        }
        return aliases.get(text)


def _infer_category(payload: dict[str, Any]) -> ArtefactCategory | None:
    keys = set(payload)
    if {"pid", "name"} <= keys or "process_name" in keys:
        return ArtefactCategory.RUNNING_PROCESS
    if {"filename", "path"} <= keys or "is_deleted" in keys:
        return ArtefactCategory.FILESYSTEM_METADATA
    if "remote_address" in keys or "protocol" in keys:
        return ArtefactCategory.NETWORK_CONNECTION
    if "key_path" in keys or "hive_name" in keys:
        return ArtefactCategory.REGISTRY_KEY
    return None


def _apply_category_defaults(
    category: ArtefactCategory,
    payload: dict[str, Any],
    record: dict[str, Any],
) -> None:
    if category is ArtefactCategory.FILESYSTEM_METADATA:
        payload.setdefault("filename", Path(str(payload.get("path") or record.get("identifier") or "file")).name)
        payload.setdefault("path", str(record.get("identifier") or payload.get("filename") or ""))
        payload.setdefault("size", 0)
        payload.setdefault("is_deleted", False)
        payload.setdefault("file_type", "file")
    elif category is ArtefactCategory.RUNNING_PROCESS:
        payload.setdefault("name", str(record.get("identifier") or "unknown"))
        payload.setdefault("pid", 0)
    elif category is ArtefactCategory.NETWORK_CONNECTION:
        payload.setdefault("protocol", "tcp")
        payload.setdefault("local_address", "0.0.0.0")
        payload.setdefault("remote_address", "0.0.0.0")
        payload.setdefault("is_external", False)
    elif category is ArtefactCategory.REGISTRY_KEY:
        payload.setdefault("hive_name", "SOFTWARE")
        payload.setdefault("key_path", str(record.get("identifier") or ""))
        payload.setdefault("value_name", "")
        payload.setdefault("value_data", "")
        payload.setdefault("value_type", "REG_SZ")


def _normalise_label(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in _POSITIVE_LABELS or lowered in {item.value for item in (SuspicionLevel.HIGH, SuspicionLevel.CRITICAL)}:
        return "suspicious"
    if lowered in _NEGATIVE_LABELS or lowered in {
        SuspicionLevel.LOW.value,
        SuspicionLevel.INFORMATIONAL.value,
        SuspicionLevel.MEDIUM.value,
    }:
        return "benign"
    return lowered or "benign"


def _label_from_suspicion(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {SuspicionLevel.HIGH.value, SuspicionLevel.CRITICAL.value, "suspicious", "malicious"}:
        return "suspicious"
    return "benign"


def _as_array(values: list[Any], *, dtype: str) -> Any:
    try:
        import numpy as np

        return np.asarray(values, dtype=float if dtype == "float" else int)
    except ImportError:
        return values
