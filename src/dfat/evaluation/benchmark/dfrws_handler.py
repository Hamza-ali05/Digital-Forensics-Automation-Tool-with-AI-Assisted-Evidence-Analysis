"""DFRWS-specific ground truth dataset loader (local files only).

Never downloads datasets. Expects pre-placed JSON ground-truth files under
``datasets_dir`` (optionally in a ``dfrws/`` subdirectory).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from dfat.core.enums import ArtefactCategory
from dfat.core.exceptions import EvaluationError, GroundTruthNotFoundError


class GroundTruthArtefact(BaseModel):
    """Single expected artefact entry from a DFRWS ground-truth file."""

    model_config = ConfigDict(frozen=False)

    identifier: str
    category: ArtefactCategory
    expected_data: dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None


class GroundTruth(BaseModel):
    """Loaded and normalised DFRWS ground-truth dataset."""

    model_config = ConfigDict(frozen=False)

    dataset_name: str
    source: str = "DFRWS"
    artefacts: list[GroundTruthArtefact] = Field(default_factory=list)
    categories: list[ArtefactCategory] = Field(default_factory=list)
    loaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_count(self) -> int:
        """Return the number of ground-truth artefacts."""
        return len(self.artefacts)


class DFRWSHandler:
    """Load and normalise DFRWS ground-truth JSON datasets from local disk."""

    def __init__(self, datasets_dir: Path) -> None:
        """Initialise the handler.

        Args:
            datasets_dir: Directory containing pre-placed DFRWS ground-truth
                JSON files (never downloaded by this class).
        """
        self._datasets_dir = Path(datasets_dir)

    def list_available_datasets(self) -> list[str]:
        """Scan ``datasets_dir`` for DFRWS ground-truth JSON files.

        Returns:
            Sorted list of dataset names (basename without ``.json``).
            Never downloads anything.
        """
        names: set[str] = set()
        search_roots = [
            self._datasets_dir,
            self._datasets_dir / "dfrws",
        ]
        for root in search_roots:
            if not root.exists() or not root.is_dir():
                continue
            for path in root.glob("*.json"):
                if not path.is_file():
                    continue
                # Prefer files that look like DFRWS ground truth when readable.
                if self._looks_like_dfrws(path):
                    names.add(path.stem)
        return sorted(names)

    def load_ground_truth(self, dataset_name: str) -> GroundTruth:
        """Load, validate, and normalise a DFRWS ground-truth dataset.

        Args:
            dataset_name: Dataset basename (with or without ``.json``).

        Returns:
            Typed ``GroundTruth`` with normalised artefact identifiers.

        Raises:
            GroundTruthNotFoundError: If the dataset file is missing.
            EvaluationError: If JSON or structure validation fails.
        """
        path = self._resolve_dataset_path(dataset_name)
        return self.load_from_path(path)

    def load_from_path(self, path: Path) -> GroundTruth:
        """Load and normalise a DFRWS ground-truth JSON file by path.

        Args:
            path: Absolute or relative path to a ground-truth JSON file.

        Returns:
            Typed ``GroundTruth`` with normalised artefact identifiers.

        Raises:
            GroundTruthNotFoundError: If the file is missing.
            EvaluationError: If JSON or structure validation fails.
        """
        path = Path(path)
        if not path.exists() or not path.is_file():
            raise GroundTruthNotFoundError(
                f"Ground-truth dataset not found: {path}",
                context={"path": str(path)},
            )
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except json.JSONDecodeError as exc:
            raise EvaluationError(
                f"Invalid DFRWS ground-truth JSON: {path}",
                context={"path": str(path), "error": str(exc)},
            ) from exc

        if not isinstance(raw, dict):
            raise EvaluationError(
                "DFRWS ground-truth root must be a JSON object",
                context={"path": str(path)},
            )
        self._validate_structure(raw, path)
        return self._build_ground_truth(raw, path, default_source="DFRWS")

    def _build_ground_truth(
        self,
        raw: dict[str, Any],
        path: Path,
        *,
        default_source: str,
        artefact_entries: list[Any] | None = None,
    ) -> GroundTruth:
        """Build a ``GroundTruth`` model from a validated raw mapping."""
        entries = (
            artefact_entries
            if artefact_entries is not None
            else list(raw.get("artefacts") or [])
        )
        artefacts: list[GroundTruthArtefact] = []
        categories: set[ArtefactCategory] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise EvaluationError(
                    f"Ground-truth artefact at index {index} must be an object",
                    context={"path": str(path)},
                )
            category = self._parse_category(entry.get("category"), index, path)
            expected_data = dict(entry.get("expected_data") or {})
            raw_for_id = dict(expected_data)
            for key, value in entry.items():
                if key in {"category", "identifier", "description", "expected_data"}:
                    continue
                raw_for_id.setdefault(key, value)
            identifier = self._normalise_identifier(category.value, raw_for_id)
            if not identifier or identifier == f"{category.value}::":
                fallback = str(entry.get("identifier") or "").strip()
                identifier = (
                    self._normalise_token(fallback)
                    if fallback
                    else f"{category.value}::unknown_{index}"
                )
                if not identifier.startswith(f"{category.value}::"):
                    identifier = f"{category.value}::{identifier}"

            description = entry.get("description")
            artefacts.append(
                GroundTruthArtefact(
                    identifier=identifier,
                    category=category,
                    expected_data=expected_data,
                    description=str(description) if description is not None else None,
                )
            )
            categories.add(category)

        source = str(raw.get("source") or default_source)
        if source.lower() == "dfrws":
            source = "DFRWS"
        elif source.lower() == "cfreds":
            source = "CFReDS"

        dataset_name = str(
            raw.get("dataset_name")
            or raw.get("name")
            or path.stem
        )
        return GroundTruth(
            dataset_name=dataset_name,
            source=source,
            artefacts=artefacts,
            categories=sorted(categories, key=lambda item: item.value),
            loaded_at=datetime.now(UTC),
        )

    def _normalise_identifier(self, category: str, raw_data: dict[str, Any]) -> str:
        """Create a comparable identifier from category + key fields.

        Args:
            category: Artefact category string (enum value).
            raw_data: Expected / raw artefact field mapping.

        Returns:
            Normalised comparable identifier string.
        """
        cat = str(category).strip().lower()
        data = raw_data or {}

        if cat == ArtefactCategory.FILESYSTEM_METADATA.value:
            path_value = self._first_str(
                data,
                "normalised_path",
                "path",
                "source_path",
                "file_path",
            )
            normalised_path = self._normalise_path(path_value)
            filename = self._first_str(data, "filename", "file_name", "name")
            if not filename and normalised_path:
                filename = Path(normalised_path).name
            return self._join(cat, normalised_path, self._normalise_token(filename))

        if cat == ArtefactCategory.REGISTRY_KEY.value:
            hive = self._first_str(data, "hive", "registry_hive")
            key_path = self._normalise_path(
                self._first_str(data, "key_path", "path", "key")
            )
            value_name = self._normalise_token(
                self._first_str(data, "value_name", "name")
            )
            return self._join(cat, self._normalise_token(hive), key_path, value_name)

        if cat == ArtefactCategory.BROWSER_HISTORY.value:
            url = self._normalise_token(self._first_str(data, "url", "uri", "address"))
            return self._join(cat, url)

        if cat == ArtefactCategory.EVENT_LOG.value:
            event_id = self._normalise_token(
                self._first_str(data, "event_id", "eventId", "id")
            )
            timestamp = self._normalise_token(
                self._first_str(data, "timestamp", "time", "event_time")
            )
            return self._join(cat, event_id, timestamp)

        if cat == ArtefactCategory.RUNNING_PROCESS.value:
            name = self._normalise_token(
                self._first_str(data, "name", "process_name", "image_name")
            )
            pid = self._normalise_token(self._first_str(data, "pid", "process_id"))
            return self._join(cat, name, pid)

        if cat == ArtefactCategory.NETWORK_CONNECTION.value:
            remote_address = self._normalise_token(
                self._first_str(
                    data,
                    "remote_address",
                    "remote_ip",
                    "dst_ip",
                    "destination_address",
                )
            )
            remote_port = self._normalise_token(
                self._first_str(
                    data,
                    "remote_port",
                    "dst_port",
                    "destination_port",
                    "port",
                )
            )
            return self._join(cat, remote_address, remote_port)

        if cat == ArtefactCategory.INJECTED_CODE.value:
            pid = self._normalise_token(self._first_str(data, "pid", "process_id"))
            vad_start = self._normalise_token(
                self._first_str(data, "vad_start", "start", "base_address", "address")
            )
            return self._join(cat, pid, vad_start)

        # Unknown category — best-effort tokenisation of common keys.
        fallback = self._first_str(data, "identifier", "path", "name", "url", "pid")
        return self._join(cat, self._normalise_token(fallback))

    def _resolve_dataset_path(self, dataset_name: str) -> Path:
        """Resolve a dataset name to a local JSON file path."""
        name = dataset_name if dataset_name.endswith(".json") else f"{dataset_name}.json"
        candidates = [
            self._datasets_dir / "dfrws" / name,
            self._datasets_dir / name,
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        raise GroundTruthNotFoundError(
            f"Ground-truth dataset not found: {dataset_name}",
            context={
                "dataset_name": dataset_name,
                "searched": [str(path) for path in candidates],
            },
        )

    @staticmethod
    def _looks_like_dfrws(path: Path) -> bool:
        """Return True when a JSON file appears to be DFRWS ground truth."""
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(data, dict):
            return False
        if "artefacts" not in data:
            return False
        source = str(data.get("source") or "").lower()
        if source and source not in {"dfrws", ""}:
            # Explicit non-DFRWS source (e.g. cfreds) — skip in DFRWS listing.
            return False
        return True

    @staticmethod
    def _validate_structure(data: dict[str, Any], path: Path) -> None:
        """Validate the expected DFRWS ground-truth schema."""
        if "dataset_name" not in data or not isinstance(data["dataset_name"], str):
            raise EvaluationError(
                "Ground truth missing string field 'dataset_name'",
                context={"path": str(path)},
            )
        artefacts = data.get("artefacts")
        if not isinstance(artefacts, list):
            raise EvaluationError(
                "Ground truth missing list field 'artefacts'",
                context={"path": str(path)},
            )

    @staticmethod
    def _parse_category(
        raw: Any,
        index: int,
        path: Path,
    ) -> ArtefactCategory:
        """Parse an artefact category enum value."""
        try:
            return ArtefactCategory(str(raw).strip().lower())
        except ValueError as exc:
            raise EvaluationError(
                f"Unknown artefact category at index {index}: {raw!r}",
                context={"path": str(path)},
            ) from exc

    @staticmethod
    def _first_str(data: dict[str, Any], *keys: str) -> str:
        """Return the first non-empty string/number field among ``keys``."""
        for key in keys:
            if key not in data or data[key] is None:
                continue
            value = data[key]
            text = str(value).strip()
            if text:
                return text
        return ""

    @staticmethod
    def _normalise_path(value: str) -> str:
        """Normalise filesystem / registry path separators and case."""
        return DFRWSHandler._normalise_token(value.replace("\\", "/"))

    @staticmethod
    def _normalise_token(value: str) -> str:
        """Collapse whitespace and lowercase an identifier token."""
        return " ".join(str(value).strip().lower().split())

    @staticmethod
    def _join(*parts: str) -> str:
        """Join identifier parts with ``::``, dropping empty trailing noise."""
        cleaned = [part for part in parts if part]
        return "::".join(cleaned)
