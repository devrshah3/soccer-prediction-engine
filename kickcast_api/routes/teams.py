from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Match, Team
from ..serialize import latest_season, match_dict, standings, team_position

router = APIRouter(prefix="/teams", tags=["teams"])


def _get_team(session: Session, team_id: str) -> Team:
    team = session.get(Team, team_id)
    if team is None:
        raise HTTPException(404, f"unknown team {team_id!r}")
    return team


def _primary_league(session: Session, team_id: str) -> str | None:
    """The domestic league (not 'international') a team plays in most recently, if any."""
    row = (
        session.query(Match.league_code)
        .filter(or_(Match.home_team_id == team_id, Match.away_team_id == team_id), Match.league_code != "international")
        .order_by(Match.date.desc())
        .first()
    )
    return row[0] if row else None


def _team_matches(session: Session, team_id: str, status: str, limit: int) -> list[Match]:
    """The single query behind both a team's fixtures list and its "next match" - the
    latter used to be a separate ad-hoc query (status="scheduled", date ascending, no
    limit) that could disagree with this one. It did: a stale "scheduled" row (see A2's
    data cleanup) sorted before the real next match in that separate query but was
    already excluded by the same status handling here once cleaned up. "Next match" is
    now simply `_team_matches(..., "scheduled", 1)[0]` - the same list's first row, so
    the two can never diverge again."""
    q = session.query(Match).filter(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    if status != "all":
        q = q.filter(Match.status == status)
    order = Match.date.asc() if status == "scheduled" else Match.date.desc()
    return q.order_by(order).limit(limit).all()


@router.get("/{team_id}")
def team_detail(team_id: str, session: Session = Depends(get_session)) -> dict:
    team = _get_team(session, team_id)
    league_code = _primary_league(session, team_id)
    position, season = None, None
    if league_code:
        season = latest_season(session, league_code)
        position = team_position(session, league_code, season, team_id) if season else None

    upcoming = _team_matches(session, team_id, "scheduled", limit=1)
    next_match = upcoming[0] if upcoming else None
    recent_form = None
    if league_code and season:
        table = {row["team_id"]: row for row in standings(session, league_code, season)}
        recent_form = table.get(team_id, {}).get("form")

    return {
        "id": team.id, "name": team.name, "country": team.country,
        "league_code": league_code, "season": season, "position": position, "form": recent_form,
        "next_match": match_dict(session, next_match) if next_match else None,
    }


@router.get("/{team_id}/fixtures")
def team_fixtures(
    team_id: str, status: str = "all", limit: int = 100, session: Session = Depends(get_session)
) -> list[dict]:
    _get_team(session, team_id)
    if status not in ("scheduled", "finished", "all"):
        raise HTTPException(400, "status must be 'scheduled', 'finished', or 'all'")
    matches = _team_matches(session, team_id, status, limit)
    return [match_dict(session, m) for m in matches]
