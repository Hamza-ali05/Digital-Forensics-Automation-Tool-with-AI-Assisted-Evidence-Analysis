"""Local ML lifecycle utilities for DFAT."""

from dfat.ml.config import MLSettings

__all__ = ["MLSettings"]


def __getattr__(name: str):
    """Lazy exports to avoid import cycles during application startup."""
    exports = {
        "AnomalyDetector": "dfat.ml.models",
        "AutoRetrainer": "dfat.ml.retrainer",
        "EmptyTrainingDatasetError": "dfat.ml.dataset_builder",
        "ExperimentNotFoundError": "dfat.ml.experiment_tracker",
        "ExperimentRecord": "dfat.ml.experiment_tracker",
        "ExperimentTracker": "dfat.ml.experiment_tracker",
        "ForensicFeatureExtractor": "dfat.ml.feature_engineering",
        "IOCPredictor": "dfat.ml.models",
        "MLDatasetBuilder": "dfat.ml.dataset_builder",
        "MLPrediction": "dfat.ml.predictor",
        "MLPredictor": "dfat.ml.predictor",
        "MalwareClassifier": "dfat.ml.models",
        "ModelRegistry": "dfat.ml.model_registry",
        "ModelTrainer": "dfat.ml.trainer",
        "ProcessSuspicionScorer": "dfat.ml.models",
        "TrainedModel": "dfat.ml.trainer",
        "TrainingDataset": "dfat.ml.dataset_builder",
        "TrainingError": "dfat.ml.trainer",
    }
    if name not in exports:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name = exports[name]
    import importlib

    module = importlib.import_module(module_name)
    return getattr(module, name)
