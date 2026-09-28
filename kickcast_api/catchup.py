"""Non-blocking catch-up refresh: new results, fixtures and predictions since the build.

Render's free instance sleeps after 15 minutes of no traffic and restarts from the BUILT state, so
on wake-up the database can be hours (or days) behind. The API starts serving immediately from the
built database and this runs in a background thread. It also runs every few hours while awake.

What it does - deliberately light, no model fitting (that is build/nightly only):
  1. download only the SMALL fresh sources (martj42 results/goalscorers CSVs, the current-season
     openfootball files) - a few MB, not the 29 MB archive;
  2. run scripts/ingest.py in a SUBPROCESS (its memory is returned to the OS when it exits) with
     INGEST_SKIP_PRECOMPUTE=1 - idempotent upserts, plus one football-data.org call for the
     Champions League when that source is enabled (well inside its 10/minute limit);
  3. precompute predictions in-process from the models that are already loaded.
API-Football is not touched here (its own budget-tracked jobs live in live/scheduler.py).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

from .db import SessionLocal
from .live.results_updater import backfill_from_espn
from .models import Meta
from .precompute import precompute_predictions

log = logging.getLogger("kickcast.catchup")
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
MIN_AGE_HOURS = 3  # a fresh build (or a recent catch-up) is not refreshed again straight away
_lock = threading.Lock()  # one refresh at a time

MARTJ42 = "https://raw.githubusercontent.com/martj42/international_results/master"
OPENFOOTBALL = "https://raw.githubusercontent.com/openfootball/football.json/master"
DOMESTIC_FILES = ["en.1.json", "es.1.json", "it.1.json", "de.1.json", "fr.1.json"]


def current_season_dir(today: datetime | None = None) -> str:
    """openfootball's season folder, e.g. '2026-27' (a season starts in July)."""
    now = today or datetime.now(UTC)
    start = now.year if now.month >= 7 else now.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def _download(url: str, dest: Path) -> bool:
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("catch-up: could not fetch %s (%s)", url, exc)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(resp.content)
    tmp.replace(dest)
    return True


def fetch_fresh_sources() -> int:
    """Returns how many small files were refreshed."""
    n = 0
    for name in ("results.csv", "goalscorers.csv"):
        n += _download(f"{MARTJ42}/{name}", DATA_DIR / name)
    season = current_season_dir()
    for name in DOMESTIC_FILES:
        n += _download(f"{OPENFOOTBALL}/{season}/{name}", DATA_DIR / "openfootball_raw" / season / name)
    return n


def is_fresh() -> bool:
    session = SessionLocal()
    try:
        row = session.get(Meta, "ingested_at")
        if row is None:
            return False
        return datetime.now(UTC) - datetime.fromisoformat(row.value) < timedelta(hours=MIN_AGE_HOURS)
    finally:
        session.close()


def run_catchup(force: bool = False) -> dict:
    """Blocking; callers run it in a thread. Returns a small report (also logged)."""
    if not _lock.acquire(blocking=False):
        return {"skipped": "another refresh is already running"}
    try:
        if not force and is_fresh():
            return {"skipped": f"data is under {MIN_AGE_HOURS}h old"}
        fetched = fetch_fresh_sources()
        env = {**os.environ, "INGEST_SKIP_PRECOMPUTE": "1"}
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "ingest.py")],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=600, check=False,
        )
        if proc.returncode != 0:
            log.error("catch-up: ingest failed: %s", proc.stderr[-500:])
            return {"fetched": fetched, "ingest": "failed"}
        session = SessionLocal()
        try:
            backfill_from_espn(session)  # re-apply recent results/scorers on top of the fresh ingest
            predictions = precompute_predictions(session)
        finally:
            session.close()
        report = {"fetched": fetched, "ingest": "ok", "predictions": predictions}
        log.info("catch-up done: %s", report)
        return report
    finally:
        _lock.release()


def start_background(force: bool = False) -> threading.Thread:
    thread = threading.Thread(target=run_catchup, kwargs={"force": force}, name="catchup", daemon=True)
    thread.start()
    return thread
