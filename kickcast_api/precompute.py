"""B.8: precompute predictions for every scheduled match in the next 90 days, storing
them (PrecomputedPrediction) so serving is a fast DB read instead of a per-request
model.predict() call. Called after every ingest (scripts/ingest.py) and on a nightly
schedule (kickcast_api/live/scheduler.py) - never from a request handler.

Excludes "CL": predictions.get_model() already refuses to fit an unvalidated cross-league
model for it, so there's nothing to precompute there (same as the live endpoint).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from .models import Match, PrecomputedPrediction
from .predictions import get_model, get_model_computed_at

PRECOMPUTE_WINDOW_DAYS = 90


def precompute_predictions(session: Session, league_codes: list[str] | None = None) -> int:
    """Returns how many rows were written/updated."""
    if league_codes is None:
        league_codes = [row[0] for row in session.query(Match.league_code).distinct()]
    now = datetime.now(UTC).date()
    horizon = now + timedelta(days=PRECOMPUTE_WINDOW_DAYS)
    written = 0
    for league_code in league_codes:
        model = get_model(session, league_code)
        if model is None:
            continue
        computed_at = get_model_computed_at(session, league_code) or datetime.now(UTC).isoformat()
        matches = (
            session.query(Match)
            .filter(
                Match.league_code == league_code, Match.status == "scheduled",
                Match.date >= now, Match.date <= horizon,
            )
            .all()
        )
        for m in matches:
            pred = model.predict(m.home_team_id, m.away_team_id, neutral=m.neutral)
            row = session.get(PrecomputedPrediction, m.id)
            if row is None:
                row = PrecomputedPrediction(
                    match_id=m.id, prediction_json="", model_version="", computed_at="", data_cutoff="",
                )
                session.add(row)
            row.prediction_json = json.dumps(pred)
            row.model_version = pred["model_version"]
            row.computed_at = computed_at
            row.data_cutoff = pred["as_of"]
            written += 1
    session.commit()
    return written


def get_precomputed_prediction(session: Session, match_id: int) -> dict | None:
    row = session.get(PrecomputedPrediction, match_id)
    if row is None:
        return None
    pred = json.loads(row.prediction_json)
    pred["computed_at"] = row.computed_at
    return pred
