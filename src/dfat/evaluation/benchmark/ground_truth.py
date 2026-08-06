"""Ground-truth loaders for DFRWS and CFReDS benchmark datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dfat.core.enums import ArtefactCategory
from dfat.core.exceptions import EvaluationError, GroundTruthNotFoundError


class GroundTruthLoader:
    """Load and validate DFRWS/CFReDS-style ground-truth JSON files."""

    def __init__(self, ground_truth_dir: Path) -> None:
        """Initialise the loader.

        Args:
            ground_truth_dir: Directory containing ground-truth JSON files.
        """
        self._ground_truth_dir = ground_truth_dir

    def load_dfrws(self, dataset_name: str) -> dict[str, Any]:
        """Load a DFRWS challenge ground-truth file.

        Args:
            dataset_name: Dataset basename (with or without ``.json``).

        Returns:
            Validated ground-truth mapping.

        Raises:
            GroundTruthNotFoundError: If the dataset file is missing.
            EvaluationError: If the structure is invalid.
        """
        path = self._resolve_named_path(dataset_name, preferred_subdir="dfrws")
        data = self.load(path)
        data.setdefault("source", "dfrws")
        return data

    def load_cfreds(self, dataset_name: str) -> dict[str, Any]:
        """Load a CFReDS ground-truth file.

        Args:
            dataset_name: Dataset basename (with or without ``.json``).

        Returns:
            Validated ground-truth mapping.

        Raises:
            GroundTruthNotFoundError: If the dataset file is missing.
            EvaluationError: If the structure is invalid.
        """
        path = self._resolve_named_path(dataset_name, preferred_subdir="cfreds")
        data = self.load(path)
        data.setdefault("source", "cfreds")
        return data

    def load(self, dataset_path: Path) -> dict[str, Any]:
        """Load and validate a ground-truth JSON file.

        Args:
            dataset_path: Path to a ground-truth JSON document.

        Returns:
            Validated ground-truth mapping.

        Raises:
            GroundTruthNotFoundError: If the path does not exist.
            EvaluationError: If JSON or structure validation fails.
        """
        if not dataset_path.exists() or not dataset_path.is_file():
            raise GroundTruthNotFoundError(
                f"Ground-truth dataset not found: {dataset_path}",
                context={"path": str(dataset_path)},
            )
        try:
            with dataset_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise EvaluationError(
                f"Invalid ground-truth JSON: {dataset_path}",
                context={"path": str(dataset_path), "error": str(exc)},
            ) from exc
        if not isinstance(data, dict):
            raise EvaluationError(
                "Ground-truth root must be a JSON object",
                context={"path": str(dataset_path)},
            )
        self._validate_structure(data, dataset_path)
        return data

    def get_expected_artefact_count(self, ground_truth: dict[str, Any]) -> int:
        """Return the number of expected artefacts.

        Args:
            ground_truth: Loaded ground-truth mapping.

        Returns:
            Expected artefact count.
        """
        artefacts = ground_truth.get("artefacts", [])
        return len(artefacts) if isinstance(artefacts, list) else 0

    def get_expected_categories(
        self,
        ground_truth: dict[str, Any],
    ) -> list[ArtefactCategory]:
        """Return distinct expected artefact categories.

        Args:
            ground_truth: Loaded ground-truth mapping.

        Returns:
            Sorted list of ``ArtefactCategory`` values present in ground truth.
        """
        categories: set[ArtefactCategory] = set()
        for entry in ground_truth.get("artefacts", []):
            if not isinstance(entry, dict):
                continue
            raw = str(entry.get("category", "")).strip().lower()
            try:
                categories.add(ArtefactCategory(raw))
            except ValueError:
                continue
        return sorted(categories, key=lambda item: item.value)

    def _resolve_named_path(self, dataset_name: str, preferred_subdir: str) -> Path:
        """Resolve a dataset name to a file under the ground-truth directory."""
        name = dataset_name if dataset_name.endswith(".json") else f"{dataset_name}.json"
        candidates = [
            self._ground_truth_dir / preferred_subdir / name,
            self._ground_truth_dir / name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise GroundTruthNotFoundError(
            f"Ground-truth dataset not found: {dataset_name}",
            context={
                "dataset_name": dataset_name,
                "searched": [str(path) for path in candidates],
            },
        )

    @staticmethod
    def _validate_structure(data: dict[str, Any], path: Path) -> None:
        """Validate the expected ground-truth schema."""
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
        for index, entry in enumerate(artefacts):
            if not isinstance(entry, dict):
                raise EvaluationError(
                    f"Ground-truth artefact at index {index} must be an object",
                    context={"path": str(path)},
                )
            for field in ("category", "identifier"):
                if field not in entry:
                    raise EvaluationError(
                        f"Ground-truth artefact missing '{field}' at index {index}",
                        context={"path": str(path)},
                    )
            if "expected_data" in entry and not isinstance(entry["expected_data"], dict):
                raise EvaluationError(
                    f"Ground-truth 'expected_data' must be an object at index {index}",
                    context={"path": str(path)},
                )
