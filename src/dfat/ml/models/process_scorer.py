"""Gradient-boosted process suspicion scorer."""

from __future__ import annotations

from typing import Any

from dfat.ml.feature_engineering import (
    NETWORK_FEATURE_NAMES,
    PROCESS_FEATURE_NAMES,
    select_feature_matrix,
)


class ProcessSuspicionScorer:
    """Gradient Boosted classifier for process suspicion scoring.

    Uses process features plus network features. Target: ``suspicion_level``.
    """

    target_name = "suspicion_level"

    def get_model(self) -> Any:
        """Return an unfitted sklearn Gradient Boosting estimator."""
        from sklearn.ensemble import GradientBoostingClassifier

        return GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=3,
            random_state=42,
        )

    def get_feature_names(self) -> list[str]:
        """Return process and network feature names used by this model."""
        return list(PROCESS_FEATURE_NAMES + NETWORK_FEATURE_NAMES)

    def get_hyperparameter_grid(self) -> dict[str, list[Any]]:
        """Return the Gradient Boosting search grid."""
        return {
            "n_estimators": [50, 100, 150],
            "learning_rate": [0.05, 0.1, 0.2],
            "max_depth": [2, 3, 5],
            "random_state": [42],
        }

    def preprocess(self, features: Any) -> Any:
        """Select and coerce the process-scorer feature matrix."""
        return select_feature_matrix(features, self.get_feature_names())
