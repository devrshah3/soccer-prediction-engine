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

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import LiveMatchState, Match
from . import api_football, quota
from .matching import find_match, sync_events

POLL_INTERVAL_MINUTES = 10
# A match "could need updating" from just before its earliest realistic kickoff to well
# after its latest realistic finish - matches poller.py's own in-progress window (135
# min, see matchState.ts on the frontend) plus a margin either side.
WINDOW_BEFORE_KICKOFF_MINUTES = 15
WINDOW_AFTER_KICKOFF_MINUTES = 150
# Finalization catch-up: a match that never got its final status (server was down, quota
# ran out, source lag) keeps being checked up to this long after kickoff - but at most one
# date call per LATE_CHECK_GAP_MINUTES once it's past the normal window, so an
# unresolvable match (postponed, unmapped) can't drain the shared 100/day budget.
CATCHUP_AFTER_KICKOFF_MINUTES = 12 * 60
LATE_CHECK_GAP_MINUTES = 30
# Keep this many calls in reserve for live polling when fetching per-match events.
EVENTS_QUOTA_RESERVE = 15

_last_date_call: datetime | None = None

_FINISHED_CODES = {"FT", "AET", "PEN"}

def _todays_candidate_matches(session: Session, today: str) -> list[Match]:
    return (
        session.query(Match)
        .filter(Match.date == today, or_(Match.status == "scheduled", Match.status == "finished"))
        .all()
    )


def _minutes_since_kickoff(m: Match, now: datetime) -> float | None:
    if not m.kickoff:
        return None
    try:
        kickoff_dt = datetime.strptime(f"{m.date} {m.kickoff}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (now - kickoff_dt).total_seconds() / 60


def dates_needing_check(session: Session, now: datetime) -> list[str]:
    """Dates worth one date-scoped API call right now. Today, if a match of ours is in its
    normal window; plus today AND yesterday when a match is past kickoff but never got its
    final status (catch-up, spaced LATE_CHECK_GAP_MINUTES apart) - yesterday matters for
    anything that finished or was missed around midnight UTC, or before the daily quota reset."""
    dates: list[str] = []
    today = now.date().isoformat()
    if in_match_window(session, now):
        dates.append(today)
    gap_ok = _last_date_call is None or (now - _last_date_call).total_seconds() / 60 >= LATE_CHECK_GAP_MINUTES
    if gap_ok:
        for day in (today, (now - timedelta(days=1)).date().isoformat()):
            if day in dates:
                continue
            if any(
                m.status == "scheduled" and (mins := _minutes_since_kickoff(m, now)) is not None
                and WINDOW_AFTER_KICKOFF_MINUTES < mins <= CATCHUP_AFTER_KICKOFF_MINUTES
                for m in _todays_candidate_matches(session, day)
            ):
                dates.append(day)
    return dates


def needs_result_check(session: Session, now: datetime) -> bool:
    return bool(dates_needing_check(session, now))


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


def update_todays_results(session: Session, now: datetime | None = None) -> int:
    """Returns how many of our Match rows were updated (0 if outside a match window,
    no key/quota, or a network error - all genuine no-ops, never an exception)."""
    now = now or datetime.now(timezone.utc)
    global _last_date_call
    updated = 0
    for day in dates_needing_check(session, now):
        fixtures = api_football.fetch_fixtures_by_date(session, day)
        if fixtures is None:
            continue
        _last_date_call = now
        updated += _apply_fixtures(session, day, fixtures, now)
    return updated


def _apply_fixtures(session: Session, day: str, fixtures: list[dict], now: datetime) -> int:
    candidates = _todays_candidate_matches(session, day)
    now_iso = now.isoformat()
    updated = 0
    for fx in fixtures:
        m = find_match(candidates, fx)
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
            _fetch_final_events(session, m, fx)
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


def _fetch_final_events(session: Session, m: Match, fx: dict) -> None:
    """A match just went final: capture its complete goal/card list once (1 call), unless the
    date response already embedded events or the shared budget is nearly spent."""
    events = fx.get("events") or []
    if not events and fx.get("fixture_id") and quota.api_football_quota_remaining(session) > EVENTS_QUOTA_RESERVE:
        events = api_football.fetch_events(session, fx["fixture_id"]) or []
    if events:
        sync_events(session, m, events)


__all__ = ["POLL_INTERVAL_MINUTES", "dates_needing_check", "in_match_window", "needs_result_check", "update_todays_results"]
