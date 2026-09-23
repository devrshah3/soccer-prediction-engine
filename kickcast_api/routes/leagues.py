from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import League, Match
from ..serialize import latest_season, match_dict, seasons, standings
from ..trophy_odds import get_trophy_odds

router = APIRouter(prefix="/leagues", tags=["leagues"])


def _get_league(session: Session, code: str) -> League:
    league = session.get(League, code)
    if league is None:
        raise HTTPException(404, f"unknown league {code!r}")
    return league


@router.get("")
def list_leagues(session: Session = Depends(get_session)) -> list[dict]:
    return [
        {"code": lg.code, "name": lg.name, "country": lg.country, "kind": lg.kind}
        for lg in session.query(League).order_by(League.kind, League.name).all()
    ]


@router.get("/{code}/standings")
def league_standings(code: str, season: str | None = None, session: Session = Depends(get_session)) -> dict:
    _get_league(session, code)
    all_seasons = seasons(session, code)
    if season is None:
        season = latest_season(session, code)
    if season not in all_seasons:
        raise HTTPException(404, f"no data for {code!r} season {season!r}. available: {all_seasons}")
    return {"league_code": code, "season": season, "available_seasons": all_seasons,
            "table": standings(session, code, season)}


@router.get("/{code}/fixtures")
def league_fixtures(
    code: str, status: str = "scheduled", limit: int = 50, session: Session = Depends(get_session)
) -> list[dict]:
    _get_league(session, code)
    if status not in ("scheduled", "finished", "all"):
        raise HTTPException(400, "status must be 'scheduled', 'finished', or 'all'")
    q = session.query(Match).filter(Match.league_code == code)
    if status != "all":
        q = q.filter(Match.status == status)
    order = Match.date.asc() if status != "finished" else Match.date.desc()
    matches = q.order_by(order).limit(limit).all()
    return [match_dict(session, m) for m in matches]


@router.get("/{code}/trophy-odds")
def league_trophy_odds(code: str, season: str | None = None, session: Session = Depends(get_session)) -> dict:
    _get_league(session, code)
    odds = get_trophy_odds(session, code, season)
    if odds is None:
        raise HTTPException(
            503, f"not enough data yet to simulate {code!r}"
            + (f" season {season!r}" if season else "")
        )
    return odds
