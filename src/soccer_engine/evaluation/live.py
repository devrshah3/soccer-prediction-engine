"""Offline chronological evaluation for live-state probability updates."""

import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd

from soccer_engine.evaluation.metrics import outcome_metrics
from soccer_engine.live.replay import StatsBombReplay
from soccer_engine.live.schemas import LiveEventType


def _score_poisson(
    home_score: int, away_score: int, home_rate: float, away_rate: float
) -> np.ndarray:
    probabilities = np.zeros(3)
    for home in range(8):
        for away in range(8):
            probability = (
                math.exp(-home_rate)
                * home_rate**home
                / math.factorial(home)
                * math.exp(-away_rate)
                * away_rate**away
                / math.factorial(away)
            )
            final_home, final_away = home_score + home, away_score + away
            index = 2 if final_home > final_away else 0 if final_home < final_away else 1
            probabilities[index] += probability
    return cast(np.ndarray, probabilities / probabilities.sum())


def _binary_ece(actual: np.ndarray, predicted: np.ndarray, bins: int = 10) -> float:
    error = 0.0
    for lower, upper in zip(
        np.linspace(0, 1, bins + 1)[:-1], np.linspace(0, 1, bins + 1)[1:], strict=True
    ):
        mask = (predicted > lower) & (predicted <= upper)
        if mask.any():
            error += float(mask.mean() * abs(actual[mask].mean() - predicted[mask].mean()))
    return error


def _cluster_interval(
    actual: np.ndarray,
    predicted: np.ndarray,
    match_ids: np.ndarray,
    metric: Any,
) -> list[float]:
    """Bootstrap whole matches so correlated in-match snapshots remain together."""

    generator = np.random.default_rng(42)
    unique = np.unique(match_ids)
    values = []
    for _ in range(300):
        sampled = generator.choice(unique, size=len(unique), replace=True)
        indices = np.concatenate([np.flatnonzero(match_ids == match_id) for match_id in sampled])
        values.append(float(metric(actual[indices], predicted[indices])))
    return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]


def _binary_report(
    actual: np.ndarray, predicted: np.ndarray, match_ids: np.ndarray
) -> dict[str, Any]:
    brier = float(np.mean((actual - predicted) ** 2))
    return {
        "brier_score": brier,
        "brier_95_ci": _cluster_interval(
            actual,
            predicted,
            match_ids,
            lambda observed, forecast: np.mean((observed - forecast) ** 2),
        ),
        "calibration_error": _binary_ece(actual, predicted),
    }


