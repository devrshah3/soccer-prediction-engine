"""Item 6: Replay = yesterday only - local-date maths against a mocked clock, real-event
handling (complete/partial/none), pre-match-prediction-vs-result, and grounded recaps."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api import replay
from kickcast_api.assistant import gemini_client, quota
from kickcast_api.db import get_session
from kickcast_api.main import app
from kickcast_api.models import Base, Goalscorer, League, Match, PrecomputedPrediction, Team
from kickcast_api.routes.replay import local_yesterday

YESTERDAY = date(2026, 9, 27)


def _pred(home: float, draw: float, away: float) -> str:
    return json.dumps({
        "model_version": "dixon-coles-v1", "as_of": "2026-09-20", "evidence": "A",
        "probabilities": {"home": home, "draw": draw, "away": away},
    })


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'replay.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add_all([
        League(code="international", name="International", country=None, kind="international"),
        League(code="en.1", name="Premier League", country="England", kind="domestic_league"),
    ])
    for tid, name in (("serbia", "Serbia"), ("netherlands", "Netherlands"), ("denmark", "Denmark"),
                      ("wales", "Wales"), ("arsenal", "Arsenal"), ("leeds", "Leeds")):
        s.add(Team(id=tid, name=name))
    s.commit()

    def add(id_, league, home, away, hg, ag, status, d=YESTERDAY, kickoff="16:00", rnd="Matchday 1"):
        s.add(Match(
            id=id_, league_code=league, season="2026-27", date=d, kickoff=kickoff, home_team_id=home,
            away_team_id=away, home_goals=hg, away_goals=ag, status=status, round=rnd, neutral=False,
            source="synthetic", source_id=f"synthetic:{id_}",
        ))

    add(1, "international", "serbia", "netherlands", 1, 2, "finished")          # complete events
    add(2, "international", "denmark", "wales", 3, 0, "finished")               # partial events
    add(3, "en.1", "arsenal", "leeds", 1, 1, "finished")                         # no events source
    add(4, "international", "wales", "serbia", None, None, "not_played")         # no result yet
    add(5, "international", "leeds", "arsenal", None, None, "finished", d=date(2026, 9, 20))  # other day
    s.commit()
    s.add_all([
        Goalscorer(match_id=1, date=YESTERDAY, team_id="serbia", scorer_name="A Striker", minute=10, own_goal=False, penalty=False, source="synthetic"),
        Goalscorer(match_id=1, date=YESTERDAY, team_id="netherlands", scorer_name="B Winger", minute=55, own_goal=False, penalty=True, source="synthetic"),
        Goalscorer(match_id=1, date=YESTERDAY, team_id="netherlands", scorer_name="C Defender", minute=88, own_goal=True, penalty=False, source="synthetic"),
        Goalscorer(match_id=2, date=YESTERDAY, team_id="denmark", scorer_name="D Forward", minute=20, own_goal=False, penalty=False, source="synthetic"),
    ])
    s.add(PrecomputedPrediction(match_id=1, prediction_json=_pred(0.5, 0.25, 0.25), model_version="dixon-coles-v1", computed_at="2026-09-26T00:00:00+00:00", data_cutoff="2026-09-20"))
    s.add(PrecomputedPrediction(match_id=3, prediction_json=_pred(0.2, 0.3, 0.5), model_version="dixon-coles-v1", computed_at="2026-09-26T00:00:00+00:00", data_cutoff="2026-09-20"))
    s.commit()
    return s


def _by_id(result):
    return {m["id"]: m for m in result["matches"]}


# ------------------------------------------------------------- local date (mocked clock)


def test_local_yesterday_uses_the_viewers_offset_not_utc():
    now = datetime(2026, 9, 28, 2, 0, tzinfo=UTC)  # 02:00 UTC
    assert local_yesterday(0, now) == date(2026, 9, 27)
    # US Eastern (UTC-4): it is still 22:00 on Sep 27 locally, so "yesterday" is Sep 26.
    assert local_yesterday(-240, now) == date(2026, 9, 26)
    # UTC+10: already 12:00 on Sep 28 locally, so yesterday is Sep 27.
    assert local_yesterday(600, now) == date(2026, 9, 27)


def test_a_late_kickoff_belongs_to_the_viewers_local_day(session):
    session.add(Match(
        id=50, league_code="international", season="2026-27", date=date(2026, 9, 28), kickoff="01:00",
        home_team_id="serbia", away_team_id="wales", home_goals=None, away_goals=None, status="not_played",
        round="x", neutral=False, source="synthetic", source_id="synthetic:50",
    ))
    session.commit()
    eastern = {m.id for m in replay.matches_on_local_date(session, YESTERDAY, -240)}
    utc = {m.id for m in replay.matches_on_local_date(session, YESTERDAY, 0)}
    assert 50 in eastern and 50 not in utc


def test_only_the_requested_local_day_is_listed(session):
    ids = {m.id for m in replay.matches_on_local_date(session, YESTERDAY, 0)}
    assert ids == {1, 2, 3, 4}  # match 5 (Sep 20) never appears


# ------------------------------------------------------------- events and results


def test_complete_events_are_tagged_and_ordered(session):
    m = _by_id(replay.day_replay(session, YESTERDAY, 0))[1]
    assert m["events_status"] == "complete"
    assert [(e["minute"], e["player"]) for e in m["events"]] == [(10, "A Striker"), (55, "B Winger"), (88, "C Defender")]
    assert m["events"][1]["penalty"] is True and m["events"][2]["own_goal"] is True


def test_partial_and_missing_events_are_labelled_honestly(session):
    by_id = _by_id(replay.day_replay(session, YESTERDAY, 0))
    assert by_id[2]["events_status"] == "partial"      # 3 goals, 1 recorded scorer
    assert by_id[3]["events_status"] == "none"         # 1-1 club match, no source
    assert "Only 1 of the 3 goals" in by_id[2]["recap"]["text"]
    assert "not available" in by_id[3]["recap"]["text"]


def test_match_without_a_result_shows_no_score_and_says_so(session):
    m = _by_id(replay.day_replay(session, YESTERDAY, 0))[4]
    assert m["has_result"] is False and m["home_goals"] is None
    assert m["events_status"] is None and m["prediction_result"] is None
    assert "No result has been recorded" in m["recap"]["text"]


def test_prediction_vs_result_chip_data(session):
    by_id = _by_id(replay.day_replay(session, YESTERDAY, 0))
    hit = by_id[1]["prediction_result"]  # model favoured home (50%), away won
    assert (hit["predicted"], hit["actual"], hit["correct"]) == ("home", "away", False)
    assert hit["actual_probability"] == 0.25
    miss = by_id[3]["prediction_result"]  # model favoured away (50%), 1-1 draw
    assert (miss["predicted"], miss["actual"], miss["correct"]) == ("away", "draw", False)
    assert by_id[2]["prediction"] is None  # never a live re-prediction of a played match


def test_empty_day_points_to_the_most_recent_day_with_matches(session):
    result = replay.day_replay(session, date(2026, 9, 22), 0)
    assert result["matches"] == []
    assert result["most_recent_day_with_matches"] == "2026-09-20"


def test_day_with_no_results_points_to_the_most_recent_day_with_results(session):
    # Only match 4 (no result) exists on this local day -> offer the latest day WITH results.
    session.add(Match(
        id=60, league_code="international", season="2026-27", date=date(2026, 9, 23), kickoff="16:00",
        home_team_id="serbia", away_team_id="wales", home_goals=None, away_goals=None, status="not_played",
        round="x", neutral=False, source="synthetic", source_id="synthetic:60",
    ))
    session.commit()
    result = replay.day_replay(session, date(2026, 9, 23), 0)
    assert result["most_recent_day_with_results"] == "2026-09-20"


def test_no_statsbomb_or_2015_16_anywhere_in_the_payload(session):
    blob = json.dumps(replay.day_replay(session, YESTERDAY, 0)).lower()
    assert "statsbomb" not in blob and "2015" not in blob


# ------------------------------------------------------------- recaps


def test_recap_defaults_to_a_labelled_template_from_verified_facts_only(session):
    m = _by_id(replay.day_replay(session, YESTERDAY, 0))[1]
    assert m["recap"]["mode"] == "template"
    assert m["recap"]["label"] == "Recap written from verified match data"
    assert "Serbia 1-2 Netherlands" in m["recap"]["text"]
    assert "B Winger for Netherlands, 55' (penalty)" in m["recap"]["text"]


def _enable_gemini(monkeypatch, reply):
    calls = []
    monkeypatch.setattr(gemini_client, "gemini_for_lookups_enabled", lambda: True)
    monkeypatch.setattr(gemini_client, "available", lambda: True)
    monkeypatch.setattr(quota, "gemini_quota_remaining", lambda s: 20)

    def fake(session, question, context, label):
        calls.append(context)
        return {"text": reply}

    monkeypatch.setattr(gemini_client, "ask_gemini_with_context", fake)
    return calls


def test_grounded_gemini_recap_is_used_and_cached(session, monkeypatch):
    calls = _enable_gemini(monkeypatch, "Netherlands came from behind to win 2-1 in Serbia.")
    first = _by_id(replay.day_replay(session, YESTERDAY, 0))[1]["recap"]
    assert first["mode"] == "gemini"

    def match1_calls():
        return [c for c in calls if "Serbia 1-2 Netherlands" in c]

    assert len(match1_calls()) == 1
    second = _by_id(replay.day_replay(session, YESTERDAY, 0))[1]["recap"]
    assert second["mode"] == "gemini" and len(match1_calls()) == 1  # served from the shared cache


def test_a_rejected_gemini_rewrite_is_not_retried_on_every_page_view(session, monkeypatch):
    calls = _enable_gemini(monkeypatch, "Netherlands won 2-1 after a 93rd minute winner.")
    replay.day_replay(session, YESTERDAY, 0)
    n = len(calls)
    replay.day_replay(session, YESTERDAY, 0)
    assert len(calls) == n


def test_gemini_recap_with_an_invented_number_is_rejected(session, monkeypatch):
    _enable_gemini(monkeypatch, "Netherlands won 2-1 after a 93rd minute winner.")
    assert _by_id(replay.day_replay(session, YESTERDAY, 0))[1]["recap"]["mode"] == "template"


def test_gemini_is_skipped_when_quota_is_at_the_reserve(session, monkeypatch):
    calls = _enable_gemini(monkeypatch, "Netherlands won 2-1.")
    monkeypatch.setattr(quota, "gemini_quota_remaining", lambda s: replay.GEMINI_RECAP_RESERVE)
    assert _by_id(replay.day_replay(session, YESTERDAY, 0))[1]["recap"]["mode"] == "template"
    assert calls == []


# ------------------------------------------------------------- route


def test_route_never_serves_today_or_later_and_old_statsbomb_routes_are_gone(session):
    def override():
        yield session

    app.dependency_overrides[get_session] = override
    try:
        c = TestClient(app)
        assert c.get("/replay/day?tz=0").json()["date"] == local_yesterday(0).isoformat()
        assert c.get("/replay/day?date=2999-01-01").status_code == 400
        assert c.get("/replay/day?tz=9999").status_code == 400
        assert c.get("/replay/matches").status_code == 404
        assert c.get("/replay/matches/anything").status_code == 404
    finally:
        app.dependency_overrides.clear()
