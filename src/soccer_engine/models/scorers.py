"""Team-xG-consistent goalscorer and first-scorer probabilities."""

import math
from typing import Any

import pandas as pd

from soccer_engine.schemas import PlayerScorerProbability

POSITION_SCORING_PRIOR = {
    "Goalkeeper": 0.002,
    "Back": 0.045,
    "Midfield": 0.11,
    "Wing": 0.22,
    "Forward": 0.30,
}


def _prior(position: object) -> float:
    value = str(position or "")
    for label, prior in POSITION_SCORING_PRIOR.items():
        if label in value:
            return prior
    return POSITION_SCORING_PRIOR["Midfield"]


def predict_goalscorers(
    candidates: pd.DataFrame,
    expected_goals_by_team: dict[str, float],
) -> list[PlayerScorerProbability]:
    """Allocate each team's expected goals across cutoff-safe candidate players.

    Independent player Poisson intensities sum exactly to the team expected-goals forecast, so the
    implied team clean-sheet probability is mathematically consistent with the goal model.
    """

    if candidates.empty:
        return []
    working = candidates.copy()
    working["raw_weight"] = (
        0.45 * working["xg_per90"].astype(float)
        + 0.25 * working["non_penalty_goals_per90"].astype(float)
        + 0.10 * working["recent_goals_per90"].astype(float)
        + 0.20 * working["position"].map(_prior).astype(float)
    )
    working["raw_weight"] *= working["expected_minutes"].astype(float) / 90
    working["raw_weight"] *= 1 + 0.30 * working["penalty_share"].astype(float)
    working["player_xg"] = 0.0
    for team_id, team_xg in expected_goals_by_team.items():
        mask = working["team_id"] == team_id
        if not mask.any():
            continue
        weights = working.loc[mask, "raw_weight"].clip(lower=1e-6)
        working.loc[mask, "player_xg"] = float(team_xg) * weights / weights.sum()

    total_xg = float(working["player_xg"].sum())
    probability_any_goal = 1 - math.exp(-total_xg)
    results = []
    for raw_row in working.itertuples(index=False):
        row: Any = raw_row
        player_xg = float(row.player_xg)
        first_probability = player_xg / total_xg * probability_any_goal if total_xg > 0 else 0.0
        results.append(
            PlayerScorerProbability(
                player_id=str(row.player_id),
                player_name=str(row.player_name),
                team_id=str(row.team_id),
                team_name=str(row.team_name),
                position=None if pd.isna(row.position) else str(row.position),
                starting_probability=float(row.starting_probability),
                expected_minutes=float(row.expected_minutes),
                expected_goals=player_xg,
                scoring_probability=1 - math.exp(-player_xg),
                first_scorer_probability=first_probability,
                reliability=str(row.reliability),
            )
        )
    return sorted(results, key=lambda item: item.scoring_probability, reverse=True)


def scorer_reconciliation_error(
    predictions: list[PlayerScorerProbability], expected_goals_by_team: dict[str, float]
) -> float:
    """Return maximum absolute team-xG allocation error."""

    errors = []
    for team_id, expected in expected_goals_by_team.items():
        allocated = sum(item.expected_goals for item in predictions if item.team_id == team_id)
        errors.append(abs(allocated - expected))
    return max(errors, default=0.0)
