"""Pre-match team features computed strictly from earlier kickoffs."""

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

LOOKBACKS = (3, 5, 10, 20)
BASE_FEATURES = (
    "matches_played",
    "elo",
    "rest_days",
    "form_ewm",
    *(f"points_avg_{window}" for window in LOOKBACKS),
    *(f"goals_for_avg_{window}" for window in LOOKBACKS),
    *(f"goals_against_avg_{window}" for window in LOOKBACKS),
)
FEATURE_COLUMNS = [
    "home_advantage",
    "neutral_venue",
    "month",
    "day_of_week",
    *(f"home_{name}" for name in BASE_FEATURES),
    *(f"away_{name}" for name in BASE_FEATURES),
    *(f"delta_{name}" for name in BASE_FEATURES if name != "rest_days"),
]


def _result_points(goals_for: int, goals_against: int) -> int:
    if goals_for > goals_against:
        return 3
    if goals_for == goals_against:
        return 1
    return 0


def _state(history: list[dict[str, Any]], elo: float, kickoff: pd.Timestamp) -> dict[str, float]:
    """Summarize only the supplied earlier matches."""

    values: dict[str, float] = {
        "matches_played": float(len(history)),
        "elo": elo,
        "rest_days": 7.0,
        "form_ewm": 0.0,
    }
    if history:
        values["rest_days"] = float(
            np.clip((kickoff - pd.Timestamp(history[-1]["kickoff"])).total_seconds() / 86400, 0, 30)
        )
        weights = np.power(1 - 0.35, np.arange(len(history) - 1, -1, -1))
        points = np.array([item["points"] for item in history])
        values["form_ewm"] = float(np.average(points, weights=weights))
    for window in LOOKBACKS:
        recent = history[-window:]
        for source in ("points", "goals_for", "goals_against"):
            values[f"{source}_avg_{window}"] = (
                float(np.mean([item[source] for item in recent])) if recent else 0.0
            )
    return values


def build_match_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Build match-level features where every rolling value is shifted by one match.

    Input may contain scheduled fixtures. Finished matches build history; scheduled fixtures receive
    the most recent earlier team state without ever updating history.
    """

    required = {
        "match_id",
        "kickoff",
        "home_team_id",
        "away_team_id",
        "home_score",
        "away_score",
        "neutral_venue",
    }
    missing = required.difference(matches.columns)
    if missing:
        raise ValueError(f"matches missing required columns: {sorted(missing)}")
    ordered = matches.copy()
    ordered["kickoff"] = pd.to_datetime(ordered["kickoff"], utc=True)
    ordered = ordered.sort_values(["kickoff", "match_id"]).reset_index(drop=True)
    histories: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    ratings: defaultdict[str, float] = defaultdict(lambda: 1500.0)
    rows: list[dict[str, object]] = []
    for raw_match in ordered.itertuples(index=False):
        match: Any = raw_match
        kickoff = pd.Timestamp(match.kickoff)
        home_id = str(match.home_team_id)
        away_id = str(match.away_team_id)
        home = _state(histories[home_id], ratings[home_id], kickoff)
        away = _state(histories[away_id], ratings[away_id], kickoff)
        row: dict[str, object] = {
            "match_id": match.match_id,
            "kickoff": kickoff,
            "home_team_id": match.home_team_id,
            "away_team_id": match.away_team_id,
            "home_score": match.home_score,
            "away_score": match.away_score,
            "home_advantage": 0.0 if bool(match.neutral_venue) else 1.0,
            "neutral_venue": float(bool(match.neutral_venue)),
            "month": float(kickoff.month),
            "day_of_week": float(kickoff.dayofweek),
        }
        for name in BASE_FEATURES:
            row[f"home_{name}"] = home[name]
            row[f"away_{name}"] = away[name]
            if name != "rest_days":
                row[f"delta_{name}"] = home[name] - away[name]
        if pd.isna(match.home_score) or pd.isna(match.away_score):
            row["outcome"] = None
        elif match.home_score > match.away_score:
            row["outcome"] = "home"
        elif match.home_score < match.away_score:
            row["outcome"] = "away"
        else:
            row["outcome"] = "draw"
        rows.append(row)
        if not pd.isna(match.home_score) and not pd.isna(match.away_score):
            home_score = int(match.home_score)
            away_score = int(match.away_score)
            histories[home_id].append(
                {
                    "kickoff": kickoff,
                    "goals_for": float(home_score),
                    "goals_against": float(away_score),
                    "points": float(_result_points(home_score, away_score)),
                }
            )
            histories[away_id].append(
                {
                    "kickoff": kickoff,
                    "goals_for": float(away_score),
                    "goals_against": float(home_score),
                    "points": float(_result_points(away_score, home_score)),
                }
            )
            advantage = 0.0 if bool(match.neutral_venue) else 65.0
            expected_home = 1 / (
                1 + 10 ** ((ratings[away_id] - ratings[home_id] - advantage) / 400)
            )
            actual_home = 1.0 if home_score > away_score else 0.5
            if home_score < away_score:
                actual_home = 0.0
            change = 24.0 * (actual_home - expected_home)
            ratings[home_id] += change
            ratings[away_id] -= change
    frame = pd.DataFrame(rows)
    frame[FEATURE_COLUMNS] = frame[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return frame
