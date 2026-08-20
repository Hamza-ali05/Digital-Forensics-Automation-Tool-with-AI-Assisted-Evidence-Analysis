"""AI subsystem bootstrap — Ollama, RAG, ML models."""

from __future__ import annotations

import logging
import time
from typing import Any

from dfat.bootstrap.models import InitPhase, InitStatus, PhaseResult
from dfat.settings import DFATSettings

logger = logging.getLogger(__name__)


class AIInitializer:
    """Check LLM connectivity, RAG readiness, and ML model availability."""

    def __init__(
        self,
        llm_connection: Any,
        rag_analyzer: Any | None,
        rule_based_analyzer: Any,
        ml_predictor: Any | None,
        model_registry: Any | None,
        auto_retrainer: Any | None,
        settings: DFATSettings,
    ) -> None:
        self._llm_connection = llm_connection
        self._rag_analyzer = rag_analyzer
        self._rule_based = rule_based_analyzer
        self._ml_predictor = ml_predictor
        self._model_registry = model_registry
        self._auto_retrainer = auto_retrainer
        self._settings = settings

    async def initialize(self) -> PhaseResult:
        """Probe all AI capabilities (compat / combined entry point)."""
        llm = await self.initialize_llm()
        rag = await self.initialize_rag()
        ml = await self.initialize_ml()
        degraded = list(
            dict.fromkeys(
                llm.degraded_capabilities
                + rag.degraded_capabilities
                + ml.degraded_capabilities
            )
        )
        details = {
            **llm.details,
            **rag.details,
            **ml.details,
            "capabilities": {
                "llm": "llm_service" not in llm.degraded_capabilities
                and llm.status != InitStatus.FAILED,
                "rag": "rag_pipeline" not in rag.degraded_capabilities
                and rag.status != InitStatus.FAILED,
                "ml": "ml_models" not in ml.degraded_capabilities
                and ml.status != InitStatus.FAILED,
                "fallback": True,
            },
        }
        status = InitStatus.COMPLETED if not degraded else InitStatus.DEGRADED
        return PhaseResult(
            phase=InitPhase.LLM_SERVICE,
            status=status,
            duration_ms=llm.duration_ms + rag.duration_ms + ml.duration_ms,
            message=(
                "AI subsystem ready (LLM + RAG + ML)"
                if not degraded
                else (
                    f"AI subsystem degraded: {', '.join(degraded)}; "
                    "rule-based fallback always available"
                )
            ),
            details=details,
            is_critical=False,
            degraded_capabilities=degraded,
        )

    async def initialize_llm(self) -> PhaseResult:
        """Check Ollama connectivity and model readiness."""
        started = time.perf_counter()
        details: dict[str, Any] = {}
        degraded: list[str] = []

        try:
            health = await self._llm_connection.check_health()
            llm_ok = getattr(health, "is_healthy", False)
            details["llm_healthy"] = llm_ok
            details["llm_model"] = getattr(health, "model_name", None)
            details["llm_response_ms"] = getattr(health, "response_time_ms", None)
            if llm_ok:
                logger.info(
                    "Ollama healthy — model=%s",
                    details["llm_model"],
                )
            else:
                degraded.append("llm_service")
                logger.warning(
                    "Ollama unhealthy — rule-based fallback active. Error: %s",
                    getattr(health, "error", "unknown"),
                )
        except Exception as exc:  # noqa: BLE001
            details["llm_healthy"] = False
            details["llm_error"] = str(exc)
            degraded.append("llm_service")
            logger.warning(
                "LLM health check failed: %s — rule-based fallback active",
                exc,
            )

        duration_ms = (time.perf_counter() - started) * 1000.0
        status = InitStatus.COMPLETED if not degraded else InitStatus.DEGRADED
        return PhaseResult(
            phase=InitPhase.LLM_SERVICE,
            status=status,
            duration_ms=duration_ms,
            message=(
                "LLM service ready"
                if not degraded
                else "LLM service degraded — rule-based fallback active"
            ),
            details=details,
            is_critical=False,
            degraded_capabilities=degraded,
        )

    async def initialize_rag(self) -> PhaseResult:
        """Check RAG retriever / context-builder readiness."""
        started = time.perf_counter()
        details: dict[str, Any] = {}
        degraded: list[str] = []

        try:
            if self._rag_analyzer is not None:
                retriever = getattr(self._rag_analyzer, "_retriever", None)
                context_builder = getattr(self._rag_analyzer, "_context_builder", None)
                rag_ok = retriever is not None and context_builder is not None
                details["rag_available"] = rag_ok
                if not rag_ok:
                    degraded.append("rag_pipeline")
                    logger.info(
                        "RAG retriever/context builder not available — "
                        "standard prompts used"
                    )
            else:
                details["rag_available"] = False
                degraded.append("rag_pipeline")
                logger.info("RAG analyzer not configured — standard prompts used")
        except Exception as exc:  # noqa: BLE001
            details["rag_available"] = False
            details["rag_error"] = str(exc)
            degraded.append("rag_pipeline")

        duration_ms = (time.perf_counter() - started) * 1000.0
        status = InitStatus.COMPLETED if not degraded else InitStatus.DEGRADED
        return PhaseResult(
            phase=InitPhase.RAG_PIPELINE,
            status=status,
            duration_ms=duration_ms,
            message=(
                "RAG pipeline ready"
                if not degraded
                else "RAG pipeline degraded — standard prompts used"
            ),
            details=details,
            is_critical=False,
            degraded_capabilities=degraded,
        )

    async def initialize_ml(self) -> PhaseResult:
        """Load trained ML models and check auto-retrain configuration."""
        started = time.perf_counter()
        details: dict[str, Any] = {}
        degraded: list[str] = []

        try:
            models: list[dict[str, Any]] = []
            if self._model_registry is not None:
                registered = self._model_registry.list_models()
                for model in registered:
                    models.append(
                        {
                            "name": getattr(model, "model_name", "unknown"),
                            "version": getattr(model, "version", "?"),
                        }
                    )
            details["ml_models"] = models
            if models:
                logger.info(
                    "Loaded ML models: %s",
                    ", ".join(f"{m['name']}@{m['version']}" for m in models),
                )
            else:
                degraded.append("ml_models")
                logger.info("No trained ML models available — ML scoring disabled")
        except Exception as exc:  # noqa: BLE001
            details["ml_models"] = []
            details["ml_error"] = str(exc)
            degraded.append("ml_models")

        try:
            retrain_enabled = False
            if self._auto_retrainer is not None:
                retrain_enabled = (
                    getattr(self._auto_retrainer, "_settings", None) is not None
                )
            details["auto_retrain_enabled"] = retrain_enabled
        except Exception:  # noqa: BLE001
            details["auto_retrain_enabled"] = False

        duration_ms = (time.perf_counter() - started) * 1000.0
        status = InitStatus.COMPLETED if not degraded else InitStatus.DEGRADED
        return PhaseResult(
            phase=InitPhase.ML_MODELS,
            status=status,
            duration_ms=duration_ms,
            message=(
                f"ML models ready ({len(details.get('ml_models', []))} loaded)"
                if not degraded
                else "ML models degraded — scoring disabled"
            ),
            details=details,
            is_critical=False,
            degraded_capabilities=degraded,
        )
