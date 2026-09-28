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

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import League, Match
from ..predictions import get_model, get_model_computed_at
from ..serialize import match_dict

router = APIRouter(tags=["batch"])

DEFAULT_UPCOMING_WINDOW_DAYS = 7


@router.get("/fixtures")
def fixtures_by_league(
    leagues: str,
    status: str = "scheduled",
    limit: int = 50,
    days: int = DEFAULT_UPCOMING_WINDOW_DAYS,
    session: Session = Depends(get_session),
) -> dict[str, list[dict]]:
    """Fixtures for several leagues in one request. `leagues` is a comma-separated list of
    league codes; unknown codes just come back with an empty list rather than erroring the
    whole batch.

    For status="scheduled" (what the homepage asks for), fixtures are hard-bounded to
    [now, now + `days`], no exceptions, regardless of league/competition. Without this,
    a league whose most recent "scheduled" row is stale (e.g. a postponed match from years
    ago that was never marked finished, or the final matchday of a season not yet ingested
    as finished) surfaces as the "next" fixture - which is how the homepage ended up
    showing La Liga/Serie A "Matchday 38" games from over a year ago alongside Nations
    League games days in the past, all labeled "upcoming" in the same list.

    Real bug fixed here: the query had no ORDER BY on kickoff time, only on `date` - ties
    on the same date were then ordered incidentally by whatever index SQLite chose to
    satisfy the query (in practice: the `uq_match_natural_key` unique index on (league_code,
    date, home_team_id, away_team_id), i.e. alphabetically by home team). Combined with a
    default limit of 6 (fine for a domestic matchday, nowhere near enough for a Nations
    League matchday with up to 26 simultaneous fixtures), this silently dropped whichever
    matches happened to sort late alphabetically - e.g. Norway-Portugal and Serbia-
    Netherlands on 2026-09-27, while Austria/Denmark/Germany/Gibraltar/Israel/Lithuania
    (alphabetically earlier home teams, same kickoff times) were kept. Fixed by sorting on
    (date, kickoff) and raising the default limit well past any real single-day fixture
    count; the date window above is the real bound now, not this limit.

    `days` is a parameter (not hardcoded) so the homepage can widen the window (7 -> 14)
    when the default window comes back thin - e.g. during an international break, when
    domestic leagues pause and 7 days of pure Nations League fixtures isn't much of a
    homepage. See also GET /fixtures/next-domestic-date for the note the homepage shows
    when even the widened window has nothing domestic in it.
    """
    if status not in ("scheduled", "finished", "all"):
        raise HTTPException(400, "status must be 'scheduled', 'finished', or 'all'")
    codes = [c for c in leagues.split(",") if c]
    order = (Match.date.asc(), Match.kickoff.asc()) if status != "finished" else (Match.date.desc(), Match.kickoff.desc())
    out: dict[str, list[dict]] = {}
    now = datetime.now(UTC).date()
    horizon = now + timedelta(days=days)
    for code in codes:
        q = session.query(Match).filter(Match.league_code == code)
        if status != "all":
            q = q.filter(Match.status == status)
        if status == "scheduled":
            q = q.filter(Match.date >= now, Match.date <= horizon)
        matches = q.order_by(*order).limit(limit).all()
        out[code] = [match_dict(session, m) for m in matches]
    return out


@router.get("/fixtures/next-domestic-date")
def next_domestic_fixture_date(session: Session = Depends(get_session)) -> dict:
    """The earliest scheduled date across domestic leagues (not international/continental
    competitions) from today onward. Used for the homepage's "International break: club
    football resumes <date>" note, which needs to look further ahead than whatever window
    the fixtures list itself is currently using."""
    now = datetime.now(UTC).date()
    row = (
        session.query(Match.date)
        .join(League, League.code == Match.league_code)
        .filter(League.kind == "domestic_league", Match.status == "scheduled", Match.date >= now)
        .order_by(Match.date.asc())
        .first()
    )
    return {"date": row[0].isoformat() if row else None}


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
        pred = model.predict(m.home_team_id, m.away_team_id, neutral=m.neutral)
        pred["computed_at"] = get_model_computed_at(session, m.league_code)
        out[str(match_id)] = pred
    return out
