"""Runtime ML inference for forensic artefacts."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from dfat.core.models.artefact import Artefact
from dfat.ml.feature_engineering import ForensicFeatureExtractor
from dfat.ml.model_registry import ModelRegistry
from dfat.ml.models import (
    AnomalyDetector,
    IOCPredictor,
    MalwareClassifier,
    ProcessSuspicionScorer,
)

logger = logging.getLogger(__name__)

_MODEL_WRAPPERS: dict[str, type] = {
    "MalwareClassifier": MalwareClassifier,
    "AnomalyDetector": AnomalyDetector,
    "ProcessSuspicionScorer": ProcessSuspicionScorer,
    "IOCPredictor": IOCPredictor,
}

_SCORE_MODEL_PRIORITY = (
    "ProcessSuspicionScorer",
    "MalwareClassifier",
    "IOCPredictor",
    "AnomalyDetector",
)


class MLPrediction(BaseModel):
    """Single-artefact inference result from a registered ML model."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    artefact_id: str
    model_name: str
    model_version: str
    prediction: Any
    confidence: float = Field(ge=0.0, le=1.0)
    feature_importance: dict[str, float] = Field(default_factory=dict)


class MLPredictor:
    """Load registered models and run feature extraction plus inference."""

    def __init__(
        self,
        model_registry: ModelRegistry,
        feature_extractor: ForensicFeatureExtractor | None = None,
    ) -> None:
        self._registry = model_registry
        self._extractor = feature_extractor or ForensicFeatureExtractor()

    async def predict(self, model_name: str, artefact: Artefact) -> MLPrediction:
        """Load the latest ``model_name`` version and run inference on ``artefact``."""
        record = self._registry.get_latest(model_name)
        if record is None:
            raise KeyError(f"No trained model registered for {model_name!r}")

        wrapper = _model_wrapper(model_name)
        features = self._extractor.extract_all(artefact)
        return await asyncio.to_thread(
            self._predict_sync,
            record,
            wrapper(),
            features,
            artefact.artefact_id,
        )

    async def predict_batch(
        self,
        model_name: str,
        artefacts: list[Artefact],
    ) -> list[MLPrediction]:
        """Run ``predict`` for each artefact (thread offloaded per item)."""
        if not artefacts:
            return []
        tasks = [self.predict(model_name, artefact) for artefact in artefacts]
        return list(await asyncio.gather(*tasks))

    async def get_available_models(self) -> list[str]:
        """Return distinct model names that have at least one registered version."""
        names = {item.model_name for item in self._registry.list_models()}
        return sorted(name for name in names if name in _MODEL_WRAPPERS)

    def has_trained_models(self) -> bool:
        """Return whether any supported model is registered (sync helper)."""
        names = {item.model_name for item in self._registry.list_models()}
        return any(name in _MODEL_WRAPPERS for name in names)

    async def score_artefact(self, artefact: Artefact) -> Optional[float]:
        """Return a normalised suspicion score in ``[0, 1]`` from the best available model."""
        available = set(await self.get_available_models())
        for model_name in _SCORE_MODEL_PRIORITY:
            if model_name not in available:
                continue
            try:
                prediction = await self.predict(model_name, artefact)
            except Exception:
                logger.exception("ML inference failed for %s", model_name)
                continue
            return prediction_to_score(prediction.prediction, prediction.confidence)
        return None

    def _predict_sync(
        self,
        record: Any,
        wrapper: Any,
        features: dict[str, Any],
        artefact_id: str,
    ) -> MLPrediction:
        estimator = self._registry.load_model(record.model_id)
        matrix = wrapper.preprocess([features])
        raw_prediction = estimator.predict(matrix)[0]
        confidence = _estimate_confidence(estimator, matrix, raw_prediction)
        importance = _feature_importance(estimator, wrapper.get_feature_names())
        return MLPrediction(
            artefact_id=artefact_id,
            model_name=record.model_name,
            model_version=record.version,
            prediction=_normalise_prediction(raw_prediction),
            confidence=confidence,
            feature_importance=importance,
        )


def prediction_to_score(prediction: Any, confidence: float) -> float:
    """Map a model prediction plus confidence to a suspicion score in ``[0, 1]``."""
    if isinstance(prediction, bool):
        return confidence if prediction else max(0.0, 1.0 - confidence)
    if isinstance(prediction, (int, float)) and not isinstance(prediction, bool):
        if prediction in (-1, 0, 1):
            if int(prediction) == -1:
                return confidence
            if int(prediction) == 1:
                return confidence
            return max(0.0, 1.0 - confidence)
        return max(0.0, min(1.0, float(prediction)))
    if isinstance(prediction, str):
        lowered = prediction.strip().lower()
        if lowered in {"true", "malicious", "suspicious", "positive", "1"}:
            return confidence
        if lowered in {"false", "benign", "normal", "negative", "0"}:
            return max(0.0, 1.0 - confidence)
    return max(0.0, min(1.0, confidence))


def _model_wrapper(model_name: str) -> type:
    wrapper = _MODEL_WRAPPERS.get(model_name)
    if wrapper is None:
        raise KeyError(f"Unsupported model name: {model_name!r}")
    return wrapper


def _normalise_prediction(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _estimate_confidence(estimator: Any, matrix: Any, prediction: Any) -> float:
    if hasattr(estimator, "predict_proba"):
        try:
            probabilities = estimator.predict_proba(matrix)[0]
            return float(max(probabilities))
        except (TypeError, ValueError, IndexError):
            pass
    if hasattr(estimator, "decision_function"):
        try:
            decision = float(estimator.decision_function(matrix)[0])
            return max(0.0, min(1.0, 1.0 / (1.0 + pow(2.718281828, -decision))))
        except (TypeError, ValueError, IndexError):
            pass
    if int(prediction) == -1:
        return 0.85
    return 0.5


def _feature_importance(estimator: Any, feature_names: list[str]) -> dict[str, float]:
    values: Any = None
    if hasattr(estimator, "feature_importances_"):
        values = getattr(estimator, "feature_importances_", None)
    elif hasattr(estimator, "coef_"):
        coef = getattr(estimator, "coef_", None)
        if coef is not None:
            try:
                values = abs(coef[0]) if len(getattr(coef, "shape", ())) > 1 else abs(coef)
            except (TypeError, ValueError, IndexError):
                values = None
    if values is None:
        return {}
    pairs = zip(feature_names, values, strict=False)
    ranked = sorted(((name, float(value)) for name, value in pairs), key=lambda item: -item[1])
    return {name: round(value, 6) for name, value in ranked[:10] if value > 0}
