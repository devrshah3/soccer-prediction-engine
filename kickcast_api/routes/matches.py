from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_module

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from kickcast_engine.models.goal_timing import goal_timing_windows

from .. import domestic_scorers
from ..cards import get_card_model
from ..db import get_session
from ..models import Goalscorer, Match
from ..precompute import get_precomputed_prediction
from ..predictions import get_model, get_model_computed_at
from ..scorers import team_likely_scorers
from ..serialize import match_dict, team_names

router = APIRouter(prefix="/matches", tags=["matches"])

# B.8: matches further out than this get a "long-range" note (form/team news can change);
# further than this, a "date may change" note too (no real "provisional" flag exists in
# our data yet - see this module's date_may_change comment below).
LONG_RANGE_DAYS = 14
DATE_MAY_CHANGE_DAYS = 28


def _get_match(session: Session, match_id: int) -> Match:
    m = session.get(Match, match_id)
    if m is None:
        raise HTTPException(404, f"unknown match {match_id!r}")
    return m


@router.get("")
def matches_by_date(date: str, league: str | None = None, session: Session = Depends(get_session)) -> list[dict]:
    """B.8: every match on a given local date (grouping by competition/league filtering
    is a frontend concern - it already has /leagues to cross-reference league_code). A
    scheduled match's prediction is served from the precompute store when one exists;
    if not (a fixture added after the last precompute run), it's computed live rather
    than silently omitted. A finished match's real result is returned instead."""
    try:
        target_date = date_module.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD") from None

    q = session.query(Match).filter(Match.date == target_date)
    if league:
        q = q.filter(Match.league_code == league)
    matches = q.order_by(Match.kickoff.asc()).all()

    today = datetime.now(UTC).date()
    days_out = (target_date - today).days
    out = []
    for m in matches:
        row = match_dict(session, m)
        if m.status == "scheduled":
            pred = get_precomputed_prediction(session, m.id)
            if pred is None:
                model = get_model(session, m.league_code)
                if model is not None:
                    pred = model.predict(m.home_team_id, m.away_team_id, neutral=m.neutral)
                    pred["computed_at"] = get_model_computed_at(session, m.league_code)
            row["prediction"] = pred
            row["long_range"] = days_out > LONG_RANGE_DAYS
            # "or it's more than 4 weeks away" (the brief's other trigger, a source
            # marking a fixture provisional, isn't something any of our sources expose -
            # not fabricated here).
            row["date_may_change"] = days_out > DATE_MAY_CHANGE_DAYS
        out.append(row)
    return out


@router.get("/nearby-date")
def nearby_match_date(date: str, direction: str = "forward", session: Session = Depends(get_session)) -> dict:
    """The nearest OTHER date (not `date` itself) with at least one match on record.
    direction="forward" (B.5's automatic rollover: the next date with matches, tomorrow
    or the next matchday) only looks ahead. direction="nearest" (B.6's empty-date
    recovery link) looks both ways and returns whichever is closer."""
    try:
        target = date_module.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD") from None
    if direction not in ("forward", "nearest"):
        raise HTTPException(400, "direction must be 'forward' or 'nearest'")

    forward_row = (
        session.query(Match.date)
        .filter(Match.date > target, Match.status.in_(["scheduled", "finished"]))
        .order_by(Match.date.asc())
        .first()
    )
    if direction == "forward":
        return {"date": forward_row[0].isoformat() if forward_row else None}

    backward_row = (
        session.query(Match.date)
        .filter(Match.date < target, Match.status.in_(["scheduled", "finished"]))
        .order_by(Match.date.desc())
        .first()
    )
    candidates = []
    if forward_row:
        candidates.append((abs((forward_row[0] - target).days), forward_row[0]))
    if backward_row:
        candidates.append((abs((target - backward_row[0]).days), backward_row[0]))
    if not candidates:
        return {"date": None}
    candidates.sort(key=lambda c: c[0])
    return {"date": candidates[0][1].isoformat()}


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
