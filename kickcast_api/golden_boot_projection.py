"""Current-season Golden Boot projection.

Method (the SAME method the internal backtest in scripts/backtest_golden_boot_
projection.py validates against real StatsBomb 2015/16 data - see reports/
golden_boot_backtest.json and GET /awards/method):
  1. Each live scorer's own per-match rate (goals-so-far / played-so-far) is shrunk
     toward a prior rate, weighted by SHRINKAGE_MATCHES "pseudo-matches" of prior - so
     an early-season outlier (e.g. 3 goals in 1 match) doesn't get projected to an
     absurd full-season total. The prior itself is the real per-match rate of that
     league's top scorers in the one past season we have complete data for (2024-25,
     via domestic_scorers) - NOT the current in-season leaderboard's own average, which
     would be circular (a small in-season sample's "leaders" are already selected for
     running hot, so their average rate is itself inflated; a completed prior season
     isn't). Falls back to the in-season leaderboard's own average only when no
     historical season is available at all (e.g. Champions League, which
     domestic_scorers doesn't cover) - a real, disclosed, weaker case.
  2. That shrunk rate is multiplied by the player's team's REAL remaining scheduled
     matches this season, read from our own fixture DB - never guessed.
  3. N_SIMS independent Poisson-noise simulations of "goals still to come" give both a
     [10th, 90th] percentile range per player and a genuine "chance of finishing as
     this competition's top scorer" (share of simulations where that player has the
     single highest simulated final tally), not just a ranking by expected value.
"""

from __future__ import annotations

import numpy as np
from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import domestic_scorers, football_data_scorers
from .models import Match
from .serialize import latest_season

SHRINKAGE_MATCHES = 5.0
N_SIMS = 5000
RNG_SEED = 20260928  # fixed for reproducibility, not tuned/cherry-picked
HISTORICAL_PRIOR_POOL = 5  # top N scorers of the historical season used for the prior


def _remaining_matches(session: Session, league_code: str, season: str, team_id: str) -> int:
    return (
        session.query(Match)
        .filter(
            Match.league_code == league_code, Match.season == season, Match.status == "scheduled",
            or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
        )
        .count()
    )


def _prior_rate(league_code: str, live_scorers: list[dict]) -> tuple[float, str]:
    """Returns (rate, source_description)."""
    if domestic_scorers.available(league_code):
        historical = domestic_scorers.league_top_scorers(league_code, limit=HISTORICAL_PRIOR_POOL)
        rates = [h["goals"] / h["appearances"] for h in historical if h["appearances"] > 0]
        if rates:
            return sum(rates) / len(rates), f"{domestic_scorers.SEASON_LABEL} top {len(rates)} scorers (real, completed season)"
    rates = [s["goals"] / s["played_matches"] for s in live_scorers if s["played_matches"] > 0]
    return (sum(rates) / len(rates) if rates else 0.0), "this season's own live leaderboard (no historical season available)"


def project(session: Session, league_code: str, network: bool = True) -> dict:
    live = football_data_scorers.fetch_scorers(league_code, network=network)
    if live is None:
        return {
            "available": False,
            "reason": "football-data.org's live scorers endpoint returned nothing for this "
                      "competition (no API key configured, rate-limited, or not reachable).",
        }
    season = latest_season(session, league_code)
    if season is None:
        return {"available": False, "reason": "no fixtures on record for the current season yet."}

    scorers = live["scorers"]
    prior_rate, prior_source = _prior_rate(league_code, scorers)

    candidates = []
    for s in scorers:
        remaining = _remaining_matches(session, league_code, season, s["team_id"])
        shrunk_rate = (s["goals"] + prior_rate * SHRINKAGE_MATCHES) / (s["played_matches"] + SHRINKAGE_MATCHES)
        candidates.append({**s, "remaining_matches": remaining, "shrunk_rate": shrunk_rate})

    if not candidates:
        return {"available": False, "reason": "no scorers returned yet this early in the season."}

    rng = np.random.default_rng(RNG_SEED)
    sims = np.zeros((N_SIMS, len(candidates)))
    for i, c in enumerate(candidates):
        lam = max(c["shrunk_rate"] * c["remaining_matches"], 0.0)
        sims[:, i] = c["goals"] + rng.poisson(lam, size=N_SIMS)
    winners = sims.argmax(axis=1)

    out = []
    for i, c in enumerate(candidates):
        col = sims[:, i]
        out.append({
            "player": c["player"], "team_id": c["team_id"], "team_name": c["team_name"],
            "goals_so_far": c["goals"], "played_matches": c["played_matches"],
            "remaining_matches": c["remaining_matches"],
            "projected_final": round(float(np.mean(col)), 1),
            "projected_range": [int(np.percentile(col, 10)), int(np.percentile(col, 90))],
            "top_scorer_chance": round(float((winners == i).mean()), 3),
        })
    out.sort(key=lambda r: -r["projected_final"])
    return {
        "available": True,
        "season": live["season_label"],
        "source": "football-data.org (live)",
        "method": (
            f"Live goals-so-far, per-match rate shrunk ({SHRINKAGE_MATCHES:.0f}-match prior "
            f"weight) toward a prior from {prior_source}, x each player's team's real "
            f"remaining scheduled matches, {N_SIMS} Poisson-noise simulations for the range "
            "and title chance. Backtested on past seasons - see the Method page."
        ),
        "scorers": out,
    }
