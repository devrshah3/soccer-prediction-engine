"""FastAPI endpoint tests against a small synthetic fixture DB (not the full 67k-match
production DB - too slow/non-deterministic to assert exact values against, same reasoning
as tests/test_models.py's synthetic() fixture).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.db import get_session
from kickcast_api.main import app
from kickcast_api.models import Base, League, Match, Team

TEAMS = [f"Team {i}" for i in range(8)]


def _seed(session) -> None:
    session.add(League(code="test.1", name="Test League", country="Testland", kind="domestic_league"))
    for i, name in enumerate(TEAMS):
        session.add(Team(id=f"team-{i}", name=name, country="Testland"))
    session.commit()

    d = date(2024, 8, 1)
    match_id = 0
    for round_no in range(6):  # 6 rounds x 4 fixtures = 24 finished matches, well over the 10-match minimum
        for k in range(4):
            h, a = (round_no + k) % 8, (round_no + k + 1) % 8
            if h == a:
                a = (a + 1) % 8
            match_id += 1
            session.add(
                Match(
                    league_code="test.1", season="2024-25", date=d, kickoff="15:00",
                    home_team_id=f"team-{h}", away_team_id=f"team-{a}",
                    home_goals=match_id % 4, away_goals=(match_id + 1) % 3,
                    status="finished", round=f"Matchday {round_no + 1}", neutral=False,
                    source="synthetic", source_id=f"synthetic:{match_id}",
                )
            )
        d += timedelta(days=7)
    # one upcoming fixture to exercise the prediction endpoint pre-kickoff
    session.add(
        Match(
            league_code="test.1", season="2024-25", date=d, kickoff="15:00",
            home_team_id="team-0", away_team_id="team-1", home_goals=None, away_goals=None,
            status="scheduled", round="Matchday 7", neutral=False,
            source="synthetic", source_id="synthetic:upcoming",
        )
    )
    session.commit()


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_api.db'}")
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


def test_list_leagues(client):
    r = client.get("/leagues")
    assert r.status_code == 200
    codes = {lg["code"] for lg in r.json()}
    assert codes == {"test.1"}


def test_standings_shape_and_ordering(client):
    r = client.get("/leagues/test.1/standings")
    assert r.status_code == 200
    body = r.json()
    assert body["season"] == "2024-25"
    table = body["table"]
    assert len(table) == 8
    pts = [row["pts"] for row in table]
    assert pts == sorted(pts, reverse=True)
    for row in table:
        assert row["played"] == row["w"] + row["d"] + row["l"]
        assert row["gd"] == row["gf"] - row["ga"]
        assert row["pts"] == row["w"] * 3 + row["d"]


def test_unknown_league_404(client):
    assert client.get("/leagues/nope/standings").status_code == 404


def test_league_fixtures_default_scheduled(client):
    r = client.get("/leagues/test.1/fixtures")
    assert r.status_code == 200
    body = r.json()
    assert all(m["status"] == "scheduled" for m in body)
    assert len(body) == 1


def test_team_detail_and_position(client):
    r = client.get("/teams/team-0")
    assert r.status_code == 200
    body = r.json()
    assert body["league_code"] == "test.1"
    assert 1 <= body["position"] <= 8
    assert body["next_match"]["home_team"]["id"] == "team-0"


def test_team_fixtures_scheduled_is_ascending(client):
    r = client.get("/teams/team-0/fixtures?status=scheduled")
    assert r.status_code == 200
    dates = [m["date"] for m in r.json()]
    assert dates == sorted(dates)


def test_match_detail(client):
    m = client.get("/leagues/test.1/fixtures").json()[0]
    r = client.get(f"/matches/{m['id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "scheduled"


def test_prediction_has_valid_probabilities(client):
    m = client.get("/leagues/test.1/fixtures").json()[0]
    r = client.get(f"/matches/{m['id']}/prediction")
    assert r.status_code == 200
    body = r.json()
    probs = body["probabilities"]
    assert abs(sum(probs.values()) - 1) < 1e-6
    assert all(0 <= v <= 1 for v in probs.values())
    assert body["evidence"] in ("A", "B", "C")
    assert body["model_version"]
    assert body["as_of"]


def test_unknown_match_404(client):
    assert client.get("/matches/999999").status_code == 404
    assert client.get("/matches/999999/prediction").status_code == 404
