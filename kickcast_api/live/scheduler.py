"""Background jobs, started once from kickcast_api.main's startup - the ONLY place any of
these run from, never a request handler.

Two kinds:
  - API-Football-dependent (live polling, the date-scoped results updater): only added if
    API_FOOTBALL_KEY is set - no key, nothing to poll.
  - Everything else (nightly prediction precompute): always scheduled, no external key
    needed - our own DB + model only.
"""

from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .. import build, catchup, settings
from ..db import SessionLocal
from . import api_football, espn
from .poller import POLL_INTERVAL_MINUTES, poll_live_matches
from .results_updater import POLL_INTERVAL_MINUTES as RESULTS_POLL_INTERVAL_MINUTES
from .results_updater import backfill_from_espn, update_results_from_espn, update_todays_results

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


def _espn_job() -> None:
    session = SessionLocal()
    try:
        update_results_from_espn(session)  # no-op outside a match window / catch-up need
    finally:
        session.close()


def _espn_backfill_job() -> None:
    session = SessionLocal()
    try:
        backfill_from_espn(session)
    finally:
        session.close()


def _nightly_build_job() -> None:
    """The ONLY place (besides the build step) that refits models and reruns the Monte Carlo."""
    session = SessionLocal()
    try:
        build.build_everything(session, network=settings.enable_football_data_org())
    finally:
        session.close()


def _scorers_job() -> None:
    """Refresh the Golden Boot projections every few hours while awake (football-data.org's 10 calls
    per minute are respected by its client; the scorer cache has a 6-hour TTL, so this is at most
    6 calls per run)."""
    if not settings.enable_football_data_org():
        return
    session = SessionLocal()
    try:
        build.build_golden_boot(session, network=True)
    finally:
        session.close()


def _catchup_job() -> None:
    catchup.run_catchup()


def start() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600})
    _scheduler.add_job(
        _nightly_build_job, CronTrigger(hour=NIGHTLY_PRECOMPUTE_HOUR_UTC, minute=0), id="nightly_build"
    )
    if settings.startup_catchup():
        # while the instance is awake: new results/fixtures/predictions every few hours
        _scheduler.add_job(_catchup_job, "interval", hours=catchup.MIN_AGE_HOURS, id="catchup_refresh")
        _scheduler.add_job(_scorers_job, "interval", hours=6, id="refresh_scorers")
    if api_football.available():
        _scheduler.add_job(_job, "interval", minutes=POLL_INTERVAL_MINUTES, id="poll_live_matches")
        _scheduler.add_job(_results_job, "interval", minutes=RESULTS_POLL_INTERVAL_MINUTES, id="update_todays_results")
    if espn.available():
        # keyless second results source - works when API-Football's daily quota is spent
        _scheduler.add_job(
            _espn_job, "interval", minutes=RESULTS_POLL_INTERVAL_MINUTES, id="update_results_espn", next_run_time=datetime.now(timezone.utc)
        )
        # One-off at startup: Render's free disk resets to the build snapshot, which only has what the
        # open sources knew at build time - pull the last week of results/scorers/cards straight away.
        _scheduler.add_job(_espn_backfill_job, id="espn_backfill_startup", next_run_time=datetime.now(timezone.utc))
    _scheduler.start()
    return _scheduler


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
