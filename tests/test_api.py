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
from kickcast_api.models import Base, Goalscorer, League, Match, MatchStats, Team

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


def test_standings_sort_order_is_points_then_goal_difference_then_goals_for(tmp_path):
    """A3: explicit lock-in for the tie-break rule (points, then GD, then GF) - a real,
    live example of exactly this tie existed in production La Liga standings (two teams
    tied on points, correctly separated by goal difference) while verifying against
    real-world data, so this is worth a dedicated test rather than relying on the
    points-only check in test_standings_shape_and_ordering."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test_sort.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    session.add(League(code="sort.1", name="Sort League", country="Testland", kind="domestic_league"))
    for name in ("A", "B", "C", "D", "E"):
        session.add(Team(id=f"t-{name}", name=f"Team {name}", country="Testland"))
    session.commit()

    # A, B, and C each finish on 6 points (2 wins, 0 draws, 0 losses) against a padding
    # opponent, so points alone can't separate them:
    #   A: GF 8, GA 1, GD +7  (5-0, 3-1)
    #   B: GF 3, GA 1, GD +2  (2-1, 1-0)
    #   C: GF 5, GA 3, GD +2  (3-2, 2-1)
    # A must rank above B/C on GD. B and C are tied on both points AND GD, so C (more
    # goals for) must rank above B.
    fixtures = [
        ("t-A", "t-Z", 5, 0), ("t-A", "t-Z", 3, 1),
        ("t-B", "t-Z", 2, 1), ("t-B", "t-Z", 1, 0),
        ("t-C", "t-Z", 3, 2), ("t-C", "t-Z", 2, 1),
    ]
    session.add(Team(id="t-Z", name="Padding Opponent", country="Testland"))
    session.commit()
    d = date(2024, 8, 1)
    for i, (home, away, hg, ag) in enumerate(fixtures):
        session.add(
            Match(
                league_code="sort.1", season="2024-25", date=d, kickoff=None,
                home_team_id=home, away_team_id=away, home_goals=hg, away_goals=ag,
                status="finished", round=f"Matchday {i + 1}", neutral=False,
                source="synthetic", source_id=f"synthetic:sort-{i}",
            )
        )
        d += timedelta(days=1)
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
        table = {row["team_id"]: row for row in c.get("/leagues/sort.1/standings").json()["table"]}
    finally:
        app.dependency_overrides.clear()

    a, b, cc = table["t-A"], table["t-B"], table["t-C"]
    assert a["pts"] == b["pts"] == cc["pts"] == 6
    assert a["gd"] == 7 and b["gd"] == 2 and cc["gd"] == 2
    assert a["position"] < b["position"] and a["position"] < cc["position"]  # A: best GD, ranks 1st
    assert b["gd"] == cc["gd"]  # B and C tied on points AND GD - must fall through to GF
    assert cc["gf"] > b["gf"]  # C: 5 vs B: 3
    assert cc["position"] < b["position"]


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
    assert "goal_events" not in r.json()  # only attached for finished matches


def test_match_detail_includes_goal_events_for_a_finished_match_when_we_have_them(client):
    finished = client.get("/leagues/test.1/fixtures?status=finished").json()[0]
    r = client.get(f"/matches/{finished['id']}")
    assert r.status_code == 200
    assert r.json()["goal_events"] == []  # synthetic fixture has no Goalscorer rows - honest empty, not guessed


def test_match_detail_returns_real_goal_events_when_present(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_goals.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    session.add(League(code="goals.1", name="Goals League", country="Testland", kind="domestic_league"))
    session.add(Team(id="g-0", name="Club 0", country="Testland"))
    session.add(Team(id="g-1", name="Club 1", country="Testland"))
    session.commit()
    m = Match(
        league_code="goals.1", season="2024-25", date=date(2024, 8, 1), kickoff=None,
        home_team_id="g-0", away_team_id="g-1", home_goals=2, away_goals=1,
        status="finished", round="Matchday 1", neutral=False,
        source="synthetic", source_id="synthetic:goals",
    )
    session.add(m)
    session.flush()
    session.add(Goalscorer(match_id=m.id, date=m.date, team_id="g-0", scorer_name="Player A", minute=10, source="synthetic"))
    session.add(Goalscorer(match_id=m.id, date=m.date, team_id="g-1", scorer_name="Player B", minute=55, source="synthetic"))
    session.add(Goalscorer(match_id=m.id, date=m.date, team_id="g-0", scorer_name="Player C", minute=80, source="synthetic"))
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
        events = c.get(f"/matches/{m.id}").json()["goal_events"]
    finally:
        app.dependency_overrides.clear()

    assert [e["minute"] for e in events] == [10, 55, 80]  # ordered by minute
    assert events[0]["scorer"] == "Player A"


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


def test_prediction_includes_goal_timing_and_scorer_gating(client):
    m = client.get("/leagues/test.1/fixtures").json()[0]
    body = client.get(f"/matches/{m['id']}/prediction").json()
    windows = body["goal_timing"]
    assert [w["window"] for w in windows] == ["0-15", "15-30", "30-45", "45-60", "60-75", "75-90", "90+"]
    assert abs(sum(w["expected_goals"] for w in windows) - sum(body["expected_goals"].values())) < 0.01
    # synthetic league is domestic, not "international" -> no fabricated scorer data
    assert body["likely_scorers"]["available"] is False
    assert body["likely_scorers"]["home"] == []
    assert body["likely_scorers"]["away"] == []
    # synthetic fixture DB has no match_stats rows seeded -> not enough card history yet
    assert body["cards"]["available"] is False


def test_unknown_match_404(client):
    assert client.get("/matches/999999").status_code == 404
    assert client.get("/matches/999999/prediction").status_code == 404


def test_trophy_odds_shape_and_sums(client):
    r = client.get("/leagues/test.1/trophy-odds")
    assert r.status_code == 200
    body = r.json()
    assert body["league_code"] == "test.1"
    assert body["n_sims"] > 0
    teams = body["teams"]
    assert len(teams) == 8
    assert abs(sum(t["title_pct"] for t in teams) - 1.0) < 1e-6
    assert abs(sum(t["top4_pct"] for t in teams) - 4.0) < 1e-6
    for t in teams:
        assert 0 <= t["title_pct"] <= 1
        assert 0 <= t["relegation_pct"] <= 1


def test_trophy_odds_unknown_league_404(client):
    assert client.get("/leagues/nope/trophy-odds").status_code == 404


def test_next_match_cannot_diverge_from_the_upcoming_fixtures_list(tmp_path):
    """Regression for a real bug: next_match used to be a separate ad-hoc query (status=
    scheduled, date ascending, unbounded) that could disagree with the team's own fixtures
    list - a stale/anomalous "scheduled" row sorted first for one but was already excluded
    from the other. Reproduced with real production data: the Inter team page's "Next
    match" hero showed a stale 2025 "Como vs Inter" row while the Upcoming list below it
    (same status="scheduled" data) did not. Both now come from the exact same query, so
    they cannot diverge - proven here with two scheduled matches for the same team, an
    intentionally out-of-date-order one included, to make sure "first in the list" really
    does mean "earliest by date", not just "whatever happens to be first"."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test_next_match.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    session.add(League(code="nm.1", name="NM League", country="Testland", kind="domestic_league"))
    for i in range(4):
        session.add(Team(id=f"nm-{i}", name=f"NM Club {i}", country="Testland"))
    session.commit()

    later = Match(
        league_code="nm.1", season="2024-25", date=date(2026, 11, 20), kickoff=None,
        home_team_id="nm-0", away_team_id="nm-1", home_goals=None, away_goals=None,
        status="scheduled", round="Matchday 12", neutral=False,
        source="synthetic", source_id="synthetic:later",
    )
    earlier = Match(
        league_code="nm.1", season="2024-25", date=date(2026, 10, 3), kickoff=None,
        home_team_id="nm-2", away_team_id="nm-0", home_goals=None, away_goals=None,
        status="scheduled", round="Matchday 8", neutral=False,
        source="synthetic", source_id="synthetic:earlier",
    )
    session.add(later)  # inserted out of date order on purpose
    session.add(earlier)
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
        detail = c.get("/teams/nm-0").json()
        fixtures = c.get("/teams/nm-0/fixtures?status=scheduled").json()
        assert detail["next_match"]["id"] == fixtures[0]["id"] == earlier.id
    finally:
        app.dependency_overrides.clear()


