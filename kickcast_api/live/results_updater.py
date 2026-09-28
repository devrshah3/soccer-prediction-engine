"""A3: keeps our own Match rows' status/score current during a match window, using
API-Football's date-scoped /fixtures endpoint (one call = every match worldwide that
day - cheap on the shared 100/day budget). This is different from poller.py's
/fixtures?live=all polling, which only ever writes to the separate LiveMatchState/
LiveEvent tables and never touches the canonical Match row - a match could finish there
and Match.status would still say "scheduled" until the next full ingest.py run (daily at
most). This module updates Match.status/home_goals/away_goals directly, the moment
API-Football reports "Match Finished", and still upserts LiveMatchState too so "result
updated X min ago" has a real timestamp to show.

Only ever called from a scheduled job (see scheduler.py), never a request handler, and
only makes the real API call when `_in_match_window` says something of ours could
plausibly need updating right now - not on every scheduler tick.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from kickcast_engine.data.api_football_crosswalk import load_team_crosswalk

from ..models import LiveMatchState, Match
from . import api_football

POLL_INTERVAL_MINUTES = 10
# A match "could need updating" from just before its earliest realistic kickoff to well
# after its latest realistic finish - matches poller.py's own in-progress window (135
# min, see matchState.ts on the frontend) plus a margin either side.
WINDOW_BEFORE_KICKOFF_MINUTES = 15
WINDOW_AFTER_KICKOFF_MINUTES = 150

_FINISHED_CODES = {"FT", "AET", "PEN"}
CROSSWALK_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "api_football_cache"

_crosswalk: dict[int, str] | None = None


def _team_crosswalk() -> dict[int, str]:
    global _crosswalk
    if _crosswalk is None:
        _crosswalk = load_team_crosswalk(CROSSWALK_CACHE_DIR) if CROSSWALK_CACHE_DIR.exists() else {}
    return _crosswalk


def _todays_candidate_matches(session: Session, today: str) -> list[Match]:
    return (
        session.query(Match)
        .filter(Match.date == today, or_(Match.status == "scheduled", Match.status == "finished"))
        .all()
    )


def in_match_window(session: Session, now: datetime | None = None) -> bool:
    """True if at least one of our own matches today has a kickoff within
    [-15min, +150min] of now - i.e. about to start, in progress, or recently finished
    and possibly not yet reflected. Avoids spending a real API call when nothing of ours
    could plausibly be affected (night hours, rest days between matchdays)."""
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    for m in _todays_candidate_matches(session, today):
        if not m.kickoff:
            continue
        try:
            kickoff_dt = datetime.strptime(f"{m.date} {m.kickoff}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        delta_min = (now - kickoff_dt).total_seconds() / 60
        if -WINDOW_BEFORE_KICKOFF_MINUTES <= delta_min <= WINDOW_AFTER_KICKOFF_MINUTES:
            return True
    return False


def _find_match(session: Session, candidates: list[Match], fx: dict) -> Match | None:
    crosswalk = _team_crosswalk()
    home_af_id, away_af_id = fx.get("home_team_id"), fx.get("away_team_id")
    home_kc_id = crosswalk.get(home_af_id) if isinstance(home_af_id, int) else None
    away_kc_id = crosswalk.get(away_af_id) if isinstance(away_af_id, int) else None
    if home_kc_id and away_kc_id:
        for m in candidates:
            if m.home_team_id == home_kc_id and m.away_team_id == away_kc_id:
                return m
        return None  # crosswalk resolved both teams but no matching fixture today - don't fuzzy-match, that risks a wrong pairing
    return None  # no fallback name matching here - a wrong match would silently corrupt a real score


def update_todays_results(session: Session, now: datetime | None = None) -> int:
    """Returns how many of our Match rows were updated (0 if outside a match window,
    no key/quota, or a network error - all genuine no-ops, never an exception)."""
    now = now or datetime.now(timezone.utc)
    if not in_match_window(session, now):
        return 0
    today = now.date().isoformat()
    fixtures = api_football.fetch_fixtures_by_date(session, today)
    if fixtures is None:
        return 0

    candidates = _todays_candidate_matches(session, today)
    now_iso = now.isoformat()
    updated = 0
    for fx in fixtures:
        m = _find_match(session, candidates, fx)
        if m is None:
            continue
        status = fx.get("match_status")
        home_score, away_score = fx.get("home_score"), fx.get("away_score")
        changed = False
        if status in _FINISHED_CODES and (m.status != "finished" or m.home_goals != home_score or m.away_goals != away_score):
            m.status = "finished"
            m.home_goals = home_score
            m.away_goals = away_score
            changed = True
        elif status not in _FINISHED_CODES and (m.home_goals != home_score or m.away_goals != away_score) and home_score is not None:
            # still in progress, but a live score is available and differs - update the
            # score without marking finished yet.
            m.home_goals = home_score
            m.away_goals = away_score
            changed = True

        state = session.get(LiveMatchState, m.id)
        if state is None:
            state = LiveMatchState(match_id=m.id, source="api-football-date-poll", match_status=status or "unknown")
            session.add(state)
        state.minute = fx.get("minute")
        state.home_score = home_score
        state.away_score = away_score
        state.match_status = status or "unknown"
        state.last_updated_at = now_iso
        state.source = "api-football-date-poll"

        if changed:
            updated += 1
    session.commit()
    return updated


__all__ = ["POLL_INTERVAL_MINUTES", "in_match_window", "update_todays_results"]
