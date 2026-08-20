"""Isolation Forest detector for anomalous forensic artefacts."""

from __future__ import annotations

from typing import Any

from dfat.ml.feature_engineering import ALL_FEATURE_NAMES, select_feature_matrix


class AnomalyDetector:
    """Isolation Forest for detecting anomalous artefacts.

    Uses all feature types. Unsupervised — no labels needed.
    """

    target_name = None

    def get_model(self) -> Any:
        """Return an unfitted sklearn Isolation Forest estimator."""
        from sklearn.ensemble import IsolationForest

        return IsolationForest(
            n_estimators=100,
            contamination="auto",
            random_state=42,
            n_jobs=1,
        )

    def get_feature_names(self) -> list[str]:
        """Return every engineered forensic feature name."""
        return list(ALL_FEATURE_NAMES)

    def get_hyperparameter_grid(self) -> dict[str, list[Any]]:
        """Return the Isolation Forest search grid."""
        return {
            "n_estimators": [50, 100, 200],
            "contamination": ["auto", 0.05, 0.1],
            "max_samples": ["auto", 0.8],
            "random_state": [42],
        }

    def preprocess(self, features: Any) -> Any:
        """Select the full forensic feature matrix for anomaly scoring."""
        matrix = select_feature_matrix(features, self.get_feature_names())
        try:
            import numpy as np

            return np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
        except ImportError:  # pragma: no cover - optional dependency
            return matrix
