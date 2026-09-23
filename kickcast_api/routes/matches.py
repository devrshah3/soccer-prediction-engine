from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Match
from ..predictions import get_model
from ..serialize import match_dict, team_names

router = APIRouter(prefix="/matches", tags=["matches"])


def _get_match(session: Session, match_id: int) -> Match:
    m = session.get(Match, match_id)
    if m is None:
        raise HTTPException(404, f"unknown match {match_id!r}")
    return m


@router.get("/{match_id}")
def match_detail(match_id: int, session: Session = Depends(get_session)) -> dict:
    return match_dict(session, _get_match(session, match_id))


@router.get("/{match_id}/prediction")
def match_prediction(match_id: int, session: Session = Depends(get_session)) -> dict:
    m = _get_match(session, match_id)
    model = get_model(session, m.league_code)
    if model is None:
        raise HTTPException(
            503, f"not enough finished-match history for {m.league_code!r} to fit a model yet"
        )
    pred = model.predict(m.home_team_id, m.away_team_id, neutral=m.neutral)
    names = team_names(session, {m.home_team_id, m.away_team_id})
    pred["home_team"] = {"id": m.home_team_id, "name": names.get(m.home_team_id, m.home_team_id)}
    pred["away_team"] = {"id": m.away_team_id, "name": names.get(m.away_team_id, m.away_team_id)}
    pred["match_status"] = m.status
    return pred
