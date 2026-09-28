"""Polls API-Football into our own DB on a schedule - never called from a request
handler. This is what makes the live data honestly "2-5 min delayed": we poll every 3
minutes, and every live UI element shows `last_updated_at` so the delay is visible, not
hidden, per the ground rules.

Matching an API-Football fixture to one of our Match rows now prefers the REAL,
verified id crosswalk (kickcast_engine.data.api_football_crosswalk, built from real
/teams responses - 96/98 big-5 teams resolved automatically, 2 real naming-quirk
overrides, see that module's docstring) - unambiguous, unlike name matching. Falls back
to best-effort substring name matching only for a fixture whose API-Football team id
isn't in the crosswalk (e.g. a competition outside the big 5, or a team not in the
season=2024 snapshot the free tier's /teams gave us - a promoted/relegated club since
then, say) - this fallback is a real degradation, kept only so those fixtures aren't
silently dropped entirely.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import LiveMatchState, Match
from . import api_football
from .matching import find_match, sync_events
from .results_updater import in_match_window

# 10 min, and only inside a match window (see results_updater.in_match_window): the old
# unconditional 3-minute poll spent ~480 calls/day against API-Football's 100/day free
# budget, leaving nothing for the matches themselves by mid-morning.
POLL_INTERVAL_MINUTES = 10


def poll_live_matches(session: Session) -> int:
    """One batched call for all live fixtures (events included - see api_football.py's
    module docstring for why a second per-match call isn't needed); updates
    LiveMatchState + LiveEvent for whichever ones we can match to a tracked Match.
    Returns how many were updated (0 if no key/quota/network error - a genuine no-op,
    not an error)."""
    if not in_match_window(session):
        return 0
    fixtures = api_football.fetch_live_fixtures(session)
    if fixtures is None:
        return 0
    today = datetime.now(timezone.utc).date()
    candidates = session.query(Match).filter(Match.date == today).all()
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    for fx in fixtures:
        m = find_match(session, candidates, fx)
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
        sync_events(session, m, fx.get("events") or [])
        updated += 1
    session.commit()
    return updated
