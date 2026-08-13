"""DFAT Benchmark Evaluation — Ground truth comparison and metric calculation."""

from dfat.evaluation.benchmark.cfreds_handler import CFReDSHandler
from dfat.evaluation.benchmark.comparator import BenchmarkComparator
from dfat.evaluation.benchmark.dfrws_handler import (
    DFRWSHandler,
    GroundTruth,
    GroundTruthArtefact,
)
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.evaluation.benchmark.metrics import MetricsCalculator
from dfat.evaluation.benchmark.performance import (
    PerformanceAnalyzer,
    PerformanceReport,
    SpeedupResult,
    TimeStats,
)
from dfat.evaluation.benchmark.visualisation import MetricsVisualiser

__all__ = [
    "BenchmarkComparator",
    "CFReDSHandler",
    "DFRWSHandler",
    "GroundTruth",
    "GroundTruthArtefact",
    "GroundTruthLoader",
    "MetricsCalculator",
    "MetricsVisualiser",
    "PerformanceAnalyzer",
    "PerformanceReport",
    "SpeedupResult",
    "TimeStats",
]
