"""Dataset discovery bootstrap phase."""

from __future__ import annotations

import logging
import time
from typing import Any

from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.dataset_intelligence.registry import DatasetRegistry
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)


class DatasetInitializer:
    """Scan and register datasets from the configured datasets directory."""

    def __init__(self, dataset_registry: DatasetRegistry, settings: DFATSettings) -> None:
        self._registry = dataset_registry
        self._settings = settings

    async def initialize(self) -> PhaseResult:
        """Run dataset discovery scan.

        Non-critical — an empty datasets directory is valid.

        Returns:
            ``PhaseResult`` with dataset counts.
        """
        started = time.perf_counter()
        details: dict[str, Any] = {}

        try:
            scan_result = await self._registry.register_all()
            total = len(scan_result.datasets)
            new_count = getattr(scan_result, "new_count", total)
            updated_count = getattr(scan_result, "updated_count", 0)
            details["total_discovered"] = total
            details["new_datasets"] = new_count
            details["already_registered"] = updated_count
            details["failed"] = getattr(scan_result, "failed_count", 0)
            details["scan_path"] = str(getattr(scan_result, "scan_path", ""))

            if total == 0:
                logger.info(
                    "Dataset directory empty or not present — datasets can be added later."
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Dataset discovery scan failed: %s", exc)
            details["error"] = str(exc)
            duration_ms = (time.perf_counter() - started) * 1000.0
            return PhaseResult(
                phase=InitPhase.DATASET_DISCOVERY,
                status=InitStatus.DEGRADED,
                duration_ms=duration_ms,
                message=f"Dataset discovery degraded: {exc}",
                details=details,
                error=str(exc),
                is_critical=False,
                degraded_capabilities=["dataset_discovery"],
            )

        duration_ms = (time.perf_counter() - started) * 1000.0
        return PhaseResult(
            phase=InitPhase.DATASET_DISCOVERY,
            status=InitStatus.COMPLETED,
            duration_ms=duration_ms,
            message=(
                f"Dataset discovery complete: {total} datasets "
                f"({new_count} new, {updated_count} existing)"
            ),
            details=details,
            is_critical=False,
        )
