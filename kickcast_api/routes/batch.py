"""Batch read endpoints that exist purely so a single page load (the homepage) can fetch
data for many leagues/matches in one HTTP round trip and one DB session, instead of fanning
out into dozens of concurrent per-league/per-match requests - that fan-out (one request per
league's fixtures, one per candidate match's prediction) was what exhausted the SQLAlchemy
connection pool under ordinary browsing, not just heavy load. Prefer the existing
per-resource endpoints (`/leagues/{code}/fixtures`, `/matches/{id}/prediction`) for anything
that only needs one league or one match - they return richer detail than is worth computing
for every row of a list view.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Match
from ..predictions import get_model
from ..serialize import match_dict

router = APIRouter(tags=["batch"])


@router.get("/fixtures")
def fixtures_by_league(
    leagues: str, status: str = "scheduled", limit: int = 6, session: Session = Depends(get_session)
) -> dict[str, list[dict]]:
    """Fixtures for several leagues in one request. `leagues` is a comma-separated list of
    league codes; unknown codes just come back with an empty list rather than erroring the
    whole batch."""
    if status not in ("scheduled", "finished", "all"):
        raise HTTPException(400, "status must be 'scheduled', 'finished', or 'all'")
    codes = [c for c in leagues.split(",") if c]
    order = Match.date.asc() if status != "finished" else Match.date.desc()
    out: dict[str, list[dict]] = {}
    for code in codes:
        q = session.query(Match).filter(Match.league_code == code)
        if status != "all":
            q = q.filter(Match.status == status)
        matches = q.order_by(order).limit(limit).all()
        out[code] = [match_dict(session, m) for m in matches]
    return out


@router.get("/predictions/summary")
def predictions_summary(match_ids: str, session: Session = Depends(get_session)) -> dict[str, dict | None]:
    """The probabilities/evidence/model_version/as_of for several matches in one request -
    the subset a list view needs. Skips the per-match likely-scorers/cards/goal-timing
    extras `/matches/{id}/prediction` computes (those cost real DB/file lookups each and
    are only worth it on a single match's own page). A match with no prediction available
    (unknown id, or not enough history yet) comes back as null rather than erroring the
    whole batch."""
    try:
        ids = [int(x) for x in match_ids.split(",") if x]
    except ValueError:
        raise HTTPException(400, "match_ids must be a comma-separated list of integers") from None

    out: dict[str, dict | None] = {}
    for match_id in ids:
        m = session.get(Match, match_id)
        if m is None:
            out[str(match_id)] = None
            continue
        model = get_model(session, m.league_code)
        if model is None:
            out[str(match_id)] = None
            continue
        out[str(match_id)] = model.predict(m.home_team_id, m.away_team_id, neutral=m.neutral)
    return out
