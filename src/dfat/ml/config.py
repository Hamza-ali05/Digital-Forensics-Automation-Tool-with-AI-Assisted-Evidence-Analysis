"""Configuration for the ML lifecycle extension package."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class MLSettings(BaseModel):
    """Local ML training, evaluation, and experiment-tracking settings."""

    models_dir: Path = Path("data/ml/models")
    experiments_dir: Path = Path("data/ml/experiments")
    auto_retrain: bool = True
    retrain_threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    test_split: float = Field(default=0.2, gt=0.0, lt=1.0)
    validation_split: float = Field(default=0.1, ge=0.0, lt=1.0)
    random_seed: int = 42
    max_training_time_seconds: int = Field(default=300, ge=1)
    cross_validation_folds: int = Field(default=5, ge=2)