def test_prediction_includes_card_data_when_available(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_cards.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    session.add(League(code="cards.1", name="Cards League", country="Testland", kind="domestic_league"))
    for i in range(8):
        session.add(Team(id=f"c-{i}", name=f"Club {i}", country="Testland"))
    session.commit()

    d = date(2024, 8, 1)
    for match_id in range(1, 13):
        i = match_id - 1
        h, a = i % 8, (i + 1) % 8
        m = Match(
            league_code="cards.1", season="2024-25", date=d, kickoff=None,
            home_team_id=f"c-{h}", away_team_id=f"c-{a}", home_goals=1, away_goals=1,
            status="finished", round=f"Matchday {match_id}", neutral=False,
            source="synthetic", source_id=f"synthetic:{match_id}",
        )
        session.add(m)
        session.flush()
        session.add(
            MatchStats(match_id=m.id, home_yellow=2, away_yellow=3, home_red=0, away_red=0, source="synthetic")
        )
        d += timedelta(days=7)
    session.add(
        Match(
            league_code="cards.1", season="2024-25", date=d, kickoff=None,
            home_team_id="c-0", away_team_id="c-1", home_goals=None, away_goals=None,
            status="scheduled", round="Matchday 13", neutral=False,
            source="synthetic", source_id="synthetic:upcoming",
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
        fixtures = c.get("/leagues/cards.1/fixtures").json()
        body = c.get(f"/matches/{fixtures[0]['id']}/prediction").json()
        assert body["cards"]["available"] is True
        assert body["cards"]["home"]["expected_yellow"] > 0
        assert body["cards"]["away"]["expected_yellow"] > 0
    finally:
        app.dependency_overrides.clear()


def test_international_prediction_includes_real_scorer_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_intl.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    session.add(League(code="international", name="International", country=None, kind="international"))
    session.add_all([Team(id="team-a", name="Team A", country=None), Team(id="team-b", name="Team B", country=None)])
    d = date(2023, 1, 1)
    for match_id in range(1, 13):
        i = match_id - 1
        session.add(
            Match(
                league_code="international", season="2023", date=d, kickoff=None,
                home_team_id="team-a" if i % 2 == 0 else "team-b",
                away_team_id="team-b" if i % 2 == 0 else "team-a",
                home_goals=2, away_goals=1, status="finished", round="Friendly", neutral=False,
                source="synthetic", source_id=f"synthetic:{match_id}",
            )
        )
        d += timedelta(days=30)
    session.add(
        Match(
            league_code="international", season="2024", date=d, kickoff=None,
            home_team_id="team-a", away_team_id="team-b", home_goals=None, away_goals=None,
            status="scheduled", round="Friendly", neutral=False,
            source="synthetic", source_id="synthetic:upcoming",
        )
    )
    session.add(
        Goalscorer(
            date=date(2023, 2, 1), team_id="team-a", scorer_name="Star Striker", minute=10,
            own_goal=False, penalty=False, source="synthetic",
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
        fixtures = c.get("/leagues/international/fixtures").json()
        body = c.get(f"/matches/{fixtures[0]['id']}/prediction").json()
        assert body["likely_scorers"]["available"] is True
        home_players = [s["player"] for s in body["likely_scorers"]["home"]]
        assert "Star Striker" in home_players
    finally:
        app.dependency_overrides.clear()


def test_domestic_prediction_includes_real_api_football_scorer_data(tmp_path):
    """Uses real La Liga team id "madrid" (Real Madrid) against the real cached
    API-Football topscorer data (data/api_football_cache/) - proves the domestic
    likely-scorers path returns real players, not just that the code runs."""
    from kickcast_api import domestic_scorers

    if not domestic_scorers.available("es.1"):
        return  # no cache in this environment - nothing to check here
    engine = create_engine(f"sqlite:///{tmp_path / 'test_domestic_scorers.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    session.add(League(code="es.1", name="La Liga", country="Spain", kind="domestic_league"))
    session.add_all([
        Team(id="madrid", name="Real Madrid", country="Spain"),
        Team(id="opponent", name="Some Opponent", country="Spain"),
    ])
    d = date(2023, 1, 1)
    for match_id in range(1, 13):
        i = match_id - 1
        session.add(
            Match(
                league_code="es.1", season="2022-23", date=d,
                home_team_id="madrid" if i % 2 == 0 else "opponent",
                away_team_id="opponent" if i % 2 == 0 else "madrid",
                home_goals=2, away_goals=1, status="finished", round=None, neutral=False,
                source="synthetic", source_id=f"synthetic:{match_id}",
            )
        )
        d += timedelta(days=7)
    session.add(
        Match(
            league_code="es.1", season="2023-24", date=d, kickoff=None,
            home_team_id="madrid", away_team_id="opponent", home_goals=None, away_goals=None,
            status="scheduled", round="Matchday 1", neutral=False,
            source="synthetic", source_id="synthetic:upcoming",
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
        fixtures = c.get("/leagues/es.1/fixtures").json()
        body = c.get(f"/matches/{fixtures[0]['id']}/prediction").json()
        assert body["likely_scorers"]["available"] is True
        assert body["likely_scorers"]["source"] == domestic_scorers.SOURCE
        home_players = [s["player"] for s in body["likely_scorers"]["home"]]
        assert "Kylian Mbappé" in home_players  # real 2024-25 La Liga top scorer for Real Madrid
    finally:
        app.dependency_overrides.clear()


def test_champions_league_never_gets_an_unvalidated_prediction_model(tmp_path):
    """get_model() must explicitly refuse "CL" even with >= 10 finished matches -
    DOMESTIC_HYPERPARAMS were validated on single-league goals, not a cross-league cup
    mixing teams with no shared strength scale (see predictions.py's docstring)."""
    from kickcast_api.predictions import get_model

    engine = create_engine(f"sqlite:///{tmp_path / 'test_cl_guard.db'}")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    session.add(League(code="CL", name="UEFA Champions League", country="Europe", kind="continental_cup"))
    session.add_all([Team(id="team-a", name="Team A", country=None), Team(id="team-b", name="Team B", country=None)])
    d = date(2026, 9, 1)
    for match_id in range(1, 15):  # well above the >= 10 threshold that would otherwise fit a model
        i = match_id - 1
        session.add(
            Match(
                league_code="CL", season="2026-27", date=d, kickoff=None,
                home_team_id="team-a" if i % 2 == 0 else "team-b",
                away_team_id="team-b" if i % 2 == 0 else "team-a",
                home_goals=2, away_goals=1, status="finished", round="LEAGUE_STAGE MD1", neutral=False,
                source="synthetic", source_id=f"synthetic:{match_id}",
            )
        )
        d += timedelta(days=7)
    session.commit()
    assert get_model(session, "CL") is None
