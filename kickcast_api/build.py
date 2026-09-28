"""Everything heavy, in one place: run at BUILD time (scripts/build.py), by the nightly job, and by
the admin recompute endpoint - never inside a public request.

Order matters: models first (predictions/odds need them), then the Monte Carlo trophy odds, the
Golden Boot projections (the only step that calls a provider - football-data.org, 6 calls, well
inside its 10/minute limit), and last the precomputed match predictions.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from . import artifacts, football_data_scorers, golden_boot_projection
from .awards import ALL_LEAGUES, golden_boot_payload_key
from .cards import fit_card_model
from .models import Match
from .precompute import precompute_predictions
from .predictions import fit_model
from .serialize import latest_season
from .trophy_odds import compute_trophy_odds, payload_key

log = logging.getLogger("kickcast.build")
DOMESTIC = ["en.1", "es.1", "it.1", "de.1", "fr.1"]


def _timed(name: str, fn: Callable[[], object], report: dict[str, float]) -> None:
    started = time.monotonic()
    try:
        fn()
    except Exception:
        log.exception("build step %s failed", name)
        report[name] = -1.0
        return
    report[name] = round(time.monotonic() - started, 1)


def build_models(session: Session) -> None:
    leagues = [row[0] for row in session.query(Match.league_code).distinct()]
    for code in leagues:
        fit_model(session, code, persist=True)
        fit_card_model(session, code, persist=True)


def build_trophy_odds(session: Session) -> None:
    for code in DOMESTIC:
        season = latest_season(session, code)
        if season is None:
            continue
        odds = compute_trophy_odds(session, code, season)
        if odds is not None:
            artifacts.put_payload(session, payload_key(code, season), odds)


def build_golden_boot(session: Session, network: bool = True) -> None:
    for code, _name in ALL_LEAGUES:
        if network:
            football_data_scorers.fetch_scorers(code)  # refresh the cached leaderboard (rate-limited client)
        result = golden_boot_projection.project(session, code, network=False)
        artifacts.put_payload(session, golden_boot_payload_key(code), result)


def build_everything(session: Session, network: bool = True) -> dict[str, float]:
    """Returns seconds per step (-1 for a step that failed)."""
    report: dict[str, float] = {}
    _timed("models", lambda: build_models(session), report)
    _timed("trophy_odds", lambda: build_trophy_odds(session), report)
    _timed("golden_boot", lambda: build_golden_boot(session, network), report)
    _timed("precompute_predictions", lambda: precompute_predictions(session), report)
    return report
