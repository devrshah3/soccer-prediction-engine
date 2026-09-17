"""Independent Poisson goal baseline and scoreline distribution."""

import math

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from soccer_engine.features.team import FEATURE_COLUMNS


def poisson_probability(goals: int, expected_goals: float) -> float:
    return math.exp(-expected_goals) * expected_goals**goals / math.factorial(goals)


class PoissonGoalModel:
    """Two regularized Poisson regressions for home and away goals."""

    def __init__(self, max_goals: int = 8):
        self.max_goals = max_goals
        self.home_model = self._pipeline()
        self.away_model = self._pipeline()

    @staticmethod
    def _pipeline() -> Pipeline:
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", PoissonRegressor(alpha=1.0, max_iter=1000)),
            ]
        )

    def fit(self, frame: pd.DataFrame) -> "PoissonGoalModel":
        training = frame.dropna(subset=["home_score", "away_score"])
        self.home_model.fit(training[FEATURE_COLUMNS], training["home_score"])
        self.away_model.fit(training[FEATURE_COLUMNS], training["away_score"])
        return self

    def predict_expected_goals(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        home = np.clip(self.home_model.predict(frame[FEATURE_COLUMNS]), 0.05, 8.0)
        away = np.clip(self.away_model.predict(frame[FEATURE_COLUMNS]), 0.05, 8.0)
        return home, away

    def distribution(self, home_xg: float, away_xg: float) -> np.ndarray:
        """Return a normalized joint score distribution including a tail bucket."""

        home = np.array([poisson_probability(i, home_xg) for i in range(self.max_goals + 1)])
        away = np.array([poisson_probability(i, away_xg) for i in range(self.max_goals + 1)])
        matrix = np.outer(home, away)
        return np.asarray(matrix / matrix.sum())
