"""Compute the two real StatsBomb-derived numbers this project cites elsewhere:

1. Goal-timing shape: the share of all goals falling in each 15-minute window, used by
   kickcast_engine/models/goal_timing.py as the shape prior for goal-timing windows.
2. Corner-to-goal rate: the share of corners whose SAME possession produced a goal
   before the ball went dead - used (when the live match center's corner-probability
   feature is built) as the base rate for "who scores from this corner" estimates.

Input is data/sb_summaries.jsonl, produced by scripts/extract_statsbomb_events.py over
the four full 2015/16 StatsBomb Open Data league seasons (Premier League, La Liga,
Serie A, Ligue 1 - see kickcast_engine/data/statsbomb.py's FULL_SEASONS). Reproduce with:

    mkdir -p data/sb
    for p in "2 27" "11 27" "12 27" "7 27"; do set -- $p
      curl -s -o data/sb/matches_$1_$2.json \\
        https://raw.githubusercontent.com/statsbomb/open-data/master/data/matches/$1/$2.json
    done
    python scripts/extract_statsbomb_events.py data/sb_summaries.jsonl data/sb/matches_*_27.json
    python scripts/analyze_corners_and_timing.py data/sb_summaries.jsonl reports/corner_and_timing_stats.json

Writes raw counts alongside the percentages so the numbers are independently checkable,
not just asserted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WINDOWS = ["0-15", "15-30", "30-45", "45-60", "60-75", "75-90", "90+"]


def _window(minute: int, period: int) -> str:
    """StatsBomb's `minute` field is a continuous match clock (period 2 starts at 45, not
    reset to 0 - verified against real event data: period 1 spans minute 0-48ish
    including first-half stoppage, period 2 spans minute 45-94ish including second-half
    stoppage). So stoppage time is: period 1 with minute >= 45, or period 2 (or later -
    extra time, not expected in a normal league season but handled defensively) with
    minute >= 90. Everything else buckets by minute // 15."""
    if period == 1:
        if minute >= 45:
            return "90+"
        return WINDOWS[minute // 15]
    if minute >= 90:
        return "90+"
    idx = minute // 15
    return WINDOWS[idx] if idx < 6 else "90+"


def analyze(summaries_path: Path) -> dict:
    n_matches = 0
    timeline_mismatches = 0
    window_counts = dict.fromkeys(WINDOWS, 0)
    total_goals = 0
    total_corners = 0
    corners_leading_to_goal = 0

    with open(summaries_path) as fh:
        for line in fh:
            s = json.loads(line)
            n_matches += 1
            if not s.get("timeline_matches_score", True):
                timeline_mismatches += 1
            for g in s["goals"]:
                total_goals += 1
                window_counts[_window(g["minute"], g["period"])] += 1
            for c in s["corners"]:
                total_corners += 1
                if c.get("goal"):
                    corners_leading_to_goal += 1

    timing_shape = [
        {"window": w, "goals": window_counts[w], "share": round(window_counts[w] / total_goals, 4)}
        for w in WINDOWS
    ]
    return {
        "source": "StatsBomb Open Data (CC0), 4 full 2015/16 league seasons "
        "(Premier League, La Liga, Serie A, Ligue 1)",
        "reproduce": "scripts/extract_statsbomb_events.py -> scripts/analyze_corners_and_timing.py",
        "n_matches": n_matches,
        "n_matches_with_timeline_mismatch": timeline_mismatches,
        "goal_timing": {
            "total_goals": total_goals,
            "windows": timing_shape,
        },
        "corner_goal_rate": {
            "total_corners": total_corners,
            "corners_leading_to_goal": corners_leading_to_goal,
            "rate": round(corners_leading_to_goal / total_corners, 4) if total_corners else None,
        },
    }


def main() -> None:
    result = analyze(Path(sys.argv[1]))
    out_path = Path(sys.argv[2])
    out_path.write_text(json.dumps(result, indent=1))
    print(f"matches: {result['n_matches']} (timeline mismatches: {result['n_matches_with_timeline_mismatch']})")
    print(f"goals: {result['goal_timing']['total_goals']}")
    for w in result["goal_timing"]["windows"]:
        print(f"  {w['window']:8} {w['goals']:5}  {w['share'] * 100:5.1f}%")
    cg = result["corner_goal_rate"]
    print(f"corners: {cg['total_corners']}, leading to a goal: {cg['corners_leading_to_goal']} "
          f"({(cg['rate'] or 0) * 100:.2f}%)")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
