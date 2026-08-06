"""DFAT Benchmark Evaluation — Ground truth comparison and metric calculation."""

from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.metrics import MetricsCalculator

__all__ = [
    "BenchmarkComparator",
    "GroundTruthLoader",
    "MetricsCalculator",
]
