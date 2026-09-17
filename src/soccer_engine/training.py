"""End-to-end training and honest out-of-time model selection."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    mean_absolute_error,
    mean_poisson_deviance,
    mean_squared_error,
)

from soccer_engine.evaluation.metrics import (
    CLASS_ORDER,
    bootstrap_interval,
    outcome_metrics,
)
from soccer_engine.evaluation.player import evaluate_goalscorers
from soccer_engine.evaluation.splits import chronological_holdout
from soccer_engine.features.team import build_match_features
from soccer_engine.models.goals import PoissonGoalModel
from soccer_engine.models.outcome import MostCommonBaseline, OutcomeModel

MODEL_VERSION = "0.2.0"


@dataclass
class ModelBundle:
    """Serializable champion models plus provenance metadata."""

    outcome_model: OutcomeModel
    goal_model: PoissonGoalModel
    trained_at: datetime
    training_cutoff: datetime
    data_source: str
    version: str = MODEL_VERSION

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: Path) -> "ModelBundle":
        value: ModelBundle = joblib.load(path)
        return value


def elo_baseline(frame: pd.DataFrame) -> np.ndarray:
    """Turn pre-match Elo difference into a conservative three-way probability."""

    delta = frame["delta_elo"].to_numpy() + 65.0 * frame["home_advantage"].to_numpy()
    decisive_home = 1 / (1 + np.power(10.0, -delta / 400))
    draw = np.clip(0.28 - np.abs(delta) / 3000, 0.16, 0.28)
    home = (1 - draw) * decisive_home
    away = (1 - draw) * (1 - decisive_home)
    return np.column_stack([away, draw, home])


def home_advantage_baseline(frame: pd.DataFrame) -> np.ndarray:
    """Simple fixed heuristic that removes home advantage at neutral venues."""

    probabilities = np.tile(np.array([0.27, 0.27, 0.46]), (len(frame), 1))
    neutral = frame["neutral_venue"].to_numpy().astype(bool)
    probabilities[neutral] = np.array([0.365, 0.27, 0.365])
    return probabilities


def _goal_metrics(frame: pd.DataFrame, goal_model: PoissonGoalModel) -> dict[str, float]:
    home, away = goal_model.predict_expected_goals(frame)
    actual_home = frame["home_score"].to_numpy(dtype=float)
    actual_away = frame["away_score"].to_numpy(dtype=float)
    actual = np.concatenate([actual_home, actual_away])
    predicted = np.concatenate([home, away])
    scoreline_probabilities = []
    over_probabilities = []
    over_actual = []
    for home_goals, away_goals, home_xg, away_xg in zip(
        actual_home, actual_away, home, away, strict=True
    ):
        distribution = goal_model.distribution(float(home_xg), float(away_xg))
        home_index = min(int(home_goals), goal_model.max_goals)
        away_index = min(int(away_goals), goal_model.max_goals)
        scoreline_probabilities.append(float(distribution[home_index, away_index]))
        totals = np.add.outer(np.arange(distribution.shape[0]), np.arange(distribution.shape[1]))
        over_probabilities.append(float(distribution[totals >= 3].sum()))
        over_actual.append(float(home_goals + away_goals >= 3))
    return {
        "mae": float(mean_absolute_error(actual, predicted)),
        "rmse": float(mean_squared_error(actual, predicted) ** 0.5),
        "poisson_deviance": float(mean_poisson_deviance(actual, np.clip(predicted, 1e-6, None))),
        "scoreline_negative_log_likelihood": float(
            -np.mean(np.log(np.clip(scoreline_probabilities, 1e-12, None)))
        ),
        "over_2_5_brier_score": float(
            np.mean((np.asarray(over_probabilities) - np.asarray(over_actual)) ** 2)
        ),
    }


def _class_diagnostics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    predicted = CLASS_ORDER[np.argmax(probabilities, axis=1)]
    return {
        "class_order": CLASS_ORDER.tolist(),
        "confusion_matrix": confusion_matrix(y_true, predicted, labels=CLASS_ORDER).tolist(),
        "per_class": classification_report(
            y_true,
            predicted,
            labels=CLASS_ORDER,
            output_dict=True,
            zero_division=0,
        ),
    }


def train_and_evaluate(
    matches: pd.DataFrame,
    model_path: Path = Path("models/champion.joblib"),
    report_path: Path = Path("reports/evaluation.json"),
    player_matches: pd.DataFrame | None = None,
) -> tuple[ModelBundle, dict[str, Any]]:
    """Select on validation, refit through validation, and report untouched test metrics."""

    features = build_match_features(matches).dropna(subset=["outcome"])
    train, validation, test = chronological_holdout(features)
    if min(len(train), len(validation), len(test)) < 10:
        raise ValueError("dataset is too small for reliable train/validation/test partitions")

    common = MostCommonBaseline().fit(train["outcome"])
    validation_candidates: dict[str, np.ndarray] = {
        "most_common": common.predict_proba(len(validation)),
        "home_advantage": home_advantage_baseline(validation),
        "elo": elo_baseline(validation),
    }
    fitted: dict[str, OutcomeModel] = {}
    for kind in ("logistic", "hist_gradient_boosting"):
        model = OutcomeModel(kind=kind).fit(train)
        fitted[kind] = model
        validation_candidates[kind] = model.predict_proba(validation)

    validation_results = {
        name: outcome_metrics(validation["outcome"].to_numpy(), probabilities)
        for name, probabilities in validation_candidates.items()
    }
    trainable_names = list(fitted)
    champion_name = min(trainable_names, key=lambda name: validation_results[name]["log_loss"])

    development = pd.concat([train, validation]).sort_values(["kickoff", "match_id"])
    champion = OutcomeModel(kind=champion_name).fit(development)
    goal_model = PoissonGoalModel().fit(development)
    test_probabilities = champion.predict_proba(test)
    test_metrics = outcome_metrics(test["outcome"].to_numpy(), test_probabilities)
    log_loss_interval = bootstrap_interval(
        lambda actual, predicted: outcome_metrics(actual, predicted)["log_loss"],
        test["outcome"].to_numpy(),
        test_probabilities,
        samples=500,
    )
    baseline_test = {
        "most_common": outcome_metrics(test["outcome"].to_numpy(), common.predict_proba(len(test))),
        "home_advantage": outcome_metrics(
            test["outcome"].to_numpy(), home_advantage_baseline(test)
        ),
        "elo": outcome_metrics(test["outcome"].to_numpy(), elo_baseline(test)),
    }
    trained_at = datetime.now(UTC)
    bundle = ModelBundle(
        outcome_model=champion,
        goal_model=goal_model,
        trained_at=trained_at,
        training_cutoff=pd.Timestamp(development["kickoff"].max()).to_pydatetime(),
        data_source="StatsBomb Open Data",
    )
    bundle.save(model_path)
    report: dict[str, Any] = {
        "model_version": bundle.version,
        "generated_at": trained_at.isoformat(),
        "dataset": {
            "source": bundle.data_source,
            "matches": len(features),
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
            "train_period": [str(train["kickoff"].min()), str(train["kickoff"].max())],
            "validation_period": [
                str(validation["kickoff"].min()),
                str(validation["kickoff"].max()),
            ],
            "test_period": [str(test["kickoff"].min()), str(test["kickoff"].max())],
        },
        "selection_metric": "validation log_loss (lower is better)",
        "champion": champion_name,
        "validation": validation_results,
        "test": {
            "champion": test_metrics,
            "diagnostics": _class_diagnostics(test["outcome"].to_numpy(), test_probabilities),
            "champion_log_loss_95_ci": list(log_loss_interval),
            "baselines": baseline_test,
            "goals": _goal_metrics(test, goal_model),
            "goalscorers": evaluate_goalscorers(
                test,
                matches,
                player_matches if player_matches is not None else pd.DataFrame(),
                goal_model,
            ),
        },
        "warning": (
            "Single-season sample results are illustrative, not evidence of global performance."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    return bundle, report
