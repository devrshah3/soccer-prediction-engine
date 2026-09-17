"""Chronological goalscorer evaluation with transparent baselines."""

import math
from collections import defaultdict
from typing import Any, cast

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, precision_score, recall_score

from soccer_engine.evaluation.metrics import bootstrap_interval
from soccer_engine.features.player import build_player_features
from soccer_engine.models.goals import PoissonGoalModel
from soccer_engine.models.scorers import POSITION_SCORING_PRIOR, predict_goalscorers


def _binary_calibration_error(actual: np.ndarray, predicted: np.ndarray, bins: int = 8) -> float:
    error = 0.0
    edges = np.linspace(0, 1, bins + 1)
    for lower, upper in zip(edges[:-1], edges[1:], strict=True):
        mask = (predicted > lower) & (predicted <= upper)
        if mask.any():
            error += float(mask.mean() * abs(actual[mask].mean() - predicted[mask].mean()))
    return error


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    as_matrix = np.column_stack([1 - predicted, predicted])
    log_ci = bootstrap_interval(
        lambda y, p: float(log_loss(y, p[:, 1], labels=[0, 1])),
        actual,
        as_matrix,
        samples=300,
    )
    brier_ci = bootstrap_interval(
        lambda y, p: float(brier_score_loss(y, p[:, 1])),
        actual,
        as_matrix,
        samples=300,
    )
    return {
        "log_loss": float(log_loss(actual, predicted, labels=[0, 1])),
        "log_loss_95_ci": list(log_ci),
        "brier_score": float(brier_score_loss(actual, predicted)),
        "brier_score_95_ci": list(brier_ci),
        "calibration_error": _binary_calibration_error(actual, predicted),
    }


def _baseline_probabilities(
    candidates: pd.DataFrame, team_xg: dict[str, float]
) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in candidates.itertuples(index=False):
        raw_row: Any = row
        minutes = float(raw_row.expected_minutes) / 90
        rate = max(float(raw_row.goals_per90), 0.01) * minutes
        result[str(row.player_id)] = rate
    for team_id, expected in team_xg.items():
        ids = candidates[candidates["team_id"] == team_id]["player_id"].astype(str).tolist()
        total = sum(result[item] for item in ids) or 1.0
        for player_id in ids:
            result[player_id] = 1 - math.exp(-expected * result[player_id] / total)
    return result


def evaluate_goalscorers(
    test_features: pd.DataFrame,
    matches: pd.DataFrame,
    player_matches: pd.DataFrame,
    goal_model: PoissonGoalModel,
) -> dict[str, Any]:
    """Backtest scorer probabilities using player history strictly before each kickoff."""

    if player_matches.empty:
        return {"available": False, "reason": "player-match data unavailable"}
    actual_values: list[int] = []
    probabilities: defaultdict[str, list[float]] = defaultdict(list)
    fixture_hits: dict[int, list[float]] = {1: [], 3: [], 5: [], 10: []}
    reliability_rows: defaultdict[str, list[tuple[int, float]]] = defaultdict(list)
    completeness_rows: defaultdict[str, list[tuple[int, float]]] = defaultdict(list)
    covered_actual_scorers = 0
    total_actual_scorers = 0
    evaluated_matches = 0
    match_lookup = matches.set_index("match_id")
    player_matches = player_matches.copy()
    player_matches["kickoff"] = pd.to_datetime(player_matches["kickoff"], utc=True)
    for feature in test_features.itertuples(index=False):
        fixture = cast(pd.Series, match_lookup.loc[feature.match_id])
        team_ids = [str(fixture["home_team_id"]), str(fixture["away_team_id"])]
        feature_frame = test_features[test_features["match_id"] == feature.match_id]
        home_xg, away_xg = goal_model.predict_expected_goals(feature_frame)
        team_xg = {team_ids[0]: float(home_xg[0]), team_ids[1]: float(away_xg[0])}
        candidates = build_player_features(
            player_matches, pd.Timestamp(fixture["kickoff"]), team_ids
        )
        predictions = predict_goalscorers(candidates, team_xg)
        if not predictions:
            continue
        evaluated_matches += 1
        historical = _baseline_probabilities(candidates, team_xg)
        position_weights = {}
        for raw_position_row in candidates.itertuples(index=False):
            position_row: Any = raw_position_row
            position_weights[str(position_row.player_id)] = (
                POSITION_SCORING_PRIOR.get(str(position_row.position), 0.11)
                * float(position_row.expected_minutes)
                / 90
            )
        actual_rows = player_matches[
            (player_matches["match_id"] == feature.match_id) & (player_matches["goals"] > 0)
        ]
        actual_ids = set(actual_rows["player_id"].astype(str))
        predicted_ids = {item.player_id for item in predictions}
        total_actual_scorers += len(actual_ids)
        covered_actual_scorers += len(actual_ids & predicted_ids)
        complete = "complete" if len(predicted_ids) >= 30 else "incomplete"
        for item in predictions:
            actual_label = int(item.player_id in actual_ids)
            actual_values.append(actual_label)
            probabilities["heuristic"].append(item.scoring_probability)
            probabilities["historical_rate"].append(historical[item.player_id])
            team_candidates = [p for p in predictions if p.team_id == item.team_id]
            proportional_xg = team_xg[item.team_id] / max(len(team_candidates), 1)
            probabilities["team_xg_proportional"].append(1 - math.exp(-proportional_xg))
            total_position = sum(position_weights[p.player_id] for p in team_candidates) or 1.0
            position_xg = team_xg[item.team_id] * position_weights[item.player_id] / total_position
            probabilities["position"].append(1 - math.exp(-position_xg))
            reliability_rows[item.reliability].append((actual_label, item.scoring_probability))
            completeness_rows[complete].append((actual_label, item.scoring_probability))
        ranked_ids = [item.player_id for item in predictions]
        for k in fixture_hits:
            fixture_hits[k].append(float(bool(actual_ids.intersection(ranked_ids[:k]))))
    if not actual_values:
        return {"available": False, "reason": "no candidate predictions in test period"}
    actual = np.asarray(actual_values)
    predicted = np.asarray(probabilities["heuristic"])
    thresholds = {}
    for threshold in (0.1, 0.2, 0.3):
        classified = predicted >= threshold
        thresholds[str(threshold)] = {
            "precision": float(precision_score(actual, classified, zero_division=0)),
            "recall": float(recall_score(actual, classified, zero_division=0)),
        }
    grouped = {}
    for name, rows in {**reliability_rows, **completeness_rows}.items():
        values = np.asarray(rows, dtype=float)
        grouped[name] = {"rows": len(rows), **_metrics(values[:, 0], values[:, 1])}
    return {
        "available": True,
        "held_out_matches": len(test_features),
        "evaluated_matches": evaluated_matches,
        "candidate_rows": len(predicted),
        "actual_scorer_candidate_coverage": (
            covered_actual_scorers / total_actual_scorers if total_actual_scorers else 1.0
        ),
        **_metrics(actual, predicted),
        "baselines": {
            name: _metrics(actual, np.asarray(values))
            for name, values in probabilities.items()
            if name != "heuristic"
        },
        "thresholds": thresholds,
        "top_k_hit_rate": {str(k): float(np.mean(values)) for k, values in fixture_hits.items()},
        "by_reliability_and_lineup_completeness": grouped,
        "warning": (
            "Player-level coverage is the four available WSL seasons, not worldwide coverage."
        ),
    }
