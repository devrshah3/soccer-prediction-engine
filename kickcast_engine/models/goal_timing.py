"""Goal-timing windows: within-match distribution of WHEN goals happen.

The shape prior is the real empirical distribution computed by
scripts/analyze_corners_and_timing.py from all 1,517 StatsBomb Open Data matches across
the four full 2015/16 league seasons (Premier League, La Liga, Serie A, Ligue 1) -
raw counts in reports/corner_and_timing_stats.json, re-run 2026-09-23 (3,979 goals
total; 14 of the 1,517 matches have a goal-event-count/final-score mismatch in
StatsBomb's own data, included anyway since it doesn't materially change the shape -
see the report). Goal minutes bucketed into 15-minute windows, extra time folded into
"90+": 13.0% (0-15'), 14.4% (15-30'), 15.0% (30-45'), 16.5% (45-60'), 16.3% (60-75'),
18.0% (75-90'), 6.7% (90+). This is a SHAPE, not a per-match measurement: for a given
match we don't know when its goals will land, only the match's total expected goals
(from the Dixon-Coles prediction) and this league-wide shape of when goals tend to
happen. Expected goals in a window = total expected goals * that window's share.

"Probability at least one goal in this window" additionally assumes goals in a window
follow a Poisson distribution with that expected count - a standard modelling
assumption, not something separately verified against minute-level data beyond the
shape prior itself.
"""

from __future__ import annotations

import math

_RAW_SHAPE = [
    ("0-15", 0.1299),
    ("15-30", 0.1445),
    ("30-45", 0.1503),
    ("45-60", 0.1649),
    ("60-75", 0.1634),
    ("75-90", 0.1802),
    ("90+", 0.0669),
]
_TOTAL = sum(p for _, p in _RAW_SHAPE)
SHAPE: list[tuple[str, float]] = [(w, p / _TOTAL) for w, p in _RAW_SHAPE]  # normalized to sum to exactly 1


def goal_timing_windows(total_expected_goals: float) -> list[dict]:
    """total_expected_goals: sum of both teams' expected goals for the match (lam + mu)."""
    out = []
    for window, share in SHAPE:
        expected = total_expected_goals * share
        out.append(
            {
                "window": window,
                "share_of_goals": round(share, 4),
                "expected_goals": round(expected, 3),
                "prob_at_least_one_goal": round(1 - math.exp(-expected), 4),
            }
        )
    return out
