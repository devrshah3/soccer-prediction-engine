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

from kickcast_api.live import matching, results_updater
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
    _add_match(session, now - timedelta(hours=100))  # beyond even the 72h catch-up horizon
    assert results_updater.update_todays_results(session, now) == 0
    assert called["n"] == 0  # never even made the call


def test_update_todays_results_marks_finished_and_sets_score(session, monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    now = datetime.now(timezone.utc)
    m = _add_match(session, now - timedelta(minutes=100))  # inside the window, "FT" plausible
    monkeypatch.setattr(matching, "_crosswalk", {9001: "team-a", 9002: "team-b"})
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
    """Names that don't canonicalise to our team ids stay unresolved - no substring
    guessing, a wrong pairing would corrupt a real score."""
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    now = datetime.now(timezone.utc)
    m = _add_match(session, now - timedelta(minutes=100))
    monkeypatch.setattr(matching, "_crosswalk", {})  # crosswalk resolves nothing
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
    monkeypatch.setattr(matching, "_crosswalk", {9001: "team-a", 9002: "team-b"})
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


def _national_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'nat.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(League(code="international", name="International", country="World", kind="international"))
    s.add_all([Team(id="georgia", name="Georgia", country=None), Team(id="ukraine", name="Ukraine", country=None)])
    s.commit()
    return s


def _national_match(s, kickoff_dt):
    m = Match(
        league_code="international", season="2026-27", date=kickoff_dt.date(), kickoff=kickoff_dt.strftime("%H:%M"),
        home_team_id="georgia", away_team_id="ukraine", home_goals=None, away_goals=None, status="scheduled",
        round="UEFA Nations League MD2", neutral=False, source="uefa", source_id="n:1",
    )
    s.add(m)
    s.commit()
    return m


def test_national_teams_outside_the_club_crosswalk_are_matched_by_exact_name(tmp_path, monkeypatch):
    """Regression: Georgia v Ukraine (Nations League) stayed 'scheduled' forever because the
    crosswalk only knows big-5 clubs and the updater refused any name fallback."""
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    s = _national_session(tmp_path)
    now = datetime.now(timezone.utc)
    m = _national_match(s, now - timedelta(minutes=110))
    monkeypatch.setattr(matching, "_crosswalk", {})  # big-5 clubs only - knows neither team
    monkeypatch.setattr(
        results_updater.api_football, "fetch_fixtures_by_date",
        lambda sess, d: [{
            "fixture_id": 77, "minute": 90, "match_status": "FT", "home_team_id": 1, "away_team_id": 2,
            "home_team_name": "Georgia", "away_team_name": "Ukraine", "home_score": 1, "away_score": 2,
            "events": [{"minute": 12, "event_type": "goal", "team_name": "Ukraine", "player": "A. Player", "detail": "Normal Goal"}],
        }],
    )
    assert results_updater.update_todays_results(s, now) == 1
    s.refresh(m)
    assert (m.status, m.home_goals, m.away_goals) == ("finished", 1, 2)
    from kickcast_api.models import LiveEvent
    ev = s.query(LiveEvent).filter(LiveEvent.match_id == m.id).all()
    assert [(e.minute, e.team_id, e.player) for e in ev] == [(12, "ukraine", "A. Player")]


def test_unfinished_match_is_caught_up_after_the_normal_window_but_rate_limited(tmp_path, monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    monkeypatch.setattr(results_updater, "_last_date_call", {})
    s = _national_session(tmp_path)
    now = datetime.now(timezone.utc)
    _national_match(s, now - timedelta(hours=4))  # past the 150-min window, still 'scheduled'
    calls = []
    monkeypatch.setattr(results_updater.api_football, "fetch_fixtures_by_date", lambda sess, d: calls.append(d) or [])
    results_updater.update_todays_results(s, now)
    results_updater.update_todays_results(s, now + timedelta(minutes=10))  # inside the 30-min gap
    assert len(calls) == 1
    results_updater.update_todays_results(s, now + timedelta(minutes=31))
    assert len(calls) == 2


def test_yesterdays_unfinished_match_is_caught_up_after_midnight(tmp_path, monkeypatch):
    """The three Sep 28 Nations League games were still unresolved when the clock rolled to
    Sep 29 (and the daily quota reset) - the updater must ask for YESTERDAY's fixtures too."""
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    monkeypatch.setattr(results_updater, "_last_date_call", {})
    s = _national_session(tmp_path)
    now = datetime(2026, 9, 29, 0, 5, tzinfo=timezone.utc)
    _national_match(s, datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc))
    calls = []
    monkeypatch.setattr(results_updater.api_football, "fetch_fixtures_by_date", lambda sess, d: calls.append(d) or [])
    results_updater.update_todays_results(s, now)
    assert calls == ["2026-09-28"]


def test_not_played_rows_from_the_last_days_are_revived_when_a_result_arrives(tmp_path, monkeypatch):
    """Sep 27's Nations League rows were relabelled 'not_played' by ingest with no score - a
    later final status from the source must turn them back into finished results."""
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    monkeypatch.setattr(results_updater, "_last_date_call", {})
    monkeypatch.setattr(matching, "_crosswalk", {})
    s = _national_session(tmp_path)
    now = datetime(2026, 9, 29, 0, 5, tzinfo=timezone.utc)
    m = _national_match(s, datetime(2026, 9, 27, 16, 0, tzinfo=timezone.utc))
    m.status = "not_played"
    s.commit()
    monkeypatch.setattr(
        results_updater.api_football, "fetch_fixtures_by_date",
        lambda sess, d: [{
            "fixture_id": 5, "minute": 90, "match_status": "FT", "home_team_id": 1, "away_team_id": 2,
            "home_team_name": "Georgia", "away_team_name": "Ukraine", "home_score": 0, "away_score": 3, "events": [],
        }] if d == "2026-09-27" else [],
    )
    monkeypatch.setattr(results_updater.api_football, "fetch_events", lambda sess, fid: [])
    assert results_updater.update_todays_results(s, now) == 1
    s.refresh(m)
    assert (m.status, m.home_goals, m.away_goals) == ("finished", 0, 3)


def test_old_unresolved_dates_are_only_rechecked_every_six_hours(tmp_path, monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake-key")
    monkeypatch.setattr(results_updater, "_last_date_call", {})
    s = _national_session(tmp_path)
    now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    _national_match(s, datetime(2026, 9, 27, 16, 0, tzinfo=timezone.utc))
    calls = []
    monkeypatch.setattr(results_updater.api_football, "fetch_fixtures_by_date", lambda sess, d: calls.append(d) or [])
    results_updater.update_todays_results(s, now)
    results_updater.update_todays_results(s, now + timedelta(hours=1))
    results_updater.update_todays_results(s, now + timedelta(hours=5))
    assert calls == ["2026-09-27"]
    results_updater.update_todays_results(s, now + timedelta(hours=6, minutes=1))
    assert len(calls) == 2
