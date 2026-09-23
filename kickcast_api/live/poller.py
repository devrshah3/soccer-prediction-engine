"""Polls API-Football into our own DB on a schedule - never called from a request
handler. This is what makes the live data honestly "2-5 min delayed": we poll every 3
minutes, and every live UI element shows `last_updated_at` so the delay is visible, not
hidden, per the ground rules.

Matching an API-Football fixture to one of our Match rows is BEST-EFFORT team-name
matching (substring, case-insensitive) - we have no verified API-Football<->kickcast
team-ID crosswalk (building one needs real API-Football responses to see its actual
name spellings, which needs a key). Flagged in MORNING_REPORT.md.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import LiveEvent, LiveMatchState, Match, Team
from . import api_football

POLL_INTERVAL_MINUTES = 3


def _find_match(session: Session, home_name: str | None, away_name: str | None) -> Match | None:
    if not home_name or not away_name:
        return None
    today = datetime.now(timezone.utc).date()
    candidates = session.query(Match).filter(Match.date == today).all()
    for m in candidates:
        home_team = session.get(Team, m.home_team_id)
        away_team = session.get(Team, m.away_team_id)
        if not home_team or not away_team:
            continue
        if _names_match(home_name, home_team.name) and _names_match(away_name, away_team.name):
            return m
    return None


def _names_match(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    return a in b or b in a


def poll_live_matches(session: Session) -> int:
    """One batched call for all live fixtures (events included - see api_football.py's
    module docstring for why a second per-match call isn't needed); updates
    LiveMatchState + LiveEvent for whichever ones we can match to a tracked Match.
    Returns how many were updated (0 if no key/quota/network error - a genuine no-op,
    not an error)."""
    fixtures = api_football.fetch_live_fixtures(session)
    if fixtures is None:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    for fx in fixtures:
        home_name, away_name = fx.get("home_team_name"), fx.get("away_team_name")
        m = _find_match(session, home_name, away_name)
        if m is None:
            continue
        state = session.get(LiveMatchState, m.id)
        if state is None:
            state = LiveMatchState(match_id=m.id, source="api-football", match_status="unknown")
            session.add(state)
        state.minute = fx.get("minute")
        state.home_score = fx.get("home_score")
        state.away_score = fx.get("away_score")
        state.match_status = fx.get("match_status") or "unknown"
        state.last_updated_at = now
        _sync_events(session, m, fx.get("events") or [])
        updated += 1
    session.commit()
    return updated


def _sync_events(session: Session, m: Match, events: list[dict]) -> None:
    """API-Football's embedded events list is the full authoritative list for the match
    as of this poll, not a delta - replace what we had rather than appending, so a VAR
    reversal or corrected minute is reflected too."""
    home_team = session.get(Team, m.home_team_id)
    away_team = session.get(Team, m.away_team_id)
    session.query(LiveEvent).filter(LiveEvent.match_id == m.id).delete()
    for e in events:
        team_name = e.get("team_name")
        team_id = None
        if team_name and home_team and _names_match(team_name, home_team.name):
            team_id = m.home_team_id
        elif team_name and away_team and _names_match(team_name, away_team.name):
            team_id = m.away_team_id
        session.add(
            LiveEvent(
                match_id=m.id,
                minute=e.get("minute") or 0,
                event_type=e.get("event_type") or "other",
                team_id=team_id,
                player=e.get("player"),
                detail=e.get("detail"),
                source="api-football",
            )
        )
