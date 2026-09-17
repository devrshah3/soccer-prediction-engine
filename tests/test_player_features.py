import math

import pandas as pd
import pytest

from soccer_engine.features.player import build_player_features
from soccer_engine.models.scorers import predict_goalscorers, scorer_reconciliation_error
from soccer_engine.models.timing import predict_goal_intervals


def _fixture_context(player_matches: pd.DataFrame) -> tuple[pd.Timestamp, list[str]]:
    kickoffs = sorted(pd.to_datetime(player_matches["kickoff"], utc=True).unique())
    cutoff = pd.Timestamp(kickoffs[int(len(kickoffs) * 0.85)])
    teams = (
        player_matches[pd.to_datetime(player_matches["kickoff"], utc=True) == cutoff]["team_id"]
        .drop_duplicates()
        .tolist()
    )
    return cutoff, teams


def test_player_features_use_only_rows_before_kickoff(player_sample) -> None:
    player_matches, _ = player_sample
    cutoff, teams = _fixture_context(player_matches)
    original = build_player_features(player_matches, cutoff, teams)
    changed = player_matches.copy()
    dates = pd.to_datetime(changed["kickoff"], utc=True)
    changed.loc[dates >= cutoff, ["goals", "expected_goals", "minutes", "started"]] = [
        99,
        99.0,
        1.0,
        False,
    ]
    rebuilt = build_player_features(changed, cutoff, teams)
    pd.testing.assert_frame_equal(original, rebuilt)


def test_expected_lineup_is_bounded_and_has_reliability(player_sample) -> None:
    player_matches, _ = player_sample
    cutoff, teams = _fixture_context(player_matches)
    features = build_player_features(player_matches, cutoff, teams)
    assert set(features["team_id"]) == set(teams)
    assert features["starting_probability"].between(0, 1).all()
    assert features["expected_minutes"].between(0, 130).all()
    assert set(features["reliability"]).issubset({"low", "medium", "high"})
    for team in teams:
        assert len(features[features["team_id"] == team].nlargest(11, "starting_probability")) == 11


def test_scorer_probabilities_reconcile_to_team_forecast(player_sample) -> None:
    player_matches, _ = player_sample
    cutoff, teams = _fixture_context(player_matches)
    candidates = build_player_features(player_matches, cutoff, teams)
    team_xg = {teams[0]: 1.7, teams[1]: 1.1}
    predictions = predict_goalscorers(candidates, team_xg)
    assert scorer_reconciliation_error(predictions, team_xg) < 1e-9
    assert all(0 <= item.scoring_probability <= 1 for item in predictions)
    expected_first_scorer_mass = 1 - math.exp(-sum(team_xg.values()))
    assert sum(item.first_scorer_probability for item in predictions) == pytest.approx(
        expected_first_scorer_mass
    )


def test_goal_timing_ignores_current_and_future_events(player_sample) -> None:
    _, goal_events = player_sample
    cutoff = pd.Timestamp("2024-04-01", tz="UTC")
    original, reliability = predict_goal_intervals(goal_events, cutoff, 1.5, 1.0)
    changed = goal_events.copy()
    dates = pd.to_datetime(changed["kickoff"], utc=True)
    changed.loc[dates >= cutoff, "interval"] = "0-15"
    rebuilt, rebuilt_reliability = predict_goal_intervals(changed, cutoff, 1.5, 1.0)
    assert original == rebuilt
    assert reliability == rebuilt_reliability
    assert len(original) == 6
    assert all(0 <= item.any_goal_probability <= 1 for item in original)


def test_player_models_have_safe_missing_data_fallbacks() -> None:
    assert predict_goalscorers(pd.DataFrame(), {"home": 1.2, "away": 0.9}) == []
    intervals, reliability = predict_goal_intervals(
        pd.DataFrame(), pd.Timestamp("2024-01-01", tz="UTC"), 1.2, 0.9
    )
    assert len(intervals) == 6
    assert reliability == "low"
