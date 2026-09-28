from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from kickcast_engine.models.goal_timing import goal_timing_windows

from .. import domestic_scorers
from ..cards import get_card_model
from ..db import get_session
from ..models import Goalscorer, Match
from ..predictions import get_model, get_model_computed_at
from ..scorers import team_likely_scorers
from ..serialize import match_dict, team_names

router = APIRouter(prefix="/matches", tags=["matches"])


def _get_match(session: Session, match_id: int) -> Match:
    m = session.get(Match, match_id)
    if m is None:
        raise HTTPException(404, f"unknown match {match_id!r}")
    return m


@router.get("/{match_id}")
def match_detail(match_id: int, session: Session = Depends(get_session)) -> dict:
    m = _get_match(session, match_id)
    result = match_dict(session, m)
    if m.status == "finished":
        # Only queried on the single-match detail endpoint, never in match_dict() itself
        # (used by every list-returning endpoint) - a per-row Goalscorer query there would
        # reintroduce the N+1 fan-out already fixed once for the homepage (see batch.py).
        # Goalscorer.match_id is only populated for international matches (see
        # scripts/ingest.py's ingest_goalscorers) - a domestic match honestly comes back
        # with an empty list, never a guessed one.
        events = (
            session.query(Goalscorer)
            .filter(Goalscorer.match_id == match_id)
            .order_by(Goalscorer.minute.asc())
            .all()
        )
        result["goal_events"] = [
            {
                "team_id": e.team_id, "scorer": e.scorer_name, "minute": e.minute,
                "own_goal": e.own_goal, "penalty": e.penalty,
            }
            for e in events
        ]
    return result


@router.get("/{match_id}/prediction")
def match_prediction(match_id: int, session: Session = Depends(get_session)) -> dict:
    m = _get_match(session, match_id)
    model = get_model(session, m.league_code)
    if model is None:
        raise HTTPException(
            503, f"not enough finished-match history for {m.league_code!r} to fit a model yet"
        )
    pred = model.predict(m.home_team_id, m.away_team_id, neutral=m.neutral)
    pred["computed_at"] = get_model_computed_at(session, m.league_code)
    names = team_names(session, {m.home_team_id, m.away_team_id})
    pred["home_team"] = {"id": m.home_team_id, "name": names.get(m.home_team_id, m.home_team_id)}
    pred["away_team"] = {"id": m.away_team_id, "name": names.get(m.away_team_id, m.away_team_id)}
    pred["match_status"] = m.status

    total_xg = pred["expected_goals"]["home"] + pred["expected_goals"]["away"]
    pred["goal_timing"] = goal_timing_windows(total_xg)

    if m.league_code == "international":
        pred["likely_scorers"] = {
            "available": True,
            "method": "historical scoring share over the last 3 years, NOT squad-sheet or "
                      "fitness/rotation-aware - a real-data approximation, not a lineup prediction",
            "home": team_likely_scorers(session, m.home_team_id, m.date, pred["expected_goals"]["home"]),
            "away": team_likely_scorers(session, m.away_team_id, m.date, pred["expected_goals"]["away"]),
        }
    elif domestic_scorers.available(m.league_code):
        pred["likely_scorers"] = {
            "available": True,
            "method": f"share of the {domestic_scorers.SEASON_LABEL} season's real goal total "
                      "(API-Football free tier - NOT the current season, that needs a paid plan; "
                      "NOT squad-sheet or fitness/rotation-aware) times this match's expected goals",
            "source": domestic_scorers.SOURCE,
            "home": domestic_scorers.team_likely_scorers(m.league_code, m.home_team_id, pred["expected_goals"]["home"]),
            "away": domestic_scorers.team_likely_scorers(m.league_code, m.away_team_id, pred["expected_goals"]["away"]),
        }
    else:
        pred["likely_scorers"] = {
            "available": False,
            "reason": "no per-player data source available for this competition",
            "home": [], "away": [],
        }

    card_model = get_card_model(session, m.league_code)
    if card_model is not None:
        pred["cards"] = {
            "available": True,
            "home": card_model.predict(m.home_team_id, True),
            "away": card_model.predict(m.away_team_id, False),
        }
    else:
        pred["cards"] = {
            "available": False,
            "reason": "no card data source for this competition yet" if m.league_code == "international"
                      else "not enough card history to fit a model yet",
        }
    return pred
