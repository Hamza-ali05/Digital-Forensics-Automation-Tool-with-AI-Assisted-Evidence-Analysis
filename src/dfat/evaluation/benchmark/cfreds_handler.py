"""CFReDS-specific ground truth dataset loader (local files only).

Never downloads datasets. Expects pre-placed JSON ground-truth files under
``datasets_dir`` (optionally in a ``cfreds/`` subdirectory).

CFReDS files may use alternate field names (``items`` / ``findings``,
``name`` instead of ``dataset_name``, ``type`` instead of ``category``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dfat.core.exceptions import EvaluationError, GroundTruthNotFoundError
from dfat.evaluation.benchmark.dfrws_handler import DFRWSHandler, GroundTruth


class CFReDSHandler(DFRWSHandler):
    """Load and normalise CFReDS ground-truth JSON datasets from local disk."""

    def list_available_datasets(self) -> list[str]:
        """Scan ``datasets_dir`` for CFReDS ground-truth JSON files.

        Returns:
            Sorted list of dataset names (basename without ``.json``).
            Never downloads anything.
        """
        names: set[str] = set()
        search_roots = [
            self._datasets_dir,
            self._datasets_dir / "cfreds",
        ]
        for root in search_roots:
            if not root.exists() or not root.is_dir():
                continue
            for path in root.glob("*.json"):
                if path.is_file() and self._looks_like_cfreds(path):
                    names.add(path.stem)
        return sorted(names)

    def load_ground_truth(self, dataset_name: str) -> GroundTruth:
        """Load, validate, and normalise a CFReDS ground-truth dataset.

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
        """Load and normalise a CFReDS ground-truth JSON file by path.

        Args:
            path: Path to a CFReDS ground-truth JSON file.

        Returns:
            Typed ``GroundTruth`` model.

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
                f"Invalid CFReDS ground-truth JSON: {path}",
                context={"path": str(path), "error": str(exc)},
            ) from exc

        if not isinstance(raw, dict):
            raise EvaluationError(
                "CFReDS ground-truth root must be a JSON object",
                context={"path": str(path)},
            )

        normalised = self._normalise_cfreds_document(raw, path)
        self._validate_structure(normalised, path)
        return self._build_ground_truth(
            normalised,
            path,
            default_source="CFReDS",
            artefact_entries=list(normalised.get("artefacts") or []),
        )

    def _resolve_dataset_path(self, dataset_name: str) -> Path:
        """Resolve a CFReDS dataset name to a local JSON file path."""
        name = dataset_name if dataset_name.endswith(".json") else f"{dataset_name}.json"
        candidates = [
            self._datasets_dir / "cfreds" / name,
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
    def _looks_like_cfreds(path: Path) -> bool:
        """Return True when a JSON file appears to be CFReDS ground truth."""
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(data, dict):
            return False
        source = str(data.get("source") or "").lower()
        if source == "cfreds":
            return True
        if source == "dfrws":
            return False
        # CFReDS-style alternate containers without an explicit DFRWS source.
        if any(key in data for key in ("items", "findings", "expected_artefacts")):
            return True
        nested = data.get("ground_truth")
        if isinstance(nested, dict) and isinstance(nested.get("artefacts"), list):
            return True
        # Path heuristic: living under a cfreds directory.
        return "cfreds" in {part.lower() for part in path.parts}

    @classmethod
    def _normalise_cfreds_document(
        cls,
        raw: dict[str, Any],
        path: Path,
    ) -> dict[str, Any]:
        """Map CFReDS field aliases onto the shared ground-truth schema."""
        document = dict(raw)

        if "dataset_name" not in document or not isinstance(document.get("dataset_name"), str):
            for key in ("name", "dataset", "id", "title"):
                value = document.get(key)
                if isinstance(value, str) and value.strip():
                    document["dataset_name"] = value.strip()
                    break
            else:
                document["dataset_name"] = path.stem

        document.setdefault("source", "CFReDS")
        if str(document.get("source", "")).lower() == "cfreds":
            document["source"] = "CFReDS"

        entries = cls._extract_artefact_entries(document)
        normalised_entries: list[dict[str, Any]] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise EvaluationError(
                    f"CFReDS artefact at index {index} must be an object",
                    context={"path": str(path)},
                )
            normalised_entries.append(cls._normalise_cfreds_entry(entry))
        document["artefacts"] = normalised_entries
        return document

    @staticmethod
    def _extract_artefact_entries(document: dict[str, Any]) -> list[Any]:
        """Return the artefact list from CFReDS or shared field names."""
        for key in ("artefacts", "items", "findings", "expected_artefacts"):
            value = document.get(key)
            if isinstance(value, list):
                return value
        nested = document.get("ground_truth")
        if isinstance(nested, dict) and isinstance(nested.get("artefacts"), list):
            return list(nested["artefacts"])
        return []

    @staticmethod
    def _normalise_cfreds_entry(entry: dict[str, Any]) -> dict[str, Any]:
        """Normalise a single CFReDS artefact entry to shared fields."""
        normalised = dict(entry)

        if "category" not in normalised:
            for key in ("type", "artefact_type", "artefact_category"):
                if key in normalised and normalised[key] is not None:
                    normalised["category"] = normalised[key]
                    break

        expected = normalised.get("expected_data")
        if not isinstance(expected, dict):
            for key in ("data", "attributes", "properties", "fields"):
                value = normalised.get(key)
                if isinstance(value, dict):
                    expected = value
                    break
            else:
                expected = {}
            normalised["expected_data"] = dict(expected)

        if "identifier" not in normalised or not normalised.get("identifier"):
            for key in ("id", "key", "uid", "artefact_id"):
                value = normalised.get(key)
                if value is not None and str(value).strip():
                    normalised["identifier"] = str(value).strip()
                    break

        if "description" not in normalised:
            for key in ("desc", "label", "summary"):
                if key in normalised:
                    normalised["description"] = normalised[key]
                    break

        return normalised
