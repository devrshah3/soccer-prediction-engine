from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api import football_data_scorers, golden_boot_projection
from kickcast_api.models import Base, League, Match, Team

FAKE_SCORERS_PAYLOAD = {
    "season": {"startDate": "2026-08-21", "endDate": "2027-05-30"},
    "scorers": [
        {"player": {"name": "Big Striker"}, "team": {"name": "Alpha FC"}, "goals": 10, "playedMatches": 5},
        {"player": {"name": "Steady Forward"}, "team": {"name": "Beta United"}, "goals": 4, "playedMatches": 5},
        {"player": {"name": "Slow Starter"}, "team": {"name": "Alpha FC"}, "goals": 1, "playedMatches": 5},
    ],
}


@pytest.fixture(autouse=True)
def _clear_scorer_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(football_data_scorers, "CACHE_DIR", tmp_path / "fd_scorer_cache")


def seeded_session(tmp_path, db_name="gbp.db"):
    engine = create_engine(f"sqlite:///{tmp_path / db_name}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(League(code="test.1", name="Test League", country="Testland", kind="domestic_league"))
    s.add_all([Team(id="alpha fc", name="Alpha FC"), Team(id="beta united", name="Beta United")])
    s.commit()
    # 5 played matches each (matches playedMatches above), then remaining scheduled ones.
    d = date(2026, 8, 1)
    for i in range(5):
        s.add(Match(
            league_code="test.1", season="2026-27", date=d, kickoff=None,
            home_team_id="alpha fc", away_team_id="beta united", home_goals=1, away_goals=0,
            status="finished", round=f"Matchday {i + 1}", neutral=False,
            source="synthetic", source_id=f"synthetic:played-{i}",
        ))
        d += timedelta(days=7)
    # Alpha FC has 3 remaining scheduled matches, Beta United has 1.
    for i in range(3):
        s.add(Match(
            league_code="test.1", season="2026-27", date=date(2027, 1, i + 1), kickoff=None,
            home_team_id="alpha fc", away_team_id="team-x", home_goals=None, away_goals=None,
            status="scheduled", round="Later", neutral=False,
            source="synthetic", source_id=f"synthetic:alpha-remaining-{i}",
        ))
    s.add(Match(
        league_code="test.1", season="2026-27", date=date(2027, 2, 1), kickoff=None,
        home_team_id="beta united", away_team_id="team-y", home_goals=None, away_goals=None,
        status="scheduled", round="Later", neutral=False,
        source="synthetic", source_id="synthetic:beta-remaining-0",
    ))
    s.commit()
    return s


def test_fetch_scorers_parses_and_caches(tmp_path, monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_ORG_API_KEY", "fake-key")
    monkeypatch.setattr(football_data_scorers, "FD_CODES", {"test.1": "TL"})
    calls = []

    def fake_get(path, params=None):
        calls.append(path)
        return FAKE_SCORERS_PAYLOAD

    monkeypatch.setattr(football_data_scorers.football_data_org, "get", fake_get)
    result = football_data_scorers.fetch_scorers("test.1")
    assert result["season_label"] == "2026-27"
    names = {s["player"] for s in result["scorers"]}
    assert names == {"Big Striker", "Steady Forward", "Slow Starter"}
    assert result["scorers"][0]["team_id"] == "alpha"  # canonical() strips "FC"

    # Second call within the TTL must hit the cache, not the network again.
    football_data_scorers.fetch_scorers("test.1")
    assert calls == ["/competitions/TL/scorers"]


def test_fetch_scorers_returns_none_for_unmapped_competition():
    assert football_data_scorers.fetch_scorers("some-unmapped-code") is None


def test_project_shrinks_outlier_rate_and_uses_real_remaining_matches(tmp_path, monkeypatch):
    # team_id in this fake payload matches the seeded Match rows' team ids directly - this
    # test is about project()'s DB-driven remaining-matches/shrinkage logic, not the
    # football-data.org name crosswalk (covered separately above).
    fake_scorers = [
        {"player": "Big Striker", "team_id": "alpha fc", "team_name": "Alpha FC", "goals": 10, "played_matches": 5},
        {"player": "Steady Forward", "team_id": "beta united", "team_name": "Beta United", "goals": 4, "played_matches": 5},
        {"player": "Slow Starter", "team_id": "alpha fc", "team_name": "Alpha FC", "goals": 1, "played_matches": 5},
    ]
    monkeypatch.setattr(
        football_data_scorers, "fetch_scorers",
        lambda code, limit=15, network=True: {"season_label": "2026-27", "scorers": fake_scorers},
    )
    s = seeded_session(tmp_path)
    result = golden_boot_projection.project(s, "test.1")

    assert result["available"] is True
    assert result["season"] == "2026-27"
    by_player = {r["player"]: r for r in result["scorers"]}

    # Real remaining-matches counts from the DB, not guessed.
    assert by_player["Big Striker"]["remaining_matches"] == 3
    assert by_player["Steady Forward"]["remaining_matches"] == 1

    # Shrinkage: "Slow Starter" (1 goal/5 played, rate 0.2) sits below the group's average
    # rate; blending toward the mean must project them ABOVE a naive 0.2-rate extrapolation.
    naive_slow_starter = 1 + (1 / 5) * 3
    assert by_player["Slow Starter"]["projected_final"] > naive_slow_starter

    # Every candidate's top-scorer chance is a real probability, and the tightest range
    # bound never exceeds the loosest.
    total_chance = sum(r["top_scorer_chance"] for r in result["scorers"])
    assert 0.9 <= total_chance <= 1.0 + 1e-9
    for r in result["scorers"]:
        assert 0.0 <= r["top_scorer_chance"] <= 1.0
        assert r["projected_range"][0] <= r["projected_range"][1]


def test_project_reports_unavailable_when_live_source_has_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(football_data_scorers, "fetch_scorers", lambda code, limit=15, network=True: None)
    s = seeded_session(tmp_path, "gbp2.db")
    result = golden_boot_projection.project(s, "test.1")
    assert result["available"] is False
    assert result["reason"]
