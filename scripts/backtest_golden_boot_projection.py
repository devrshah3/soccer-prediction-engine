"""Internal backtest of the Golden Boot projection method (kickcast_api.golden_boot_
projection) against real historical data: StatsBomb Open Data's 4 full 2015/16 league
seasons (Premier League, La Liga, Serie A, Ligue 1 - see kickcast_engine.data.statsbomb.
FULL_SEASONS), which are the only competitions in this project with real, dated,
per-goal, per-match data across a FULL completed season - exactly what's needed to
simulate "what would the projection have said at matchday 5/10/20, and how did that
compare to what actually happened".

This data is used INTERNALLY here only, to validate the method - never surfaced as
real-looking 2015/16 "live" scorer data anywhere user-facing (that would be inventing
data). See item 6 for the parallel rule about StatsBomb matches leaving the user-facing
Replay page entirely.

Method being validated (must stay in sync with kickcast_api/golden_boot_projection.py):
  shrunk_rate = (goals_so_far + prior_rate * SHRINKAGE_MATCHES) / (played_so_far + SHRINKAGE_MATCHES)
  projected_final = goals_so_far + shrunk_rate * remaining_matches
compared against a naive "current pace" baseline: (goals_so_far / played_so_far) * TOTAL_MATCHDAYS.

Candidate pool at each cutoff = the top CANDIDATE_POOL scorers observed so far (mirrors
football-data.org's live top-N leaderboard, which is all the production code ever sees).

Run: python scripts/backtest_golden_boot_projection.py
Writes: reports/golden_boot_backtest.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kickcast_engine.data.statsbomb import FULL_SEASONS, load_matches

REPO_ROOT = Path(__file__).resolve().parents[1]
SB_CACHE_DIR = REPO_ROOT / "data" / "sb"
SUMMARIES_PATH = REPO_ROOT / "data" / "sb_summaries.jsonl"
OUT_PATH = REPO_ROOT / "reports" / "golden_boot_backtest.json"

SHRINKAGE_MATCHES = 5.0
CUTOFFS = [5, 10, 20]
CANDIDATE_POOL = 15
TOTAL_MATCHDAYS = 38  # all 4 competitions were 20-team/38-matchday seasons in 2015/16


def load_summaries() -> dict[int, dict]:
    out = {}
    with SUMMARIES_PATH.open() as fh:
        for line in fh:
            d = json.loads(line)
            out[d["match_id"]] = d
    return out


def player_goals(matches: list[dict], summaries: dict[int, dict]) -> tuple[dict[str, int], dict[str, str], dict[str, int]]:
    """Across the given matches (chronological order), returns:
    - cumulative non-own-goal goals per player
    - each player's most-recently-scored-for team name (good enough for a 2015/16 season)
    - matches played per team (home or away appearance count)
    """
    goals: dict[str, int] = {}
    player_team: dict[str, str] = {}
    team_played: dict[str, int] = {}
    for m in matches:
        s = summaries.get(int(m["source_id"]))
        team_played[m["home"]] = team_played.get(m["home"], 0) + 1
        team_played[m["away"]] = team_played.get(m["away"], 0) + 1
        if s is None:
            continue
        for g in s["goals"]:
            if g["own_goal"] or not g["player"]:
                continue
            goals[g["player"]] = goals.get(g["player"], 0) + 1
            player_team[g["player"]] = m["home"] if g["side"] == "home" else m["away"]
    return goals, player_team, team_played


def run_one(league_name: str, matches: list[dict], summaries: dict[int, dict]) -> list[dict]:
    final_goals, _, _ = player_goals(matches, summaries)
    results = []
    for cutoff in CUTOFFS:
        n_observed = cutoff * (len({m["home"] for m in matches}) // 2)
        observed = matches[:n_observed]
        goals_so_far, player_team, team_played = player_goals(observed, summaries)
        pool = sorted(goals_so_far.items(), key=lambda kv: -kv[1])[:CANDIDATE_POOL]
        if len(pool) < 2:
            continue

        rates = []
        for player, g in pool:
            played = team_played.get(player_team.get(player, ""), cutoff)
            if played > 0:
                rates.append(g / played)
        prior_rate = sum(rates) / len(rates) if rates else 0.0

        rows = []
        for player, g in pool:
            team = player_team.get(player, "")
            played = team_played.get(team, cutoff)
            remaining = max(TOTAL_MATCHDAYS - played, 0)
            shrunk_rate = (g + prior_rate * SHRINKAGE_MATCHES) / (played + SHRINKAGE_MATCHES)
            projected = g + shrunk_rate * remaining
            naive = (g / played * TOTAL_MATCHDAYS) if played > 0 else g
            actual = final_goals.get(player, g)
            rows.append({
                "player": player, "goals_so_far": g, "actual_final": actual,
                "projected_final": round(projected, 2), "naive_final": round(naive, 2),
            })

        actual_top = max(rows, key=lambda r: r["actual_final"])["player"]
        model_top = max(rows, key=lambda r: r["projected_final"])["player"]
        naive_top = max(rows, key=lambda r: r["naive_final"])["player"]
        model_mae = sum(abs(r["projected_final"] - r["actual_final"]) for r in rows) / len(rows)
        naive_mae = sum(abs(r["naive_final"] - r["actual_final"]) for r in rows) / len(rows)

        results.append({
            "league": league_name, "cutoff_matchday": cutoff, "candidates": len(rows),
            "model_mae": round(model_mae, 2), "naive_mae": round(naive_mae, 2),
            "model_hit": model_top == actual_top, "naive_hit": naive_top == actual_top,
            "actual_top_scorer": actual_top, "model_picked": model_top, "naive_picked": naive_top,
        })
    return results


def main() -> None:
    summaries = load_summaries()
    all_results = []
    for name, (comp_id, season_id) in FULL_SEASONS.items():
        matches = load_matches(comp_id, season_id, SB_CACHE_DIR)
        all_results += run_one(name, matches, summaries)

    model_maes = [r["model_mae"] for r in all_results]
    naive_maes = [r["naive_mae"] for r in all_results]
    model_hit_rate = sum(r["model_hit"] for r in all_results) / len(all_results)
    naive_hit_rate = sum(r["naive_hit"] for r in all_results) / len(all_results)
    avg_model_mae = sum(model_maes) / len(model_maes)
    avg_naive_mae = sum(naive_maes) / len(naive_maes)

    report = {
        "source": "StatsBomb Open Data (CC0), 4 full 2015/16 league seasons - internal "
                   "backtest only, never shown as live scorer data anywhere user-facing.",
        "method": "See kickcast_api/golden_boot_projection.py - shrunken per-match rate x "
                  "real remaining matches, vs a naive current-pace baseline.",
        "n_test_points": len(all_results),
        "results": all_results,
        "summary": {
            "model_avg_mae_goals": round(avg_model_mae, 2),
            "naive_avg_mae_goals": round(avg_naive_mae, 2),
            "model_hit_rate": round(model_hit_rate, 3),
            "naive_hit_rate": round(naive_hit_rate, 3),
            "winner": "model" if avg_model_mae < avg_naive_mae else "naive",
        },
    }
    OUT_PATH.write_text(json.dumps(report, indent=2))
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
