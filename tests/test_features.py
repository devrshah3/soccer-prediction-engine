import pandas as pd

from soccer_engine.features.team import build_match_features


def test_rolling_features_exclude_current_match(small_matches: pd.DataFrame) -> None:
    original = build_match_features(small_matches)
    changed = small_matches.copy()
    changed.loc[10, ["home_score", "away_score"]] = [99, 0]
    rebuilt = build_match_features(changed)
    current_columns = [
        column
        for column in original
        if column.startswith(("home_", "away_", "delta_"))
        and column not in {"home_team_id", "away_team_id", "home_score", "away_score"}
    ]
    pd.testing.assert_series_equal(
        original.loc[10, current_columns], rebuilt.loc[10, current_columns], check_names=False
    )
    assert not original.loc[11:, current_columns].equals(rebuilt.loc[11:, current_columns])


def test_future_match_change_cannot_change_past_features(small_matches: pd.DataFrame) -> None:
    original = build_match_features(small_matches)
    changed = small_matches.copy()
    changed.loc[39, ["home_score", "away_score"]] = [50, 50]
    rebuilt = build_match_features(changed)
    pd.testing.assert_frame_equal(original.iloc[:39], rebuilt.iloc[:39])


def test_neutral_fixture_has_no_home_advantage(small_matches: pd.DataFrame) -> None:
    neutral = small_matches.copy()
    neutral.loc[5, "neutral_venue"] = True
    features = build_match_features(neutral)
    assert features.loc[5, "home_advantage"] == 0
    assert features.loc[5, "neutral_venue"] == 1


def test_missing_optional_statistics_are_supported(small_matches: pd.DataFrame) -> None:
    features = build_match_features(small_matches)
    assert len(features) == len(small_matches)
    assert not features.filter(regex="^(home|away|delta)_").isna().any().any()
