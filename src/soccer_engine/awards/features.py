"""Cutoff-safe player-period features shared by award-specific models."""

import pandas as pd


def position_group(position: object) -> str:
    value = str(position or "").casefold()
    if "goalkeeper" in value:
        return "goalkeeper"
    if any(word in value for word in ("back", "defender")):
        return "defence"
    if "midfield" in value:
        return "midfield"
    return "attack"


def build_player_period_features(rows: pd.DataFrame) -> pd.DataFrame:
    """Aggregate only caller-filtered rows; player IDs prevent transfer double counting."""

    frame = rows.copy()
    expected_assists_available = "expected_assists" in frame
    for column in ("expected_assists", "penalties_scored"):
        if column not in frame:
            frame[column] = 0.0
    aggregates = frame.groupby("player_id", as_index=False).agg(
        player_name=("player_name", "last"),
        team_id=("team_id", "last"),
        team_name=("team_name", "last"),
        position=("position", "last"),
        goals=("goals", "sum"),
        non_penalty_goals=("non_penalty_goals", "sum"),
        assists=("assists", "sum"),
        expected_goals=("expected_goals", "sum"),
        expected_assists=("expected_assists", "sum"),
        shots=("shots", "sum"),
        shots_on_target=("shots_on_target", "sum"),
        penalties_scored=("penalties_scored", "sum"),
        minutes=("minutes", "sum"),
        starts=("started", "sum"),
        appearances=("match_id", "nunique"),
    )
    aggregates = aggregates[aggregates["minutes"] > 0].copy()
    denominator = aggregates["minutes"].clip(lower=1) / 90
    for column in (
        "goals",
        "non_penalty_goals",
        "assists",
        "expected_goals",
        "expected_assists",
        "shots",
        "shots_on_target",
    ):
        aggregates[f"{column}_per_90"] = aggregates[column] / denominator
    aggregates["goal_involvement"] = aggregates["goals"] + aggregates["assists"]
    aggregates["penalty_adjusted_goals"] = aggregates["goals"] - aggregates["penalties_scored"]
    aggregates["availability_rate"] = aggregates["appearances"] / max(
        int(frame["match_id"].nunique()), 1
    )
    aggregates["position_group"] = aggregates["position"].map(position_group)
    production = aggregates["non_penalty_goals_per_90"] + 0.7 * aggregates["assists_per_90"]

    def normalize(values: pd.Series) -> pd.Series:
        deviation = float(values.std(ddof=0))
        return (values - values.mean()) / deviation if deviation > 0 else values * 0

    aggregates["position_adjusted_production"] = production.groupby(
        aggregates["position_group"]
    ).transform(normalize)
    aggregates["data_completeness"] = 0.9 if expected_assists_available else 0.75
    return aggregates
