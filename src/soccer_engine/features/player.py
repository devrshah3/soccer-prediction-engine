"""Cutoff-safe expected-lineup and player form features."""

from datetime import datetime

import numpy as np
import pandas as pd

POSITION_START_PRIORS = {
    "Goalkeeper": 0.72,
    "Center Back": 0.58,
    "Right Back": 0.55,
    "Left Back": 0.55,
    "Midfield": 0.50,
    "Wing": 0.48,
    "Forward": 0.52,
}


def _position_group(position: str | None) -> str:
    value = position or ""
    if "Goalkeeper" in value:
        return "Goalkeeper"
    if "Back" in value:
        return "Center Back" if "Center" in value else value
    if "Wing" in value:
        return "Wing"
    if "Forward" in value or "Striker" in value:
        return "Forward"
    return "Midfield"


def _weighted_average(values: np.ndarray, decay: float = 0.82) -> float:
    if not len(values):
        return 0.0
    weights = np.power(decay, np.arange(len(values) - 1, -1, -1))
    return float(np.average(values, weights=weights))


def build_player_features(
    player_matches: pd.DataFrame,
    fixture_kickoff: datetime | pd.Timestamp,
    team_ids: list[str],
    lookback_matches: int = 10,
) -> pd.DataFrame:
    """Estimate lineups using only player rows strictly before fixture kickoff."""

    columns = [
        "player_id",
        "player_name",
        "team_id",
        "team_name",
        "position",
        "starting_probability",
        "expected_minutes",
        "appearances",
        "total_minutes",
        "goals_per90",
        "non_penalty_goals_per90",
        "xg_per90",
        "shots_per90",
        "recent_goals_per90",
        "penalty_share",
        "last_seen",
        "reliability",
    ]
    if player_matches.empty:
        return pd.DataFrame(columns=columns)
    cutoff = pd.Timestamp(fixture_kickoff)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    history = player_matches.copy()
    history["kickoff"] = pd.to_datetime(history["kickoff"], utc=True)
    history = history[(history["kickoff"] < cutoff) & history["team_id"].isin(team_ids)]
    if history.empty:
        return pd.DataFrame(columns=columns)

    candidates: list[dict[str, object]] = []
    for team_id in team_ids:
        team_history = history[history["team_id"] == team_id].sort_values("kickoff")
        recent_team_dates = team_history["kickoff"].drop_duplicates().tail(3)
        active_ids = team_history[team_history["kickoff"].isin(recent_team_dates)][
            "player_id"
        ].unique()
        for player_id in active_ids:
            rows = team_history[team_history["player_id"] == player_id].tail(lookback_matches)
            latest = rows.iloc[-1]
            minutes = rows["minutes"].to_numpy(dtype=float)
            total_minutes = float(minutes.sum())
            position = latest.get("position")
            group = _position_group(position if isinstance(position, str) else None)
            prior = POSITION_START_PRIORS.get(group, 0.5)
            weighted_start = _weighted_average(rows["started"].astype(float).to_numpy())
            start_probability = (weighted_start * len(rows) + prior * 2) / (len(rows) + 2)
            expected_minutes = _weighted_average(minutes)
            denominator = max(total_minutes, 180.0)
            recent = rows.tail(5)
            recent_minutes = max(float(recent["minutes"].sum()), 90.0)
            appearances = int((rows["minutes"] > 0).sum())
            reliability = "high" if appearances >= 8 else "medium" if appearances >= 4 else "low"
            candidates.append(
                {
                    "player_id": player_id,
                    "player_name": latest["player_name"],
                    "team_id": team_id,
                    "team_name": latest["team_name"],
                    "position": position,
                    "starting_probability": float(np.clip(start_probability, 0.02, 0.98)),
                    "expected_minutes": max(expected_minutes, 2.0),
                    "appearances": appearances,
                    "total_minutes": total_minutes,
                    "goals_per90": float(rows["goals"].sum() * 90 / denominator),
                    "non_penalty_goals_per90": float(
                        rows["non_penalty_goals"].sum() * 90 / denominator
                    ),
                    "xg_per90": float(rows["expected_goals"].sum() * 90 / denominator),
                    "shots_per90": float(rows["shots"].sum() * 90 / denominator),
                    "recent_goals_per90": float(recent["goals"].sum() * 90 / recent_minutes),
                    "penalty_share": float(
                        rows["penalties_taken"].sum()
                        / max(team_history["penalties_taken"].sum(), 1)
                    ),
                    "last_seen": latest["kickoff"],
                    "reliability": reliability,
                }
            )
    result = pd.DataFrame(candidates, columns=columns)
    if result.empty:
        return result
    for team_id in team_ids:
        mask = result["team_id"] == team_id
        if not mask.any():
            continue
        start_total = float(result.loc[mask, "starting_probability"].sum())
        if start_total > 0:
            result.loc[mask, "starting_probability"] = np.clip(
                result.loc[mask, "starting_probability"] * 11 / start_total, 0.01, 0.99
            )
        minute_total = float(result.loc[mask, "expected_minutes"].sum())
        if minute_total > 0:
            result.loc[mask, "expected_minutes"] = np.clip(
                result.loc[mask, "expected_minutes"] * 990 / minute_total, 1, 95
            )
    return result.sort_values(
        ["team_id", "starting_probability", "expected_minutes"], ascending=[True, False, False]
    ).reset_index(drop=True)
