"""Threat intelligence bootstrap — YARA, Sigma, MITRE."""

from __future__ import annotations

import logging
import time
from typing import Any

from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)


class ThreatIntelInitializer:
    """Load threat intelligence rules and mappings at startup."""

    def __init__(
        self,
        feed_manager: Any,
        yara_engine: Any,
        sigma_engine: Any,
        mitre_mapper: Any,
        settings: DFATSettings,
    ) -> None:
        self._feed_manager = feed_manager
        self._yara_engine = yara_engine
        self._sigma_engine = sigma_engine
        self._mitre_mapper = mitre_mapper
        self._settings = settings

    async def initialize(self) -> PhaseResult:
        """Load YARA rules, Sigma rules, and initialize MITRE mapper.

        Returns:
            ``PhaseResult`` — COMPLETED or DEGRADED.
        """
        started = time.perf_counter()
        details: dict[str, Any] = {}
        degraded: list[str] = []

        # YARA
        try:
            yara_count = self._yara_engine.load_rules()
            details["yara_rules_loaded"] = yara_count
            if yara_count == 0:
                degraded.append("yara_rules")
                logger.warning("No YARA rules loaded (yara-python missing or no .yar files)")
        except Exception as exc:  # noqa: BLE001
            details["yara_rules_loaded"] = 0
            details["yara_error"] = str(exc)
            degraded.append("yara_rules")
            logger.warning("YARA rule loading failed: %s", exc)

        # Sigma
        try:
            sigma_count = self._sigma_engine.load_rules()
            details["sigma_rules_loaded"] = sigma_count
            if sigma_count == 0:
                degraded.append("sigma_rules")
                logger.info("No Sigma rules loaded (pySigma missing or no .yml files)")
        except Exception as exc:  # noqa: BLE001
            details["sigma_rules_loaded"] = 0
            details["sigma_error"] = str(exc)
            degraded.append("sigma_rules")
            logger.warning("Sigma rule loading failed: %s", exc)

        # MITRE mapper (embedded, always available)
        try:
            mitre_techniques = 0
            if hasattr(self._mitre_mapper, "get_tactic_coverage"):
                mitre_techniques = len(
                    getattr(self._mitre_mapper, "_techniques", {})
                )
            details["mitre_techniques_mapped"] = mitre_techniques
        except Exception as exc:  # noqa: BLE001
            details["mitre_techniques_mapped"] = 0
            details["mitre_error"] = str(exc)

        duration_ms = (time.perf_counter() - started) * 1000.0
        status = InitStatus.COMPLETED if not degraded else InitStatus.DEGRADED
        message = (
            "Threat intelligence ready"
            if not degraded
            else f"Threat intelligence degraded: {', '.join(degraded)}"
        )

        return PhaseResult(
            phase=InitPhase.THREAT_INTELLIGENCE,
            status=status,
            duration_ms=duration_ms,
            message=message,
            details=details,
            is_critical=False,
            degraded_capabilities=degraded,
        )
