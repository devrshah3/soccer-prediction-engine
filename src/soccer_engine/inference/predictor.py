"""Structured fixture inference."""

from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from soccer_engine.evaluation.metrics import CLASS_ORDER
from soccer_engine.features.player import build_player_features
from soccer_engine.models.scorers import predict_goalscorers
from soccer_engine.models.timing import predict_goal_intervals
from soccer_engine.schemas import (
    ExpectedLineupPlayer,
    FixturePrediction,
    OutcomeProbabilities,
    ScorelineProbability,
)
from soccer_engine.training import ModelBundle


def _market_probabilities(distribution: np.ndarray) -> dict[str, float]:
    total_indices = np.add.outer(np.arange(distribution.shape[0]), np.arange(distribution.shape[1]))
    return {
        "over_1_5": float(distribution[total_indices >= 2].sum()),
        "over_2_5": float(distribution[total_indices >= 3].sum()),
        "over_3_5": float(distribution[total_indices >= 4].sum()),
        "both_teams_to_score": float(distribution[1:, 1:].sum()),
        "home_clean_sheet": float(distribution[:, 0].sum()),
        "away_clean_sheet": float(distribution[0, :].sum()),
    }


def predict_fixture(
    fixture: pd.Series,
    feature_row: pd.DataFrame,
    bundle: ModelBundle,
    player_matches: pd.DataFrame | None = None,
    goal_events: pd.DataFrame | None = None,
) -> FixturePrediction:
    """Generate calibrated outcome and probabilistic scoreline output."""

    outcome_array = bundle.outcome_model.predict_proba(feature_row)[0]
    mapped = dict(zip(CLASS_ORDER, outcome_array, strict=True))
    home_xg_values, away_xg_values = bundle.goal_model.predict_expected_goals(feature_row)
    home_xg, away_xg = float(home_xg_values[0]), float(away_xg_values[0])
    distribution = bundle.goal_model.distribution(home_xg, away_xg)
    positions = np.dstack(
        np.unravel_index(np.argsort(distribution.ravel())[::-1], distribution.shape)
    )[0]
    scorelines = [
        ScorelineProbability(
            home_goals=int(home), away_goals=int(away), probability=float(distribution[home, away])
        )
        for home, away in positions[:5]
    ]
    markets = _market_probabilities(distribution)
    history_matches = min(
        float(feature_row.iloc[0]["home_matches_played"]),
        float(feature_row.iloc[0]["away_matches_played"]),
    )
    reliability = "medium" if history_matches >= 10 else "low"
    team_ids = [str(fixture["home_team_id"]), str(fixture["away_team_id"])]
    candidates = build_player_features(
        player_matches if player_matches is not None else pd.DataFrame(),
        fixture["kickoff"],
        team_ids,
    )
    scorers = predict_goalscorers(candidates, {team_ids[0]: home_xg, team_ids[1]: away_xg})
    lineup_rows: list[ExpectedLineupPlayer] = []
    if not candidates.empty:
        for team_id in team_ids:
            selected_lineup = candidates[candidates["team_id"] == team_id].nlargest(
                11, "starting_probability"
            )
            for raw_row in selected_lineup.itertuples(index=False):
                row: Any = raw_row
                lineup_rows.append(
                    ExpectedLineupPlayer(
                        player_id=str(row.player_id),
                        player_name=str(row.player_name),
                        team_id=str(row.team_id),
                        team_name=str(row.team_name),
                        position=None if pd.isna(row.position) else str(row.position),
                        starting_probability=float(row.starting_probability),
                        expected_minutes=float(row.expected_minutes),
                        reliability=str(row.reliability),
                    )
                )
    intervals, timing_reliability = predict_goal_intervals(
        goal_events if goal_events is not None else pd.DataFrame(),
        fixture["kickoff"],
        home_xg,
        away_xg,
    )
    warnings = [
        "Current injury and suspension data are unavailable; lineup probabilities use prior squads."
    ]
    if not scorers:
        warnings.append(
            "No compatible earlier player history was found; "
            "goalscorer probabilities are unavailable."
        )
    if timing_reliability == "low":
        warnings.append("Goal-timing history is limited; interval estimates use a smoothed prior.")
    if reliability == "low":
        warnings.append("At least one team has fewer than 10 earlier matches in this dataset.")
    factors = [
        f"Pre-match Elo difference: {feature_row.iloc[0]['delta_elo']:.0f} points",
        f"Recent 5-match points-rate difference: {feature_row.iloc[0]['delta_points_avg_5']:.2f}",
        "Normal home advantage applied"
        if feature_row.iloc[0]["home_advantage"]
        else "Neutral venue: no home advantage applied",
    ]
    return FixturePrediction(
        fixture_id=str(fixture["match_id"]),
        competition=str(fixture["competition_name"]),
        kickoff=pd.Timestamp(fixture["kickoff"]).to_pydatetime(),
        home_team=str(fixture["home_team_name"]),
        away_team=str(fixture["away_team_name"]),
        outcome=OutcomeProbabilities(
            home_win=float(mapped["home"]),
            draw=float(mapped["draw"]),
            away_win=float(mapped["away"]),
        ),
        expected_home_goals=home_xg,
        expected_away_goals=away_xg,
        expected_home_margin=home_xg - away_xg,
        likely_scorelines=scorelines,
        expected_lineups=lineup_rows,
        likely_goalscorers=scorers[:12],
        goal_intervals=intervals,
        important_factors=factors,
        data_freshness=pd.Timestamp(fixture.get("ingested_at", datetime.now(UTC))).to_pydatetime(),
        model_version=bundle.version,
        reliability=reliability,
        warnings=warnings,
        over_1_5=markets["over_1_5"],
        over_2_5=markets["over_2_5"],
        over_3_5=markets["over_3_5"],
        both_teams_to_score=markets["both_teams_to_score"],
        home_clean_sheet=markets["home_clean_sheet"],
        away_clean_sheet=markets["away_clean_sheet"],
    )
