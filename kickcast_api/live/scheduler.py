"""Background jobs, started once from kickcast_api.main's startup - the ONLY place any of
these run from, never a request handler.

Two kinds:
  - API-Football-dependent (live polling, the date-scoped results updater): only added if
    API_FOOTBALL_KEY is set - no key, nothing to poll.
  - Everything else (nightly prediction precompute): always scheduled, no external key
    needed - our own DB + model only.
"""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..db import SessionLocal
from ..precompute import precompute_predictions
from . import api_football
from .poller import POLL_INTERVAL_MINUTES, poll_live_matches
from .results_updater import POLL_INTERVAL_MINUTES as RESULTS_POLL_INTERVAL_MINUTES
from .results_updater import update_todays_results

NIGHTLY_PRECOMPUTE_HOUR_UTC = 3  # low-traffic hour; the C.9 daily re-ingest should run before this

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


def _precompute_job() -> None:
    session = SessionLocal()
    try:
        precompute_predictions(session)
    finally:
        session.close()


def start() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _precompute_job, CronTrigger(hour=NIGHTLY_PRECOMPUTE_HOUR_UTC, minute=0), id="nightly_precompute_predictions"
    )
    if api_football.available():
        _scheduler.add_job(_job, "interval", minutes=POLL_INTERVAL_MINUTES, id="poll_live_matches")
        _scheduler.add_job(_results_job, "interval", minutes=RESULTS_POLL_INTERVAL_MINUTES, id="update_todays_results")
    _scheduler.start()
    return _scheduler


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
