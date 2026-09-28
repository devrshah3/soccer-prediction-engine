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
