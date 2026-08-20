"""Benchmark evaluation dataset availability bootstrap."""

from __future__ import annotations

import logging
import time
from typing import Any

from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.evaluation.benchmark.ground_truth import GroundTruthLoader
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)


class EvaluationInitializer:
    """Check availability of DFRWS and CFReDS benchmark datasets."""

    def __init__(
        self,
        ground_truth_loader: GroundTruthLoader,
        settings: DFATSettings,
    ) -> None:
        self._loader = ground_truth_loader
        self._settings = settings

    async def initialize(self) -> PhaseResult:
        """Probe for pre-placed benchmark datasets.

        Non-critical — benchmarks are run on demand.

        Returns:
            ``PhaseResult`` — COMPLETED or DEGRADED.
        """
        started = time.perf_counter()
        details: dict[str, Any] = {}
        degraded: list[str] = []

        try:
            available = self._loader.list_all_datasets()
            dfrws_datasets = available.get("dfrws", [])
            cfreds_datasets = available.get("cfreds", [])
            details["dfrws_datasets"] = dfrws_datasets
            details["cfreds_datasets"] = cfreds_datasets
            details["total_available"] = len(dfrws_datasets) + len(cfreds_datasets)

            if not dfrws_datasets and not cfreds_datasets:
                degraded.append("benchmark_datasets")
                logger.info(
                    "No benchmark datasets found. Place DFRWS/CFReDS ground-truth "
                    "JSON files in %s to enable evaluation.",
                    self._settings.evaluation.ground_truth_dir,
                )
        except Exception as exc:  # noqa: BLE001
            details["error"] = str(exc)
            degraded.append("benchmark_datasets")
            logger.warning("Evaluation dataset scan failed: %s", exc)

        duration_ms = (time.perf_counter() - started) * 1000.0
        status = InitStatus.COMPLETED if not degraded else InitStatus.DEGRADED
        message = (
            f"Evaluation ready ({details.get('total_available', 0)} benchmark datasets)"
            if not degraded
            else "Evaluation degraded: no benchmark datasets available"
        )

        return PhaseResult(
            phase=InitPhase.EVALUATION,
            status=status,
            duration_ms=duration_ms,
            message=message,
            details=details,
            is_critical=False,
            degraded_capabilities=degraded,
        )
