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

import logging
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
CATCHUP_AFTER_KICKOFF_MINUTES = 72 * 60
LATE_CHECK_GAP_MINUTES = 30  # per date, while the match is < 12h past kickoff
OLD_LATE_CHECK_GAP_MINUTES = 6 * 60  # per date, once it's older than that
# Keep this many calls in reserve for live polling when fetching per-match events.
EVENTS_QUOTA_RESERVE = 15

_last_date_call: dict[str, datetime] = {}  # date -> when we last asked API-Football for it

_FINISHED_CODES = {"FT", "AET", "PEN"}

def _todays_candidate_matches(session: Session, today: str) -> list[Match]:
    return (
        session.query(Match)
        .filter(Match.date == today, or_(Match.status == "scheduled", Match.status == "finished", Match.status == "not_played"))
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


UNRESOLVED_STATUSES = ("scheduled", "not_played")  # ingest relabels a stale 'scheduled' row 'not_played'


def dates_needing_check(session: Session, now: datetime, last_calls: dict[str, datetime] | None = None) -> list[str]:
    """Dates worth one date-scoped API call right now: today if a match of ours is in its
    normal window; plus any of the last few days that still hold a match past kickoff that
    never got its final status (catch-up - covers a server that was down, an exhausted
    quota, or matches around midnight UTC). Catch-up asks are spaced per date so an
    unresolvable match (postponed, unmapped) can't drain the shared 100/day budget."""
    last_calls = _last_date_call if last_calls is None else last_calls
    dates: list[str] = []
    today = now.date().isoformat()
    if in_match_window(session, now):
        dates.append(today)
    for back in range(4):
        day = (now - timedelta(days=back)).date().isoformat()
        if day in dates:
            continue
        ages = [
            mins
            for m in _todays_candidate_matches(session, day)
            if m.status in UNRESOLVED_STATUSES
            and (mins := _minutes_since_kickoff(m, now)) is not None
            and WINDOW_AFTER_KICKOFF_MINUTES < mins <= CATCHUP_AFTER_KICKOFF_MINUTES
        ]
        if not ages:
            continue
        gap = LATE_CHECK_GAP_MINUTES if min(ages) < 12 * 60 else OLD_LATE_CHECK_GAP_MINUTES
        last = last_calls.get(day)
        if last is None or (now - last).total_seconds() / 60 >= gap:
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
    updated = 0
    for day in dates_needing_check(session, now):
        fixtures = api_football.fetch_fixtures_by_date(session, day)
        if fixtures is None:
            continue
        _last_date_call[day] = now
        updated += _apply_fixtures(session, day, fixtures, now)
    return updated


log = logging.getLogger("uvicorn.error")  # so scheduled-job activity shows in the server log

_espn_last_date_call: dict[str, datetime] = {}


def update_results_from_espn(session: Session, now: datetime | None = None) -> int:
    """Same job as update_todays_results, from ESPN's keyless scoreboard - no daily quota, so it
    is what keeps scores flowing when API-Football's 100/day is spent. Returns rows changed."""
    from . import espn  # local: keeps the API-Football path importable without it

    now = now or datetime.now(timezone.utc)
    updated = 0
    for day in dates_needing_check(session, now, _espn_last_date_call):
        codes = {m.league_code for m in _todays_candidate_matches(session, day)}
        fixtures = espn.fetch_fixtures(day, codes)
        if fixtures is None:
            continue
        _espn_last_date_call[day] = now
        changed = _apply_fixtures(session, day, fixtures, now)
        log.info("results/espn: %s - %d fixtures from source, %d of our matches changed", day, len(fixtures), changed)
        updated += changed
    return updated


BACKFILL_DAYS = 14  # covers roughly two league matchweeks + the last international window
last_backfill: dict = {"at": None, "report": None}  # for /meta


def backfill_from_espn(session: Session, days: int = BACKFILL_DAYS, now: datetime | None = None) -> dict:
    """Re-read the last `days` days from ESPN for every competition we hold matches in, so a
    freshly built or freshly woken instance (Render's free disk resets to the build snapshot, which
    only has what the open sources had at build time) gets its recent results, scorers and cards
    straight away instead of waiting for a live window. Idempotent; a no-op when ESPN is disabled."""
    from . import espn

    now = now or datetime.now(timezone.utc)
    report = {"days": 0, "fixtures": 0, "changed": 0}
    if not espn.available():
        return report
    for back in range(days + 1):
        day = (now - timedelta(days=back)).date().isoformat()
        codes = {m.league_code for m in _todays_candidate_matches(session, day)}
        if not codes:
            continue
        fixtures = espn.fetch_fixtures(day, codes)
        if fixtures is None:
            continue
        report["days"] += 1
        report["fixtures"] += len(fixtures)
        report["changed"] += _apply_fixtures(session, day, fixtures, now)
    last_backfill.update(at=now.isoformat(), report=dict(report))
    log.info("results/espn backfill: %s", report)
    return report


def _apply_fixtures(session: Session, day: str, fixtures: list[dict], now: datetime) -> int:
    candidates = _todays_candidate_matches(session, day)
    now_iso = now.isoformat()
    updated = 0
    for fx in fixtures:
        m = find_match(session, candidates, fx)
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
            if not fx.get("events_authoritative"):
                _fetch_final_events(session, m, fx)
        elif status not in _FINISHED_CODES and (m.home_goals != home_score or m.away_goals != away_score) and home_score is not None:
            # still in progress, but a live score is available and differs - update the
            # score without marking finished yet.
            m.home_goals = home_score
            m.away_goals = away_score
            changed = True

        source = fx.get("source") or "api-football-date-poll"
        if fx.get("events_authoritative"):
            # complete as of this poll (even an empty list = 0-0): replace what we hold, so a new
            # goal appears - and a VAR-cancelled one disappears - on the very next poll.
            sync_events(session, m, fx.get("events") or [], source=source)

        state = session.get(LiveMatchState, m.id)
        if state is None:
            state = LiveMatchState(match_id=m.id, source=source, match_status=status or "unknown")
            session.add(state)
        state.minute = fx.get("minute")
        state.home_score = home_score
        state.away_score = away_score
        state.match_status = status or "unknown"
        state.last_updated_at = now_iso
        state.source = source

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


__all__ = ["POLL_INTERVAL_MINUTES", "backfill_from_espn", "dates_needing_check", "in_match_window", "needs_result_check", "update_results_from_espn", "update_todays_results"]
