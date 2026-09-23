from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.live import api_football, poller, quota
from kickcast_api.models import Base, League, LiveEvent, LiveMatchState, Match, Team


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'live.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(League(code="test.1", name="Test League", country="Testland", kind="domestic_league"))
    s.add_all([Team(id="team-a", name="Alpha FC", country="Testland"), Team(id="team-b", name="Beta United", country="Testland")])
    s.add(
        Match(
            league_code="test.1", season="2024-25", date=datetime.now(timezone.utc).date(), kickoff=None,
            home_team_id="team-a", away_team_id="team-b", home_goals=None, away_goals=None,
            status="scheduled", round="Matchday 1", neutral=False, source="synthetic", source_id="s:1",
        )
    )
    s.commit()
    return s


# ------------------------------------------------------------- api_football.py


def test_unavailable_without_key(session, monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    assert api_football.available() is False
    assert api_football.fetch_live_fixtures(session) is None


def test_fetch_live_fixtures_parses_mocked_response(session, monkeypatch):
    """Response shape verified against real API-Football calls on 2026-09-23: fixture
    id/status.elapsed/status.short, teams.home/away.id/name, goals.home/away, and events
    embedded per-fixture (confirmed real - see api_football.py's module docstring)."""
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key-for-test")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "response": [
                    {
                        "fixture": {"id": 111, "status": {"elapsed": 37, "short": "1H"}},
                        "teams": {"home": {"id": 33, "name": "Alpha FC"}, "away": {"id": 34, "name": "Beta United"}},
                        "goals": {"home": 1, "away": 0},
                        "events": [
                            {"time": {"elapsed": 12}, "type": "Goal", "detail": "Normal Goal",
                             "team": {"name": "Alpha FC"}, "player": {"name": "A. Striker"}},
                        ],
                    }
                ]
            }

    def fake_get(url, params=None, headers=None, timeout=None):
        assert params == {"live": "all"}  # one batched call, not per-match
        return FakeResponse()

    monkeypatch.setattr(api_football.requests, "get", fake_get)
    fixtures = api_football.fetch_live_fixtures(session)
    assert fixtures == [
        {
            "fixture_id": 111, "minute": 37, "match_status": "1H",
            "home_team_id": 33, "away_team_id": 34,
            "home_team_name": "Alpha FC", "away_team_name": "Beta United",
            "home_score": 1, "away_score": 0,
            "events": [
                {"minute": 12, "event_type": "goal", "team_name": "Alpha FC",
                 "player": "A. Striker", "detail": "Normal Goal"},
            ],
        }
    ]