def evaluate_live_replays(
    replay: StatsBombReplay,
    limit: int = 50,
    interval_minutes: int = 10,
    output: Path = Path("reports/live_replay_evaluation.json"),
) -> dict[str, Any]:
    """Evaluate the latest cached matches chronologically; model state sees only revealed events."""

    matches = replay.engine.service.matches().copy()
    event_dir = replay.provider.cache_dir / "events"
    available = {path.stem for path in event_dir.glob("*.json")}
    matches = matches[matches["provider_match_id"].astype(str).isin(available)]
    matches["kickoff"] = pd.to_datetime(matches["kickoff"], utc=True)
    matches = matches.sort_values("kickoff").tail(limit)
    actual_outcomes: list[str] = []
    predictions: defaultdict[str, list[np.ndarray]] = defaultdict(list)
    window_actual: defaultdict[int, list[int]] = defaultdict(list)
    window_predicted: defaultdict[str, defaultdict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    next_team_actual: list[str] = []
    next_team_predicted: list[str] = []
    groups: defaultdict[str, list[int]] = defaultdict(list)
    snapshot_match_ids: list[str] = []
    snapshot_index = 0
    replayed_matches = 0
    for fixture in matches.itertuples(index=False):
        try:
            result = replay.run(str(fixture.match_id), interval_minutes)
            normalized = replay.normalize(str(fixture.match_id), str(fixture.provider_match_id))
            prematch = replay.engine.prematch(str(fixture.match_id))
        except (FileNotFoundError, KeyError, ValueError):
            continue
        replayed_matches += 1
        goals = [event for event in normalized if event.event_type == LiveEventType.GOAL]
        raw_fixture: Any = fixture
        final_outcome = (
            "home"
            if int(raw_fixture.home_score) > int(raw_fixture.away_score)
            else "away"
            if int(raw_fixture.home_score) < int(raw_fixture.away_score)
            else "draw"
        )
        static = np.array(
            [prematch.outcome.away_win, prematch.outcome.draw, prematch.outcome.home_win]
        )
        for snapshot in result.snapshots:
            live = snapshot.prediction
            minute = snapshot.minute
            future_goals = [goal for goal in goals if goal.minute > minute]
            actual_outcomes.append(final_outcome)
            snapshot_match_ids.append(str(fixture.match_id))
            live_array = np.array([live.outcome.away_win, live.outcome.draw, live.outcome.home_win])
            predictions["live_event_model"].append(live_array)
            predictions["static_prematch"].append(static)
            remaining = max(0.0, (95 - minute) / 95)
            score_poisson = _score_poisson(
                live.home_score,
                live.away_score,
                prematch.expected_home_goals * remaining,
                prematch.expected_away_goals * remaining,
            )
            predictions["current_score_poisson"].append(score_poisson)
            decay_weight = min(minute / 95, 1.0)
            state_target = np.zeros(3)
            state_index = (
                2
                if live.home_score > live.away_score
                else 0
                if live.home_score < live.away_score
                else 1
            )
            state_target[state_index] = 1
            decay = (1 - decay_weight) * static + decay_weight * state_target
            predictions["time_decay_only"].append(decay / decay.sum())
            tilt = np.array(
                [
                    -0.12 * live.home_pressure + 0.12 * live.away_pressure,
                    0,
                    0.12 * live.home_pressure - 0.12 * live.away_pressure,
                ]
            )
            heuristic = np.clip(score_poisson + tilt, 1e-6, None)
            predictions["event_count_heuristic"].append(heuristic / heuristic.sum())
            per_minute_static = (prematch.expected_home_goals + prematch.expected_away_goals) / 95
            per_minute_pace = per_minute_static * live.match_pace
            for window, live_probability in (
                (5, live.goal_within_5_minutes),
                (10, live.goal_within_10_minutes),
                (15, live.goal_within_15_minutes),
            ):
                actual = int(any(goal.minute <= minute + window for goal in future_goals))
                window_actual[window].append(actual)
                window_predicted["live_event_model"][window].append(live_probability)
                window_predicted["time_decay_only"][window].append(
                    1 - math.exp(-per_minute_static * min(window, 95 - minute))
                )
                window_predicted["event_count_heuristic"][window].append(
                    1 - math.exp(-per_minute_pace * min(window, 95 - minute))
                )
            if future_goals:
                next_team_actual.append(str(future_goals[0].team_id))
                next_team_predicted.append(
                    str(fixture.home_team_id)
                    if live.next_home_goal_probability >= live.next_away_goal_probability
                    else str(fixture.away_team_id)
                )
            period = "0-30" if minute <= 30 else "31-60" if minute <= 60 else "61+"
            groups[f"period:{period}"].append(snapshot_index)
            groups[f"score:{live.home_score}-{live.away_score}"].append(snapshot_index)
            groups[f"competition:{fixture.competition_name}"].append(snapshot_index)
            groups[f"reliability:{live.reliability}"].append(snapshot_index)
            red_before = any(
                event.event_type == LiveEventType.RED_CARD and event.minute <= minute
                for event in normalized
            )
            groups[f"red_card:{red_before}"].append(snapshot_index)
            snapshot_index += 1
    actual_array = np.asarray(actual_outcomes)
    match_id_array = np.asarray(snapshot_match_ids)
    outcome_reports = {}
    for name, values in predictions.items():
        matrix = np.vstack(values)
        metrics = outcome_metrics(actual_array, matrix)
        interval = _cluster_interval(
            actual_array,
            matrix,
            match_id_array,
            lambda actual, probability: outcome_metrics(actual, probability)["log_loss"],
        )
        outcome_reports[name] = {**metrics, "log_loss_95_ci": list(interval)}
    windows = {
        name: {
            str(window): _binary_report(
                np.asarray(window_actual[window]),
                np.asarray(values[window]),
                match_id_array,
            )
            for window in (5, 10, 15)
        }
        for name, values in window_predicted.items()
    }
    live_matrix = np.vstack(predictions["live_event_model"])
    grouped = {}
    for name, indices in groups.items():
        if len(indices) < 10:
            continue
        index = np.asarray(indices)
        grouped[name] = {
            "snapshots": len(index),
            **outcome_metrics(actual_array[index], live_matrix[index]),
        }
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "historical_replay_not_live",
        "matches": replayed_matches,
        "snapshots": len(actual_array),
        "date_range": [str(matches["kickoff"].min()), str(matches["kickoff"].max())],
        "outcome": outcome_reports,
        "goal_windows": windows,
        "next_scoring_team": {
            "samples": len(next_team_actual),
            "accuracy": float(
                np.mean(np.asarray(next_team_actual) == np.asarray(next_team_predicted))
            )
            if next_team_actual
            else None,
        },
        "by_group": grouped,
        "limitations": [
            "This is accelerated historical replay from cached StatsBomb events, not a live feed.",
            "Event coefficients are heuristics pending a larger independently calibrated holdout.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    return report
