"""DB-backed lookup feeding kickcast_engine.models.goalscorers. Only meaningful for
international matches - see that module's docstring for why domestic leagues are excluded.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from kickcast_engine.models.goalscorers import aggregate_goals, likely_scorers

from .models import Goalscorer

LOOKBACK_DAYS = 365 * 3


def team_likely_scorers(session: Session, team_id: str, before: date, expected_goals: float) -> list[dict]:
    since = before - timedelta(days=LOOKBACK_DAYS)
    rows = (
        session.query(Goalscorer)
        .filter(Goalscorer.team_id == team_id, Goalscorer.date >= since, Goalscorer.date < before)
        .all()
    )
    goals = aggregate_goals([(r.scorer_name, r.own_goal, r.penalty) for r in rows])
    return likely_scorers(goals, expected_goals)
