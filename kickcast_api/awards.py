"""Awards: built honestly against what data actually exists, season by season.

- Golden Boot, CURRENT season: a live per-player leaderboard from football-data.org
  (kickcast_api.football_data_scorers - the only source on our free tier that can see
  the LIVE season) plus a projection of each contender's final tally
  (kickcast_api.golden_boot_projection), backtested internally against real 2015/16
  data (see /awards/method).
- Golden Boot, past seasons: only the ONE past season API-Football's free tier actually
  gave us (kickcast_api.domestic_scorers, "2024-25", domestic leagues only) is shown,
  labeled "Final" with no projection. Any OTHER past season - or Champions League for
  any past season, which neither source covers - is reported unavailable, honestly,
  never silently substituted with a different season's data.
- Ballon d'Or / The Best: needs real historical voting data to train anything honest.
  No free, verified dataset of past voting results was found - `available: false`
  rather than a model trained on nothing.
- Puskas: the spec wants nominees + official video links, no probability. We have no
  free, verified source of nominee lists - `available: false`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import domestic_scorers, golden_boot_projection
from .models import Goalscorer, Team
from .serialize import latest_season

LOOKBACK_DAYS = 365
DOMESTIC_LEAGUES = [
    ("en.1", "Premier League"), ("es.1", "La Liga"), ("it.1", "Serie A"),
    ("de.1", "Bundesliga"), ("fr.1", "Ligue 1"),
]
ALL_LEAGUES = [*DOMESTIC_LEAGUES, ("CL", "UEFA Champions League")]


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


def _final_domestic_golden_boot(league_code: str) -> dict:
    if not domestic_scorers.available(league_code):
        return {
            "available": False,
            "reason": f"No scorer data for {domestic_scorers.SEASON_LABEL} from our free sources.",
        }
    return {
        "available": True,
        "season": domestic_scorers.SEASON_LABEL,
        "tag": "Final",
        "source": domestic_scorers.SOURCE,
        "top_scorers": domestic_scorers.league_top_scorers(league_code),
    }


def golden_boot_for_league(session: Session, league_code: str, season: str) -> dict:
    """Never silently substitutes a different season - a season either has real data
    (current, live; or the one past season we have a real cache for) or it says so."""
    current = latest_season(session, league_code)
    if current is not None and season == current:
        result = golden_boot_projection.project(session, league_code)
        if result["available"]:
            result["tag"] = "Current season"
        return result
    if league_code != "CL" and season == domestic_scorers.SEASON_LABEL:
        return _final_domestic_golden_boot(league_code)
    return {"available": False, "reason": f"No scorer data for {season} from our free sources."}


def get_awards(session: Session, season: str | None = None) -> dict:
    current_season = latest_season(session, "en.1")
    resolved_season = season or current_season or "unknown"
    by_league = {code: golden_boot_for_league(session, code, resolved_season) for code, _ in ALL_LEAGUES}

    result: dict = {
        "season": resolved_season,
        "available_seasons": None,  # filled by the route from the standings endpoint's list
        "golden_boot": {
            "available": any(v["available"] for v in by_league.values()),
            "by_league": by_league,
        },
        "ballon_dor": {
            "available": False,
            "reason": "Needs real historical Ballon d'Or voting data to train anything honest - "
                      "no free, verified dataset of past voting results was found. Not simulated "
                      "or guessed.",
        },
        "puskas": {
            "available": False,
            "reason": "Judging the Puskás Award means assessing a goal's technical/aesthetic "
                      "quality - something box-score data (scorer, minute, scoreline) simply "
                      "can't measure, and we have no free, verified source of nominee lists or "
                      "official goal video links either. Not fabricated.",
        },
    }
    if season is None:
        scorers = international_top_scorers(session)
        result["golden_boot"]["international_top_scorers_also_available"] = {
            "reason": f"Also showing a real international top-scorers leaderboard (last "
                      f"{LOOKBACK_DAYS} days, from martj42/international_results' "
                      "goalscorers.csv) - NOT a Golden Boot (that's domestic-only), included "
                      "for context.",
            "international_top_scorers": scorers,
            "lookback_days": LOOKBACK_DAYS,
        }
    return result
