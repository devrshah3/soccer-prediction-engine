"""kickcast_api/live/results_updater.py: the scheduled job (A3) that keeps our own Match
rows' status/score current during a match window, using API-Football's date-scoped
/fixtures endpoint - distinct from poller.py's live=all polling, which never touches the
canonical Match row (see results_updater.py's module docstring).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.live import results_updater
from kickcast_api.models import Base, League, LiveMatchState, Match, Team


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'results_updater.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(League(code="test.1", name="Test League", country="Testland", kind="domestic_league"))
    s.add_all([Team(id="team-a", name="Alpha FC", country="Testland"), Team(id="team-b", name="Beta United", country="Testland")])
    s.commit()
    return s


def _add_match(session, kickoff_dt: datetime, status="scheduled", home_goals=None, away_goals=None):
    m = Match(
        league_code="test.1", season="2024-25", date=kickoff_dt.date(),
        kickoff=kickoff_dt.strftime("%H:%M"), home_team_id="team-a", away_team_id="team-b",
        home_goals=home_goals, away_goals=away_goals, status=status, round="Matchday 1",
        neutral=False, source="synthetic", source_id="s:1",
    )
    session.add(m)
    session.commit()
    return m


def test_in_match_window_true_shortly_after_kickoff(session):
    now = datetime.now(timezone.utc)
    _add_match(session, now - timedelta(minutes=30))
    assert results_updater.in_match_window(session, now) is True


def test_in_match_window_false_long_before_or_after_kickoff(session):
    now = datetime.now(timezone.utc)
    _add_match(session, now - timedelta(hours=6))  # long finished, outside the 150-min window
    assert results_updater.in_match_window(session, now) is False


def test_in_match_window_false_with_no_matches_today(session):
    assert results_updater.in_match_window(session) is False


def test_update_todays_results_is_a_noop_outside_match_window(session, monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    called = {"n": 0}
    monkeypatch.setattr(results_updater.api_football, "fetch_fixtures_by_date", lambda s, d: called.__setitem__("n", called["n"] + 1) or [])
    now = datetime.now(timezone.utc)
    _add_match(session, now - timedelta(hours=6))  # outside the window
    assert results_updater.update_todays_results(session, now) == 0
    assert called["n"] == 0  # never even made the call


def test_update_todays_results_marks_finished_and_sets_score(session, monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    now = datetime.now(timezone.utc)
    m = _add_match(session, now - timedelta(minutes=100))  # inside the window, "FT" plausible
    monkeypatch.setattr(results_updater, "_crosswalk", {9001: "team-a", 9002: "team-b"})
    monkeypatch.setattr(
        results_updater.api_football, "fetch_fixtures_by_date",
        lambda s, d: [{
            "fixture_id": 1, "minute": 90, "match_status": "FT",
            "home_team_id": 9001, "away_team_id": 9002,
            "home_team_name": "irrelevant", "away_team_name": "irrelevant",
            "home_score": 2, "away_score": 1, "events": [],
        }],
    )
    updated = results_updater.update_todays_results(session, now)
    assert updated == 1
    session.refresh(m)
    assert m.status == "finished" and m.home_goals == 2 and m.away_goals == 1

    state = session.get(LiveMatchState, m.id)
    assert state.match_status == "FT" and state.home_score == 2 and state.last_updated_at


def test_update_todays_results_ignores_a_match_it_cannot_confidently_map(session, monkeypatch):
    """No fuzzy name fallback here (unlike poller.py) - a wrong pairing would corrupt a
    real score, worse than leaving it unresolved until the next full ingest."""
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    now = datetime.now(timezone.utc)
    m = _add_match(session, now - timedelta(minutes=100))
    monkeypatch.setattr(results_updater, "_crosswalk", {})  # crosswalk resolves nothing
    monkeypatch.setattr(
        results_updater.api_football, "fetch_fixtures_by_date",
        lambda s, d: [{
            "fixture_id": 1, "minute": 90, "match_status": "FT",
            "home_team_id": 555, "away_team_id": 556,
            "home_team_name": "Alpha FC", "away_team_name": "Beta United",
            "home_score": 2, "away_score": 1, "events": [],
        }],
    )
    updated = results_updater.update_todays_results(session, now)
    assert updated == 0
    session.refresh(m)
    assert m.status == "scheduled" and m.home_goals is None


def test_update_todays_results_does_not_regress_an_already_correct_finished_match(session, monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    now = datetime.now(timezone.utc)
    m = _add_match(session, now - timedelta(minutes=100), status="finished", home_goals=2, away_goals=1)
    monkeypatch.setattr(results_updater, "_crosswalk", {9001: "team-a", 9002: "team-b"})
    monkeypatch.setattr(
        results_updater.api_football, "fetch_fixtures_by_date",
        lambda s, d: [{
            "fixture_id": 1, "minute": 90, "match_status": "FT",
            "home_team_id": 9001, "away_team_id": 9002,
            "home_team_name": "irrelevant", "away_team_name": "irrelevant",
            "home_score": 2, "away_score": 1, "events": [],
        }],
    )
    updated = results_updater.update_todays_results(session, now)
    assert updated == 0  # already correct - not counted as a change
    session.refresh(m)
    assert m.status == "finished" and m.home_goals == 2
