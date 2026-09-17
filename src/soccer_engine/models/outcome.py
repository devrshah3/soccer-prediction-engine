"""Calibrated multiclass outcome models and explicit baselines."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from soccer_engine.evaluation.metrics import CLASS_ORDER
from soccer_engine.features.team import FEATURE_COLUMNS


def _ordered_probabilities(classes: np.ndarray, probabilities: np.ndarray) -> np.ndarray:
    ordered = np.zeros((len(probabilities), len(CLASS_ORDER)))
    for source_index, label in enumerate(classes):
        ordered[:, int(np.where(label == CLASS_ORDER)[0][0])] = probabilities[:, source_index]
    return np.asarray(ordered / ordered.sum(axis=1, keepdims=True))


@dataclass
class MostCommonBaseline:
    """Smoothed most-common-class baseline with finite probabilistic loss."""

    probabilities: np.ndarray | None = None

    def fit(self, y: pd.Series) -> "MostCommonBaseline":
        majority = str(y.value_counts().idxmax())
        self.probabilities = np.full(len(CLASS_ORDER), 0.01)
        self.probabilities[int(np.where(majority == CLASS_ORDER)[0][0])] = 0.98
        return self

    def predict_proba(self, rows: int) -> np.ndarray:
        if self.probabilities is None:
            raise RuntimeError("baseline is not fitted")
        return np.tile(self.probabilities, (rows, 1))


class OutcomeModel:
    """Multinomial classifier with time-ordered sigmoid calibration."""

    def __init__(self, kind: str = "logistic", random_seed: int = 42):
        if kind == "logistic":
            estimator = Pipeline(
                [
                    ("impute", SimpleImputer(strategy="median")),
                    ("scale", StandardScaler()),
                    ("model", LogisticRegression(max_iter=2000, random_state=random_seed)),
                ]
            )
        elif kind == "hist_gradient_boosting":
            estimator = Pipeline(
                [
                    ("impute", SimpleImputer(strategy="median")),
                    (
                        "model",
                        HistGradientBoostingClassifier(
                            max_iter=200, learning_rate=0.05, random_state=random_seed
                        ),
                    ),
                ]
            )
        else:
            raise ValueError(f"unknown outcome model kind: {kind}")
        self.kind = kind
        self.estimator = estimator
        self.calibrator: CalibratedClassifierCV | None = None

    def fit(self, frame: pd.DataFrame) -> "OutcomeModel":
        """Fit using time-respecting cross-validation folds for calibration."""

        training = frame.dropna(subset=["outcome"]).sort_values(["kickoff", "match_id"])
        if len(training) < 30:
            raise ValueError("at least 30 finished matches are required")
        # Each calibration fold is later than training; no future row calibrates an earlier one.
        boundaries = [int(len(training) * ratio) for ratio in (0.55, 0.7, 0.85, 1.0)]
        cv = []
        for left, right in zip(boundaries[:-1], boundaries[1:], strict=True):
            cv.append((np.arange(left), np.arange(left, right)))
        self.calibrator = CalibratedClassifierCV(self.estimator, method="sigmoid", cv=cv)
        self.calibrator.fit(training[FEATURE_COLUMNS], training["outcome"])
        return self

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        if self.calibrator is None:
            raise RuntimeError("outcome model is not fitted")
        probabilities = self.calibrator.predict_proba(frame[FEATURE_COLUMNS])
        return _ordered_probabilities(self.calibrator.classes_, probabilities)
