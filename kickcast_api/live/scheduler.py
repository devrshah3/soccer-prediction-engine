"""Starts the live-polling background job, only if API_FOOTBALL_KEY is set. Called once
from kickcast_api.main's startup - this is the ONLY place poller.poll_live_matches runs
from, never a request handler."""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from ..db import SessionLocal
from . import api_football
from .poller import POLL_INTERVAL_MINUTES, poll_live_matches
from .results_updater import POLL_INTERVAL_MINUTES as RESULTS_POLL_INTERVAL_MINUTES
from .results_updater import update_todays_results

_scheduler: BackgroundScheduler | None = None


def _job() -> None:
    session = SessionLocal()
    try:
        poll_live_matches(session)
    finally:
        session.close()


def _results_job() -> None:
    session = SessionLocal()
    try:
        update_todays_results(session)  # no-op outside a match window - see its own docstring
    finally:
        session.close()


def start() -> BackgroundScheduler | None:
    global _scheduler
    if not api_football.available():
        return None  # no key - nothing to poll, don't start a scheduler that would no-op forever
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_job, "interval", minutes=POLL_INTERVAL_MINUTES, id="poll_live_matches")
    _scheduler.add_job(_results_job, "interval", minutes=RESULTS_POLL_INTERVAL_MINUTES, id="update_todays_results")
    _scheduler.start()
    return _scheduler


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
