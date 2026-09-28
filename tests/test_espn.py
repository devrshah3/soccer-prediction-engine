"""ESPN scoreboard source (kickcast_api/live/espn.py) end to end, from a REAL trimmed payload
(tests/data/espn_nations_league_2026-09-28.json, captured 2026-09-28)."""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.live import espn, results_updater
from kickcast_api.match_events import events_for_matches
from kickcast_api.models import Base, League, LiveMatchState, Match, Team

REAL = json.loads((Path(__file__).parent / "data" / "espn_nations_league_2026-09-28.json").read_text())["events"]
NOW = datetime(2026, 9, 28, 20, 58, tzinfo=timezone.utc)


def _real(name_part: str) -> dict:
    return copy.deepcopy(next(e for e in REAL if name_part in e["name"]))


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(results_updater, "_espn_last_date_call", {})
    engine = create_engine(f"sqlite:///{tmp_path / 'espn.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(League(code="international", name="International", country="World", kind="international"))
    for tid, name in [("sweden", "Sweden"), ("poland", "Poland"), ("armenia", "Armenia"), ("montenegro", "Montenegro")]:
        s.add(Team(id=tid, name=name, country=None))
    for h, a, ko in [("sweden", "poland", "18:45"), ("armenia", "montenegro", "16:00")]:
        s.add(Match(league_code="international", season="2026-27", date=date(2026, 9, 28), kickoff=ko, home_team_id=h,
                    away_team_id=a, home_goals=None, away_goals=None, status="scheduled", round="NL", neutral=False,
                    source="uefa", source_id=f"{h}"))
    s.commit()
    return s


def _serve(monkeypatch, events):
    monkeypatch.setattr(espn.requests, "get", lambda *a, **k: _Resp({"events": events}))


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def test_parse_real_finished_event():
    fx = espn.parse_event(_real("Sweden"))
    assert (fx["home_team_name"], fx["away_team_name"], fx["home_score"], fx["away_score"]) == ("Sweden", "Poland", 3, 1)
    assert fx["match_status"] == "FT" and fx["events_authoritative"] is True
    goals = [(e["minute"], e["player"]) for e in fx["events"] if e["event_type"] == "goal"]
    assert goals == [(8, "Benjamin Nygren"), (43, "Sebastian Szymanski"), (63, "Yasin Ayari"), (72, "Viktor Gyökeres")]
    assert sum(e["event_type"] == "card" for e in fx["events"]) == 4


def test_parse_skips_not_started_and_marks_own_goals():
    pre = _real("Sweden")
    pre["status"]["type"]["name"] = "STATUS_SCHEDULED"
    assert espn.parse_event(pre) is None
    og = [e for e in espn.parse_event(_real("Armenia"))["events"] if e["detail"] == "Own Goal"]
    assert [e["player"] for e in og] == ["Erik Piloyan"]


def test_a_finished_match_gets_its_score_goals_and_cards_and_a_fetch_timestamp(session, monkeypatch):
    _serve(monkeypatch, [_real("Sweden"), _real("Armenia")])
    assert results_updater.update_results_from_espn(session, NOW) == 2
    m = session.query(Match).filter_by(home_team_id="sweden").one()
    assert (m.status, m.home_goals, m.away_goals) == ("finished", 3, 1)
    state = session.get(LiveMatchState, m.id)
    assert state.match_status == "FT" and state.source == "espn" and state.last_updated_at == NOW.isoformat()
    ev = events_for_matches(session, [m])[m.id]
    assert [g["scorer"] for g in ev["goals"]] == ["Benjamin Nygren", "Sebastian Szymanski", "Yasin Ayari", "Viktor Gyökeres"]
    assert len(ev["cards"]) == 4
    # the own goal is credited to the side that makes Armenia 2 - 3 Montenegro add up
    arm = session.query(Match).filter_by(home_team_id="armenia").one()
    goals = events_for_matches(session, [arm])[arm.id]["goals"]
    assert (sum(g["team_id"] == "armenia" for g in goals), sum(g["team_id"] == "montenegro" for g in goals)) == (2, 3)


def test_live_match_goes_from_0_0_to_a_goal_between_polls(session, monkeypatch):
    def live(home_goals_in_details: int):
        e = _real("Sweden")
        e["status"]["type"].update(name="STATUS_FIRST_HALF", state="in", completed=False)
        e["status"]["displayClock"] = "30'"
        comp = e["competitions"][0]
        comp["details"] = [d for d in comp["details"] if d["scoringPlay"]][:home_goals_in_details]
        for c in comp["competitors"]:
            c["score"] = str(home_goals_in_details if c["homeAway"] == "home" else 0)
        return e

    m = session.query(Match).filter_by(home_team_id="sweden").one()
    _serve(monkeypatch, [live(0)])
    results_updater.update_results_from_espn(session, NOW)
    session.refresh(m)
    state = session.get(LiveMatchState, m.id)
    assert m.status == "scheduled" and (m.home_goals, m.away_goals) == (0, 0)  # a real 0-0, not "no data"
    assert (state.match_status, state.minute, state.home_score) == ("1H", 30, 0)
    assert events_for_matches(session, [m])[m.id]["goals"] == []

    _serve(monkeypatch, [live(1)])
    later = datetime(2026, 9, 28, 21, 8, tzinfo=timezone.utc)
    results_updater._espn_last_date_call.clear()
    results_updater.update_results_from_espn(session, later)
    session.refresh(m)
    assert (m.home_goals, m.away_goals) == (1, 0)
    assert [g["scorer"] for g in events_for_matches(session, [m])[m.id]["goals"]] == ["Benjamin Nygren"]
    assert session.get(LiveMatchState, m.id).last_updated_at == later.isoformat()


def test_disabled_source_makes_no_request(session, monkeypatch):
    monkeypatch.setenv("ENABLE_ESPN", "false")
    monkeypatch.setattr(espn.requests, "get", lambda *a, **k: pytest.fail("must not call ESPN when disabled"))
    assert results_updater.update_results_from_espn(session, NOW) == 0


def test_production_default_is_off(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ENABLE_ESPN", raising=False)
    assert espn.available() is False


def test_backfill_walks_the_recent_days_and_fills_in_results_scorers_and_cards(session, monkeypatch):
    """A freshly built/woken instance only has what the open sources knew at build time; the
    backfill re-reads the last week from ESPN so finished matches get score, scorers and cards."""
    _serve(monkeypatch, [_real("Sweden"), _real("Armenia")])
    report = results_updater.backfill_from_espn(session, days=3, now=NOW)
    assert report["days"] == 1 and report["changed"] == 2  # only Sep 28 holds matches (the fake answers every slug)
    m = session.query(Match).filter_by(home_team_id="sweden").one()
    assert (m.status, m.home_goals, m.away_goals) == ("finished", 3, 1)
    ev = events_for_matches(session, [m])[m.id]
    assert len(ev["goals"]) == 4 and len(ev["cards"]) == 4
    # idempotent: a second run changes nothing
    assert results_updater.backfill_from_espn(session, days=3, now=NOW)["changed"] == 0


def test_backfill_is_a_noop_when_espn_is_disabled(session, monkeypatch):
    monkeypatch.setenv("ENABLE_ESPN", "false")
    monkeypatch.setattr(espn.requests, "get", lambda *a, **k: pytest.fail("must not call ESPN when disabled"))
    assert results_updater.backfill_from_espn(session, days=3, now=NOW) == {"days": 0, "fixtures": 0, "changed": 0}
