"""Logistic Regression model for IOC likelihood prediction."""

from __future__ import annotations

from typing import Any

from dfat.ml.feature_engineering import ALL_FEATURE_NAMES, select_feature_matrix


class IOCPredictor:
    """Logistic Regression for predicting IOC likelihood.

    Uses combined features. Target: ``is_ioc`` (bool).
    """

    target_name = "is_ioc"

    def __init__(self) -> None:
        pass

    def get_model(self) -> Any:
        """Return an unfitted sklearn Logistic Regression estimator."""
        from sklearn.linear_model import LogisticRegression

        return LogisticRegression(
            C=1.0,
            max_iter=500,
            solver="lbfgs",
            random_state=42,
        )

    def get_feature_names(self) -> list[str]:
        """Return the combined forensic feature names."""
        return list(ALL_FEATURE_NAMES)

    def get_hyperparameter_grid(self) -> dict[str, list[Any]]:
        """Return the Logistic Regression search grid."""
        return {
            "C": [0.1, 1.0, 10.0],
            "max_iter": [500],
            "solver": ["lbfgs"],
            "random_state": [42],
        }

    def preprocess(self, features: Any) -> Any:
        """Select combined features for inference or training."""
        return select_feature_matrix(features, self.get_feature_names())