def test_fetch_live_fixtures_respects_quota(session, monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    monkeypatch.setenv("API_FOOTBALL_DAILY_QUOTA", "0")
    assert api_football.fetch_live_fixtures(session) is None


def test_fetch_live_fixtures_fails_closed_on_network_error(session, monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")

    def raising_get(*a, **kw):
        raise api_football.requests.RequestException("boom")

    monkeypatch.setattr(api_football.requests, "get", raising_get)
    assert api_football.fetch_live_fixtures(session) is None


# ------------------------------------------------------------- poller.py


def test_poller_no_key_is_a_clean_noop(session, monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    assert poller.poll_live_matches(session) == 0
    assert session.query(LiveMatchState).count() == 0


def test_poller_matches_by_team_name_and_writes_state(session, monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    monkeypatch.setattr(
        poller.api_football, "fetch_live_fixtures",
        lambda s: [{"fixture_id": 1, "minute": 60, "match_status": "2H",
                    "home_team_name": "Alpha FC", "away_team_name": "Beta United",
                    "home_score": 2, "away_score": 1, "events": []}],
    )
    updated = poller.poll_live_matches(session)
    assert updated == 1
    state = session.query(LiveMatchState).one()
    assert state.minute == 60 and state.home_score == 2 and state.away_score == 1


def test_poller_prefers_real_crosswalk_over_name_matching(session, monkeypatch):
    """kickcast_engine.data.api_football_crosswalk (built from real /teams responses,
    see its module docstring) should be tried FIRST and take priority over fuzzy name
    matching, since it's unambiguous. Team names here are deliberately misleading
    (wouldn't fuzzy-match "Alpha FC"/"Beta United" at all) to prove the id path, not the
    name fallback, is what matched."""
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    monkeypatch.setattr(poller, "_crosswalk", {9001: "team-a", 9002: "team-b"})
    monkeypatch.setattr(
        poller.api_football, "fetch_live_fixtures",
        lambda s: [{"fixture_id": 1, "minute": 10, "match_status": "1H",
                    "home_team_id": 9001, "away_team_id": 9002,
                    "home_team_name": "Some Completely Different Name FC",
                    "away_team_name": "Another Unrelated Name United",
                    "home_score": 0, "away_score": 0, "events": []}],
    )
    updated = poller.poll_live_matches(session)
    assert updated == 1
    state = session.query(LiveMatchState).one()
    assert state.match_id == session.query(Match).one().id


def test_poller_does_not_fall_back_to_fuzzy_matching_when_crosswalk_ids_are_known_but_unmatched(session, monkeypatch):
    """If the crosswalk resolves both API-Football team ids to real kickcast teams but
    there's no fixture for that exact pairing today, that's a real "no fixture today"
    case - must NOT then guess via name substring matching (risk of matching the wrong
    game entirely)."""
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    monkeypatch.setattr(poller, "_crosswalk", {9001: "team-a", 9003: "team-c-not-playing-today"})
    monkeypatch.setattr(
        poller.api_football, "fetch_live_fixtures",
        lambda s: [{"fixture_id": 1, "minute": 10, "match_status": "1H",
                    "home_team_id": 9001, "away_team_id": 9003,
                    "home_team_name": "Alpha FC", "away_team_name": "Beta United",  # would fuzzy-match team-a/team-b if tried
                    "home_score": 0, "away_score": 0, "events": []}],
    )
    assert poller.poll_live_matches(session) == 0
    assert session.query(LiveMatchState).count() == 0


def test_poller_ignores_fixtures_it_cant_match(session, monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    monkeypatch.setattr(
        poller.api_football, "fetch_live_fixtures",
        lambda s: [{"fixture_id": 2, "minute": 10, "match_status": "1H",
                    "home_team_name": "Totally Unrelated FC", "away_team_name": "Nobody FC",
                    "home_score": 0, "away_score": 0, "events": []}],
    )
    assert poller.poll_live_matches(session) == 0
    assert session.query(LiveMatchState).count() == 0


def test_poller_writes_events_from_embedded_events(session, monkeypatch):
    """Events come embedded in the same batched live=all response - no second per-match
    call. Confirmed for real against API-Football on 2026-09-23 (see api_football.py)."""
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    monkeypatch.setattr(
        poller.api_football, "fetch_live_fixtures",
        lambda s: [{"fixture_id": 1, "minute": 60, "match_status": "2H",
                    "home_team_name": "Alpha FC", "away_team_name": "Beta United",
                    "home_score": 2, "away_score": 1,
                    "events": [
                        {"minute": 23, "event_type": "goal", "team_name": "Alpha FC",
                         "player": "A. Striker", "detail": "Normal Goal"},
                        {"minute": 58, "event_type": "card", "team_name": "Beta United",
                         "player": "B. Defender", "detail": "Yellow Card"},
                    ]}],
    )
    poller.poll_live_matches(session)
    events = session.query(LiveEvent).order_by(LiveEvent.minute).all()
    assert len(events) == 2
    assert events[0].minute == 23 and events[0].event_type == "goal" and events[0].team_id == "team-a"
    assert events[1].minute == 58 and events[1].event_type == "card" and events[1].team_id == "team-b"


def test_poller_replaces_events_on_next_poll_not_appends(session, monkeypatch):
    """API-Football's embedded events list is authoritative-as-of-now, not a delta (a VAR
    reversal or corrected minute must be reflected) - each poll should replace, not add."""
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    first = [{"fixture_id": 1, "minute": 20, "match_status": "1H",
              "home_team_name": "Alpha FC", "away_team_name": "Beta United",
              "home_score": 1, "away_score": 0,
              "events": [{"minute": 15, "event_type": "goal", "team_name": "Alpha FC",
                          "player": "A. Striker", "detail": "Normal Goal"}]}]
    second = [{"fixture_id": 1, "minute": 40, "match_status": "1H",
               "home_team_name": "Alpha FC", "away_team_name": "Beta United",
               "home_score": 2, "away_score": 0,
               "events": [
                   {"minute": 15, "event_type": "goal", "team_name": "Alpha FC",
                    "player": "A. Striker", "detail": "Normal Goal"},
                   {"minute": 38, "event_type": "goal", "team_name": "Alpha FC",
                    "player": "A. Striker", "detail": "Normal Goal"},
               ]}]
    monkeypatch.setattr(poller.api_football, "fetch_live_fixtures", lambda s: first)
    poller.poll_live_matches(session)
    monkeypatch.setattr(poller.api_football, "fetch_live_fixtures", lambda s: second)
    poller.poll_live_matches(session)
    assert session.query(LiveEvent).count() == 2  # not 3 - replaced, not appended


# ------------------------------------------------------------- quota.py


def test_quota_decrements(session):
    before = quota.api_football_quota_remaining(session)
    quota.record_api_football_call(session)
    assert quota.api_football_quota_remaining(session) == before - 1


# ------------------------------------------------------------- route


def test_live_route_unavailable_without_key(session, monkeypatch):
    from fastapi.testclient import TestClient

    from kickcast_api.db import get_session
    from kickcast_api.main import app

    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)

    def override():
        yield session

    app.dependency_overrides[get_session] = override
    try:
        m = session.query(Match).one()
        r = TestClient(app).get(f"/matches/{m.id}/live")
        assert r.status_code == 200
        assert r.json()["available"] is False
    finally:
        app.dependency_overrides.clear()


def test_live_route_reports_staleness_when_data_exists(session, monkeypatch):
    from fastapi.testclient import TestClient

    from kickcast_api.db import get_session
    from kickcast_api.main import app

    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    m = session.query(Match).one()
    stale = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
    session.add(LiveMatchState(match_id=m.id, minute=55, home_score=1, away_score=1, match_status="2H",
                                last_updated_at=stale, source="api-football"))
    session.commit()

    def override():
        yield session

    app.dependency_overrides[get_session] = override
    try:
        r = TestClient(app).get(f"/matches/{m.id}/live")
        body = r.json()
        assert body["available"] is True
        assert body["updated_minutes_ago"] >= 3.9
    finally:
        app.dependency_overrides.clear()
