from __future__ import annotations

from kickcast_engine.models.goal_timing import SHAPE, goal_timing_windows
from kickcast_engine.models.goalscorers import aggregate_goals, likely_scorers, scorer_shares


def test_shape_sums_to_one():
    assert abs(sum(p for _, p in SHAPE) - 1) < 1e-9


def test_goal_timing_scales_with_expected_goals():
    windows = goal_timing_windows(2.0)
    assert len(windows) == 7
    assert abs(sum(w["expected_goals"] for w in windows) - 2.0) < 0.01  # each window is rounded to 3dp
    # more goals in a window -> higher (but still <1) probability of at least one
    zero = goal_timing_windows(0.0)
    assert all(w["expected_goals"] == 0 and w["prob_at_least_one_goal"] == 0 for w in zero)
    assert all(0 <= w["prob_at_least_one_goal"] <= 1 for w in windows)


def test_goal_timing_windows_are_labelled_and_ordered():
    windows = goal_timing_windows(2.5)
    assert [w["window"] for w in windows] == ["0-15", "15-30", "30-45", "45-60", "60-75", "75-90", "90+"]


def test_scorer_shares_sum_to_one():
    shares = scorer_shares([("A", 6), ("B", 3), ("C", 1)])
    assert abs(sum(s["share"] for s in shares) - 1) < 1e-9
    assert shares[0]["player"] == "A"  # sorted descending


def test_scorer_shares_empty_when_no_goals():
    assert scorer_shares([]) == []
    assert scorer_shares([("A", 0)]) == []


def test_likely_scorers_probabilities_bounded():
    goals = aggregate_goals([("A", False, False), ("A", False, True), ("B", False, False), ("OG", True, False)])
    # own goal excluded, so only A (2 goals) and B (1 goal) count
    assert dict(goals) == {"A": 2, "B": 1}
    scorers = likely_scorers(goals, team_expected_goals=1.5)
    assert all(0 <= s["prob_scores"] <= 1 for s in scorers)
    assert scorers[0]["player"] == "A"


def test_likely_scorers_no_data_returns_empty():
    assert likely_scorers([], team_expected_goals=1.5) == []
