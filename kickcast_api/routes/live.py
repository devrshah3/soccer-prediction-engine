"""Live match center: serves ONLY from data poller.py already wrote to the DB (never
fetches live on request - see kickcast_api/live/). Without API_FOOTBALL_KEY configured,
every match honestly reports `available: false` rather than guessing at a live state.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..live import api_football
from ..models import LiveEvent, LiveMatchState, Match

router = APIRouter(prefix="/matches", tags=["live"])


@router.get("/{match_id}/live")
def match_live_state(match_id: int, session: Session = Depends(get_session)) -> dict:
    if session.get(Match, match_id) is None:
        raise HTTPException(404, f"unknown match {match_id!r}")

    if not api_football.available():
        return {"available": False, "reason": "no API_FOOTBALL_KEY configured - live scores/events need it"}

    state = session.get(LiveMatchState, match_id)
    if state is None:
        return {"available": False, "reason": "no live data polled for this match yet (it may not be live right now)"}

    events = (
        session.query(LiveEvent)
        .filter(LiveEvent.match_id == match_id)
        .order_by(LiveEvent.minute.asc())
        .all()
    )
    updated = datetime.fromisoformat(state.last_updated_at)
    age_minutes = round((datetime.now(timezone.utc) - updated).total_seconds() / 60, 1)
    return {
        "available": True,
        "minute": state.minute,
        "home_score": state.home_score,
        "away_score": state.away_score,
        "match_status": state.match_status,
        "last_updated_at": state.last_updated_at,
        "updated_minutes_ago": age_minutes,
        "events": [
            {"minute": e.minute, "type": e.event_type, "team_id": e.team_id, "player": e.player, "detail": e.detail}
            for e in events
        ],
    }
