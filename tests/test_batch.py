"""Tests for kickcast_api/routes/batch.py: the homepage's batched fixtures/predictions
endpoints, its date-window bounding (A2 in MORNING_REPORT.md), and the widened-window +
"next domestic fixture" support added for A4.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.db import get_session
from kickcast_api.main import app
from kickcast_api.models import Base, League, Match, Team


def _seed(session) -> None:
    session.add(League(code="dom.1", name="Domestic League", country="Testland", kind="domestic_league"))
    session.add(League(code="intl", name="International", country=None, kind="international"))
    for i in range(4):
        session.add(Team(id=f"t-{i}", name=f"Team {i}", country="Testland"))
    session.commit()

    now = datetime.now(UTC).date()

    def add(league_code, days_from_now, home, away, status="scheduled"):
        session.add(
            Match(
                league_code=league_code, season="2026-27", date=now + timedelta(days=days_from_now),
                kickoff=None, home_team_id=home, away_team_id=away, home_goals=None, away_goals=None,
                status=status, round=None, neutral=False,
                source="synthetic", source_id=f"synthetic:{league_code}:{days_from_now}:{home}:{away}",
            )
        )

    # Domestic league: nothing within 7 days, one match at day 10 (within 14 but not 7).
    add("dom.1", 10, "t-0", "t-1")
    # International: several matches within the next 7 days (an "international break").
    for d in (1, 2, 3, 4, 5):
        add("intl", d, "t-2", "t-3")
    # A stale/not-yet-relabeled "scheduled" row from the past - must never appear.
    add("dom.1", -400, "t-0", "t-1")
    session.commit()


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_batch.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    _seed(TestSession())

    def override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_fixtures_batch_bounds_by_days_and_excludes_stale_rows(client):
    r = client.get("/fixtures?leagues=dom.1,intl&status=scheduled&limit=10&days=7")
    assert r.status_code == 200
    body = r.json()
    assert body["dom.1"] == []  # the day-10 match is outside a 7-day window
    assert len(body["intl"]) == 5
    assert all(m["date"] for m in body["intl"])  # sanity: real rows, not the stale one


def test_fixtures_batch_widens_with_days_param(client):
    r = client.get("/fixtures?leagues=dom.1,intl&status=scheduled&limit=10&days=14")
    assert r.status_code == 200
    body = r.json()
    assert len(body["dom.1"]) == 1  # the day-10 match now falls inside the window
    assert len(body["intl"]) == 5


def test_fixtures_batch_sorts_by_kickoff_and_does_not_truncate_a_busy_day(tmp_path):
    """Real bug (A.1): 8 real Nations League matches exist on 2026-09-27, all in our DB,
    but the homepage only showed 6 - Norway-Portugal and Serbia-Netherlands were missing.
    Root cause: the query had no ORDER BY on kickoff, only date, so ties on the same date
    were incidentally ordered by whatever index SQLite used to satisfy the filter (in
    practice, alphabetically by home_team_id via the natural-key unique index) - combined
    with a default limit of 6, this silently dropped whichever teams sorted late
    alphabetically. Reproduced here with 8 teams named A-H (so alphabetical-by-home-team
    order is deterministic) at 3 different kickoff times, with the teams that should sort
    LAST by kickoff time given names that sort FIRST alphabetically - a query that only
    sorts by date (or is unordered) and limits to 6 would drop the two 18:45 matches
    whose home teams alphabetize last; the fixed query must return all 8, in kickoff order."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test_busy_day.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    session.add(League(code="intl", name="International", country=None, kind="international"))
    for name in "ABCDEFGHIJKLMNOP":
        session.add(Team(id=f"team-{name.lower()}", name=f"Team {name}", country=None))
    session.commit()

    now = datetime.now(UTC).date() + timedelta(days=1)
    # Team A/B (alphabetically first) kick off LAST (18:45); Team G/H kick off FIRST
    # (13:00) - a date-only or unordered sort would still pass a naive "first 6" check by
    # accident unless the alphabetically-last teams are made to kick off last for real.
    fixtures = [
        ("13:00", "team-g", "team-h"), ("13:00", "team-i", "team-j"),
        ("16:00", "team-c", "team-d"), ("16:00", "team-e", "team-f"),
        ("16:00", "team-k", "team-l"), ("16:00", "team-m", "team-n"),
        ("18:45", "team-a", "team-b"), ("18:45", "team-o", "team-p"),
    ]
    for kickoff, home, away in fixtures:
        session.add(
            Match(
                league_code="intl", season="2026-27", date=now, kickoff=kickoff,
                home_team_id=home, away_team_id=away, home_goals=None, away_goals=None,
                status="scheduled", round=None, neutral=False,
                source="synthetic", source_id=f"synthetic:{kickoff}:{home}:{away}",
            )
        )
    session.commit()

    def override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override
    try:
        c = TestClient(app)
        body = c.get("/fixtures?leagues=intl&status=scheduled&days=7").json()  # default limit (50), not the old 6
    finally:
        app.dependency_overrides.clear()

    assert len(body["intl"]) == 8, "all 8 same-day matches must come back, not just the first 6"
    kickoffs = [m["kickoff"] for m in body["intl"]]
    assert kickoffs == sorted(kickoffs), "must be ordered by actual kickoff time"
    # The two 18:45 matches (team-a/b, team-o/p) alphabetize earliest/latest respectively -
    # both must survive regardless, proving the limit isn't truncating by alphabetical luck.
    home_ids = {m["home_team"]["id"] for m in body["intl"]}
    assert {"team-a", "team-o"} <= home_ids


def test_next_domestic_fixture_date_skips_international(client):
    r = client.get("/fixtures/next-domestic-date")
    assert r.status_code == 200
    now = datetime.now(UTC).date()
    assert r.json()["date"] == (now + timedelta(days=10)).isoformat()


def test_next_domestic_fixture_date_null_when_none_scheduled(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_batch_empty.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    TestSession().commit()

    def override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override
    try:
        c = TestClient(app)
        assert c.get("/fixtures/next-domestic-date").json() == {"date": None}
    finally:
        app.dependency_overrides.clear()
