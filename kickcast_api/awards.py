"""Awards: built honestly against what data actually exists.

- Golden Boot: traditionally a DOMESTIC league season award. Real per-player domestic
  scoring data now exists for the big-5 leagues (API-Football free tier - see
  kickcast_api.domestic_scorers for the real data-quality caveat: it's the 2024-25
  season, NOT the current 2026-27 season, which needs a paid plan). Reported as a real
  historical leaderboard per league, clearly labeled with the actual season used - not
  presented as a live/current simulation, since we have no current-season data.
- Ballon d'Or / The Best: needs real historical voting data to train anything honest.
  No free, verified dataset of past voting results was found - `available: false`
  rather than a model trained on nothing.
- Puskas: the spec wants nominees + official video links, no probability. We have no
  free, verified source of nominee lists - `available: false`.

All three are structured so a better data source can be plugged in later without
changing the API shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import domestic_scorers
from .models import Goalscorer, Team

LOOKBACK_DAYS = 365
DOMESTIC_LEAGUES = [
    ("en.1", "Premier League"), ("es.1", "La Liga"), ("it.1", "Serie A"),
    ("de.1", "Bundesliga"), ("fr.1", "Ligue 1"),
]


def international_top_scorers(session: Session, limit: int = 15) -> list[dict]:
    since = datetime.now(timezone.utc).date() - timedelta(days=LOOKBACK_DAYS)
    rows = (
        session.query(Goalscorer)
        .filter(Goalscorer.date >= since, Goalscorer.own_goal.is_(False))
        .all()
    )
    counts: dict[tuple[str, str], int] = {}
    for r in rows:
        counts[(r.scorer_name, r.team_id)] = counts.get((r.scorer_name, r.team_id), 0) + 1
    team_names = {t.id: t.name for t in session.query(Team).all()}
    ranked = sorted(counts.items(), key=lambda item: -item[1])[:limit]
    return [
        {"player": name, "team_id": team_id, "team_name": team_names.get(team_id, team_id), "goals": n}
        for (name, team_id), n in ranked
    ]


def domestic_golden_boot(league_code: str) -> dict:
    if not domestic_scorers.available(league_code):
        return {
            "available": False,
            "reason": "no per-player data source cached for this league - run "
                      "scripts/fetch_api_football.py (needs API_FOOTBALL_KEY)",
        }
    return {
        "available": True,
        "season": domestic_scorers.SEASON_LABEL,
        "source": domestic_scorers.SOURCE,
        "note": "real final tallies for the most recent season API-Football's free plan can "
                "access - NOT the live current season (needs a paid plan), and NOT a simulation.",
        "top_scorers": domestic_scorers.league_top_scorers(league_code),
    }


def get_awards(session: Session) -> dict:
    scorers = international_top_scorers(session)
    return {
        "golden_boot": {
            "available": any(domestic_scorers.available(code) for code, _ in DOMESTIC_LEAGUES),
            "by_league": {code: domestic_golden_boot(code) for code, _ in DOMESTIC_LEAGUES},
            "international_top_scorers_also_available": {
                "reason": f"Also showing a real international top-scorers leaderboard (last "
                          f"{LOOKBACK_DAYS} days, from martj42/international_results' "
                          "goalscorers.csv) - NOT a Golden Boot (that's domestic-only), included "
                          "for context.",
                "international_top_scorers": scorers,
                "lookback_days": LOOKBACK_DAYS,
            },
        },
        "ballon_dor": {
            "available": False,
            "reason": "Needs real historical Ballon d'Or voting data to train anything honest - "
                      "no free, verified dataset of past voting results was found. Not simulated "
                      "or guessed.",
        },
        "puskas": {
            "available": False,
            "reason": "Needs a real source of nominee lists and official goal video links - none "
                      "found free and keyless. Not fabricated.",
        },
    }
