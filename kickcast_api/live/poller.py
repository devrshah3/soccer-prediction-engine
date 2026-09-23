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

from ..models import LiveMatchState, Match, Team
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
    """One batched call for all live fixtures; updates LiveMatchState for whichever ones
    we can match to a tracked Match. Returns how many were updated (0 if no key/quota/
    network error - a genuine no-op, not an error)."""
    fixtures = api_football.fetch_live_fixtures(session)
    if fixtures is None:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    for fx in fixtures:
        m = _find_match(session, fx.get("home_team_name"), fx.get("away_team_name"))
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
        updated += 1
    session.commit()
    return updated
