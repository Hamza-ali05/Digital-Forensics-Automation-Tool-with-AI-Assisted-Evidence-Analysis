"""Abstract evaluator port for benchmark evaluation implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from dfat.core.models.artefact import ArtefactSet
from dfat.core.models.evaluation import BenchmarkResult


class IEvaluator(ABC):
    """Port for ground-truth loading and benchmark metric computation."""

    @abstractmethod
    def load_ground_truth(self, dataset_path: Path) -> dict[str, Any]:
        """Load ground-truth annotations from a dataset path.

        Args:
            dataset_path: Path to a DFRWS/CFReDS-style ground-truth file.

        Returns:
            Parsed ground-truth structure.
        """

    @abstractmethod
    def compute_metrics(
        self,
        recovered: ArtefactSet,
        ground_truth: dict[str, Any],
    ) -> BenchmarkResult:
        """Compute precision, recall, F1, and related benchmark metrics.

        Args:
            recovered: Artefacts recovered by the pipeline.
            ground_truth: Loaded ground-truth annotations.

        Returns:
            Benchmark result metrics.
        """

    @abstractmethod
    def compare(self, result: BenchmarkResult) -> dict[str, Any]:
        """Compare a benchmark result against configured thresholds.

        Args:
            result: Computed benchmark metrics.

        Returns:
            Comparison summary structure.
        """
