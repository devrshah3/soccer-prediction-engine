"""Likely-goalscorer probabilities from historical scoring share.

Only meaningful where we have real player-level goal data (currently: international
matches, from martj42's goalscorers.csv). We do NOT have a free, keyless source of
domestic-league (Premier League etc.) player-level stats - see MORNING_REPORT.md -
so this is never used for domestic predictions; callers should show "not available"
there instead of calling this with fabricated inputs.

Method: a player's share of their team's historical goals (own goals/penalties
excluded from the numerator, since a "likely scorer" claim about a penalty or an
own goal is a different thing) times the team's model expected goals for this match,
converted to a "scores at least once" probability via Poisson(mean=share*xG). This is
a simple, explainable approximation from real historical data, NOT a squad-sheet or
fitness/rotation-aware forecast, and is clearly labeled as such in the API/UI.
"""

from __future__ import annotations

import math
from collections import Counter


def scorer_shares(scorer_goals: list[tuple[str, int]]) -> list[dict]:
    """scorer_goals: [(player_name, goals_in_lookback_window), ...] for one team.
    Returns players sorted by share, descending."""
    total = sum(g for _, g in scorer_goals)
    if total == 0:
        return []
    return [
        {"player": name, "goals_in_window": goals, "share": goals / total}
        for name, goals in sorted(scorer_goals, key=lambda x: -x[1])
    ]


def likely_scorers(scorer_goals: list[tuple[str, int]], team_expected_goals: float, top_n: int = 6) -> list[dict]:
    shares = scorer_shares(scorer_goals)[:top_n]
    return [
        {
            "player": s["player"],
            "goals_in_window": s["goals_in_window"],
            "prob_scores": round(1 - math.exp(-team_expected_goals * s["share"]), 4),
        }
        for s in shares
    ]


def aggregate_goals(rows: list[tuple[str, bool, bool]]) -> list[tuple[str, int]]:
    """rows: [(scorer_name, own_goal, penalty), ...], one row per goal event. Own goals
    are excluded (credited to the wrong team for "who is likely to score" purposes);
    penalties are kept (they were still that player's goal)."""
    c: Counter[str] = Counter()
    for name, own_goal, _penalty in rows:
        if own_goal:
            continue
        c[name] += 1
    return list(c.items())
