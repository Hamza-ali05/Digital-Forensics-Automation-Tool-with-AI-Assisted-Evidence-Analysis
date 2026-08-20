"""Train sklearn classifiers with optional grid-search CV and experiment logging."""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from dfat.ml.config import MLSettings
from dfat.ml.dataset_builder import TrainingDataset
from dfat.ml.experiment_tracker import ExperimentTracker

logger = logging.getLogger(__name__)

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class TrainingError(RuntimeError):
    """Raised when model training cannot run."""


class TrainedModel(BaseModel):
    """Serialized trained classifier plus evaluation metadata."""

    model_config = ConfigDict(
        frozen=False,
        str_strip_whitespace=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    model_id: str = Field(default_factory=lambda: str(uuid4()))
    model_name: str
    model_path: Path
    version: str
    hyperparameters: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    training_dataset: str
    trained_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    feature_names: list[str] = Field(default_factory=list)


class ModelTrainer:
    """Train, evaluate, and persist sklearn models with experiment tracking."""

    def __init__(self, experiment_tracker: ExperimentTracker, ml_settings: MLSettings) -> None:
        self._tracker = experiment_tracker
        self._settings = ml_settings

    async def train(
        self,
        model_class: type,
        training_data: TrainingDataset,
        hyperparameters: Optional[dict] = None,
    ) -> TrainedModel:
        """Train ``model_class`` on ``training_data`` and persist the fitted model."""
        _require_sklearn()
        wrapper = _model_wrapper(model_class)
        sklearn_class = wrapper.get_model().__class__ if wrapper is not None else model_class
        model_name = model_class.__name__ if wrapper is not None else _model_display_name(
            model_class,
            training_data.name,
        )
        experiment_id = self._tracker.start_experiment(
            model_name=model_name,
            dataset_name=training_data.name,
            hyperparameters=dict(hyperparameters or {}),
        )
        try:
            estimator, used_params, metrics, model_path, version, feature_names = await asyncio.to_thread(
                self._train_sync,
                sklearn_class,
                training_data,
                hyperparameters,
                model_name,
                wrapper,
            )
        except Exception:
            logger.exception("Training failed for %s", model_name)
            raise

        for metric_name, value in metrics.items():
            self._tracker.log_metric(experiment_id, metric_name, float(value))
        self._tracker.log_artifact(experiment_id, model_path)
        self._tracker.complete_experiment(experiment_id, metrics)

        trained = TrainedModel(
            model_name=model_name,
            model_path=model_path,
            version=version,
            hyperparameters=used_params,
            metrics=metrics,
            training_dataset=training_data.name,
            feature_names=feature_names,
        )
        logger.debug("Trained %s %s metrics=%s", model_name, estimator.__class__.__name__, metrics)
        return trained

    def _train_sync(
        self,
        model_class: type,
        training_data: TrainingDataset,
        hyperparameters: Optional[dict],
        model_name: str,
        wrapper: Any = None,
    ) -> tuple[Any, dict[str, Any], dict[str, float], Path, str]:
        from joblib import dump

        features, labels = _as_xy(training_data)
        if wrapper is not None:
            features = wrapper.preprocess(features)
        train_idx = list(training_data.train_indices) or list(range(len(labels)))
        val_idx = list(training_data.val_indices)
        x_train, y_train = features[train_idx], labels[train_idx]
        if val_idx:
            x_eval, y_eval = features[val_idx], labels[val_idx]
        else:
            x_eval, y_eval = x_train, y_train

        if hyperparameters is None:
            used_params = self._grid_search(
                model_class,
                x_train,
                y_train,
                wrapper=wrapper,
            )
        else:
            used_params = dict(hyperparameters)

        estimator = _instantiate(model_class, used_params, self._settings.random_seed)
        fit_args = (x_train,) if model_class.__name__ == "IsolationForest" else (x_train, y_train)
        estimator.fit(*fit_args)
        predictions = estimator.predict(x_eval)
        metrics = _classification_metrics(y_eval, predictions)

        version = _next_version(self._settings.models_dir, model_name)
        model_path = _model_file(self._settings.models_dir, model_name, version)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        dump(estimator, model_path)
        feature_names = (
            wrapper.get_feature_names()
            if wrapper is not None
            else list(training_data.feature_names)
        )
        return estimator, used_params, metrics, model_path, version, feature_names

    def _grid_search(
        self,
        model_class: type,
        features: Any,
        labels: Any,
        *,
        wrapper: Any = None,
    ) -> dict[str, Any]:
        from sklearn.model_selection import ParameterGrid, StratifiedKFold, cross_val_score

        grid = (
            wrapper.get_hyperparameter_grid()
            if wrapper is not None
            else _default_grid(model_class, self._settings.random_seed)
        )
        fallback = _instantiate_params(model_class, {}, self._settings.random_seed)
        if not grid:
            return fallback

        n_splits = _safe_n_splits(labels, self._settings.cross_validation_folds)
        if n_splits < 2:
            return next(iter(ParameterGrid(grid)), fallback)

        splitter = StratifiedKFold(
            n_splits=n_splits,
            shuffle=True,
            random_state=self._settings.random_seed,
        )
        deadline = time.monotonic() + self._settings.max_training_time_seconds
        best_score = float("-inf")
        best_params: dict[str, Any] = fallback

        for params in ParameterGrid(grid):
            if time.monotonic() >= deadline:
                logger.info("Grid search stopped after max_training_time_seconds")
                break
            candidate = _instantiate(model_class, params, self._settings.random_seed)
            try:
                scores = cross_val_score(
                    candidate,
                    features,
                    labels,
                    cv=splitter,
                    scoring="f1_weighted",
                )
            except ValueError:
                continue
            mean_score = float(scores.mean()) if len(scores) else float("-inf")
            if mean_score > best_score:
                best_score = mean_score
                best_params = dict(params)
        return best_params


def _model_wrapper(model_class: type) -> Any:
    if hasattr(model_class, "get_model") and callable(model_class.get_model):
        return model_class()
    return None


def _require_sklearn() -> None:
    try:
        import joblib  # noqa: F401
        import sklearn  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise TrainingError(
            "scikit-learn and joblib are required for model training. "
            "Install with: pip install scikit-learn joblib"
        ) from exc


def _model_display_name(model_class: type, dataset_name: str) -> str:
    class_name = getattr(model_class, "__name__", None)
    if isinstance(class_name, str) and class_name:
        return class_name
    return dataset_name or "forensic_model"


def _safe_name(name: str) -> str:
    return _UNSAFE_NAME.sub("_", name.strip()) or "unnamed_model"


def _model_file(models_dir: Path, model_name: str, version: str) -> Path:
    return Path(models_dir) / _safe_name(model_name) / version / "model.joblib"


def _next_version(models_dir: Path, model_name: str) -> str:
    directory = Path(models_dir) / _safe_name(model_name)
    if not directory.exists():
        return "1"
    versions: list[int] = []
    for child in directory.iterdir():
        if child.is_dir() and child.name.isdigit():
            versions.append(int(child.name))
    return str(max(versions, default=0) + 1)


def _as_xy(training_data: TrainingDataset) -> tuple[Any, Any]:
    import numpy as np

    features = np.asarray(training_data.feature_matrix, dtype=float)
    labels = np.asarray(training_data.labels)
    if features.ndim != 2 or len(features) == 0:
        raise TrainingError("Training dataset feature_matrix must be a non-empty 2D array")
    if len(labels) != len(features):
        raise TrainingError("Training dataset labels must align with feature_matrix rows")
    return features, labels


def _safe_n_splits(labels: Any, requested: int) -> int:
    counts = Counter(int(label) for label in labels)
    if not counts:
        return 0
    return max(0, min(requested, len(labels), min(counts.values())))


def _classification_metrics(y_true: Any, y_pred: Any) -> dict[str, float]:
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, average="weighted", zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, average="weighted", zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
    }


