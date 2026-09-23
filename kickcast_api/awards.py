"""Awards: built honestly against what data actually exists.

- Golden Boot: traditionally a DOMESTIC league season award. We have no free, keyless
  per-player domestic scoring data (same gap as kickcast_engine.models.goalscorers -
  see that module's docstring), so it's `available: false` for any domestic league.
  We DO have real per-player international goal data (data/goalscorers.csv), so we
  report an international top-scorers leaderboard instead - explicitly NOT labeled
  "Golden Boot" (that's a different, specific award this isn't standing in for).
- Ballon d'Or / The Best: needs real historical voting data to train anything honest.
  No free, verified dataset of past voting results was found - `available: false`
  rather than a model trained on nothing.
- Puskas: the spec wants nominees + official video links, no probability. We have no
  free, verified source of nominee lists - `available: false`.

All three are structured so a real data source can be plugged in later without changing
the API shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import Goalscorer, Team

LOOKBACK_DAYS = 365


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


def get_awards(session: Session) -> dict:
    scorers = international_top_scorers(session)
    return {
        "golden_boot": {
            "available": False,
            "reason": "Golden Boot is a domestic-league award; we have no free, keyless "
                      "per-player domestic scoring data source (checked football-data.co.uk "
                      "and openfootball - neither has it; API-Football's free tier needs a key "
                      "we don't have). Showing a real international top-scorers leaderboard "
                      f"instead (last {LOOKBACK_DAYS} days, from martj42/international_results' "
                      "goalscorers.csv) - NOT the same thing as a Golden Boot.",
            "international_top_scorers": scorers,
            "lookback_days": LOOKBACK_DAYS,
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
