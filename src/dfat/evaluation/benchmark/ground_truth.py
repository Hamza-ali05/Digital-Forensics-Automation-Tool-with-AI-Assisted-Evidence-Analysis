"""Generic ground-truth loader with DFRWS / CFReDS auto-detection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dfat.core.enums import ArtefactCategory
from dfat.core.exceptions import EvaluationError, GroundTruthNotFoundError
from dfat.evaluation.benchmark.cfreds_handler import CFReDSHandler
from dfat.evaluation.benchmark.dfrws_handler import DFRWSHandler, GroundTruth


class GroundTruthLoader:
    """Facade that auto-detects ground-truth format and delegates to handlers."""

    def __init__(
        self,
        ground_truth_dir: Path,
        dfrws: DFRWSHandler,
        cfreds: CFReDSHandler,
    ) -> None:
        """Initialise the generic loader.

        Args:
            ground_truth_dir: Root directory of pre-placed ground-truth files.
            dfrws: DFRWS-specific handler.
            cfreds: CFReDS-specific handler.
        """
        self._ground_truth_dir = Path(ground_truth_dir)
        self._dfrws = dfrws
        self._cfreds = cfreds

    def load(self, dataset_path: Path) -> GroundTruth:
        """Load a ground-truth file, auto-detecting DFRWS vs CFReDS format.

        Args:
            dataset_path: Path to a ground-truth JSON document.

        Returns:
            Typed ``GroundTruth`` model.

        Raises:
            GroundTruthNotFoundError: If the path does not exist.
            EvaluationError: If JSON or structure validation fails.
        """
        path = Path(dataset_path)
        if not path.exists() or not path.is_file():
            raise GroundTruthNotFoundError(
                f"Ground-truth dataset not found: {path}",
                context={"path": str(path)},
            )
        fmt = self._detect_format(path)
        if fmt == "cfreds":
            return self._cfreds.load_from_path(path)
        return self._dfrws.load_from_path(path)

    def load_dfrws(self, name: str) -> GroundTruth:
        """Load a DFRWS dataset by name via ``DFRWSHandler``."""
        return self._dfrws.load_ground_truth(name)

    def load_cfreds(self, name: str) -> GroundTruth:
        """Load a CFReDS dataset by name via ``CFReDSHandler``."""
        return self._cfreds.load_ground_truth(name)

    def list_all_datasets(self) -> dict[str, list[str]]:
        """List pre-placed datasets for both sources.

        Returns:
            Mapping ``{"dfrws": [...], "cfreds": [...]}`` of dataset names.
            Never downloads anything.
        """
        return {
            "dfrws": self._dfrws.list_available_datasets(),
            "cfreds": self._cfreds.list_available_datasets(),
        }

    def get_expected_artefact_count(self, gt: GroundTruth) -> int:
        """Return the number of expected artefacts in ``gt``."""
        return int(gt.total_count)

    def get_expected_categories(self, gt: GroundTruth) -> list[ArtefactCategory]:
        """Return distinct expected artefact categories from ``gt``."""
        if gt.categories:
            return list(gt.categories)
        return sorted(
            {artefact.category for artefact in gt.artefacts},
            key=lambda item: item.value,
        )

    def _detect_format(self, path: Path) -> str:
        """Detect whether ``path`` is CFReDS or DFRWS format.

        Returns:
            ``\"cfreds\"`` or ``\"dfrws\"``.
        """
        parts = {part.lower() for part in path.parts}
        if "cfreds" in parts and "dfrws" not in parts:
            return "cfreds"
        if "dfrws" in parts and "cfreds" not in parts:
            return "dfrws"

        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise EvaluationError(
                f"Invalid ground-truth JSON: {path}",
                context={"path": str(path), "error": str(exc)},
            ) from exc

        if not isinstance(data, dict):
            raise EvaluationError(
                "Ground-truth root must be a JSON object",
                context={"path": str(path)},
            )

        source = str(data.get("source") or "").lower()
        if source == "cfreds":
            return "cfreds"
        if source == "dfrws":
            return "dfrws"

        if any(key in data for key in ("items", "findings", "expected_artefacts")):
            return "cfreds"
        nested = data.get("ground_truth")
        if isinstance(nested, dict) and isinstance(nested.get("artefacts"), list):
            return "cfreds"

        # Default to DFRWS shared schema when ambiguous.
        return "dfrws"