def _default_grid(model_class: type, seed: int) -> dict[str, list[Any]]:
    name = getattr(model_class, "__name__", "")
    grids: dict[str, dict[str, list[Any]]] = {
        "RandomForestClassifier": {
            "n_estimators": [50, 100],
            "max_depth": [5, 10, None],
            "random_state": [seed],
        },
        "GradientBoostingClassifier": {
            "n_estimators": [50, 100],
            "learning_rate": [0.05, 0.1],
            "random_state": [seed],
        },
        "LogisticRegression": {
            "C": [0.1, 1.0, 10.0],
            "max_iter": [200],
            "random_state": [seed],
        },
        "DecisionTreeClassifier": {
            "max_depth": [3, 5, 10, None],
            "random_state": [seed],
        },
        "SVC": {
            "C": [0.5, 1.0],
            "kernel": ["linear", "rbf"],
        },
    }
    return grids.get(name, {})


def _instantiate(model_class: type, params: dict[str, Any], seed: int) -> Any:
    return model_class(**_instantiate_params(model_class, params, seed))


def _instantiate_params(model_class: type, params: dict[str, Any], seed: int) -> dict[str, Any]:
    merged = dict(params)
    merged.setdefault("random_state", seed)
    accepted = _accepted_kwargs(model_class)
    if not accepted:
        return dict(params)
    return {key: value for key, value in merged.items() if key in accepted}


def _accepted_kwargs(model_class: type) -> set[str]:
    try:
        signature = inspect.signature(model_class.__init__)
    except (TypeError, ValueError):
        return set()
    names = set(signature.parameters)
    names.discard("self")
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return set()
    return names
