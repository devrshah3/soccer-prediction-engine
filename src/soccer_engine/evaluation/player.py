"""Chronological goalscorer evaluation."""

from typing import Any, cast

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, precision_score, recall_score

from soccer_engine.features.player import build_player_features
from soccer_engine.models.goals import PoissonGoalModel
from soccer_engine.models.scorers import predict_goalscorers


def _binary_calibration_error(actual: np.ndarray, predicted: np.ndarray, bins: int = 8) -> float:
    error = 0.0
    edges = np.linspace(0, 1, bins + 1)
    for lower, upper in zip(edges[:-1], edges[1:], strict=True):
        mask = (predicted > lower) & (predicted <= upper)
        if mask.any():
            error += float(mask.mean() * abs(actual[mask].mean() - predicted[mask].mean()))
    return error


def evaluate_goalscorers(
    test_features: pd.DataFrame,
    matches: pd.DataFrame,
    player_matches: pd.DataFrame,
    goal_model: PoissonGoalModel,
) -> dict[str, Any]:
    """Backtest scorer probabilities with player history strictly before each test kickoff."""

    if player_matches.empty:
        return {"available": False, "reason": "player-match data unavailable"}
    actual_values: list[int] = []
    probabilities: list[float] = []
    fixture_hits: dict[int, list[float]] = {1: [], 3: [], 5: []}
    covered_actual_scorers = 0
    total_actual_scorers = 0
    match_lookup = matches.set_index("match_id")
    player_matches = player_matches.copy()
    player_matches["kickoff"] = pd.to_datetime(player_matches["kickoff"], utc=True)
    for feature in test_features.itertuples(index=False):
        fixture = cast(pd.Series, match_lookup.loc[feature.match_id])
        team_ids = [str(fixture["home_team_id"]), str(fixture["away_team_id"])]
        feature_frame = test_features[test_features["match_id"] == feature.match_id]
        home_xg, away_xg = goal_model.predict_expected_goals(feature_frame)
        candidates = build_player_features(
            player_matches, pd.Timestamp(fixture["kickoff"]), team_ids
        )
        predictions = predict_goalscorers(
            candidates, {team_ids[0]: float(home_xg[0]), team_ids[1]: float(away_xg[0])}
        )
        actual_rows = player_matches[
            (player_matches["match_id"] == feature.match_id) & (player_matches["goals"] > 0)
        ]
        actual_ids = set(actual_rows["player_id"].astype(str))
        predicted_ids = {item.player_id for item in predictions}
        total_actual_scorers += len(actual_ids)
        covered_actual_scorers += len(actual_ids & predicted_ids)
        for item in predictions:
            actual_values.append(int(item.player_id in actual_ids))
            probabilities.append(item.scoring_probability)
        ranked_ids = [item.player_id for item in predictions]
        for k in fixture_hits:
            fixture_hits[k].append(float(bool(actual_ids.intersection(ranked_ids[:k]))))
    if not probabilities:
        return {"available": False, "reason": "no candidate predictions in test period"}
    actual = np.asarray(actual_values)
    predicted = np.asarray(probabilities)
    thresholds = {}
    for threshold in (0.1, 0.2, 0.3):
        classified = predicted >= threshold
        thresholds[str(threshold)] = {
            "precision": float(precision_score(actual, classified, zero_division=0)),
            "recall": float(recall_score(actual, classified, zero_division=0)),
        }
    return {
        "available": True,
        "candidate_rows": len(predicted),
        "actual_scorer_candidate_coverage": (
            covered_actual_scorers / total_actual_scorers if total_actual_scorers else 1.0
        ),
        "log_loss": float(log_loss(actual, predicted, labels=[0, 1])),
        "brier_score": float(brier_score_loss(actual, predicted)),
        "calibration_error": _binary_calibration_error(actual, predicted),
        "thresholds": thresholds,
        "top_k_hit_rate": {str(k): float(np.mean(values)) for k, values in fixture_hits.items()},
        "warning": "Small single-season holdout; scorer outcomes are sparse and noisy.",
    }
