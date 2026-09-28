from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.awards import get_awards, international_top_scorers
from kickcast_api.models import Base, Goalscorer, League, Match, Team


def seeded_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'awards.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add_all([Team(id="team-a", name="Team A", country=None), Team(id="team-b", name="Team B", country=None)])
    # A real current-season fixture per domestic league, so latest_season() resolves to
    # something other than domestic_scorers.SEASON_LABEL ("2024-25") - the two are
    # deliberately different seasons here, exactly like production, so a test asking for
    # "2024-25" explicitly exercises the "not current, but the one cached past season we
    # have" branch rather than the live-projection "current season" branch.
    for code, name in (("en.1", "EN"), ("es.1", "ES"), ("it.1", "IT"), ("de.1", "DE"), ("fr.1", "FR")):
        s.add(League(code=code, name=name, country=None, kind="domestic_league"))
        s.add(Match(
            league_code=code, season="2026-27", date=date(2026, 9, 1), kickoff=None,
            home_team_id="team-a", away_team_id="team-b", home_goals=1, away_goals=0,
            status="finished", round="Matchday 1", neutral=False,
            source="synthetic", source_id=f"synthetic:{code}",
        ))
    s.commit()
    today = datetime.now(timezone.utc).date()
    recent = today - timedelta(days=10)
    old = today - timedelta(days=800)
    s.add_all(
        [
            Goalscorer(date=recent, team_id="team-a", scorer_name="Striker One", minute=10, own_goal=False, penalty=False, source="synthetic"),
            Goalscorer(date=recent, team_id="team-a", scorer_name="Striker One", minute=50, own_goal=False, penalty=False, source="synthetic"),
            Goalscorer(date=recent, team_id="team-b", scorer_name="Striker Two", minute=20, own_goal=False, penalty=True, source="synthetic"),
            Goalscorer(date=recent, team_id="team-a", scorer_name="Defender X", minute=90, own_goal=True, penalty=False, source="synthetic"),
            Goalscorer(date=old, team_id="team-a", scorer_name="Old Timer", minute=30, own_goal=False, penalty=False, source="synthetic"),
        ]
    )
    s.commit()
    return s


def test_international_top_scorers_excludes_own_goals_and_old_data(tmp_path):
    s = seeded_session(tmp_path)
    scorers = international_top_scorers(s)
    names = {r["player"] for r in scorers}
    assert "Striker One" in names
    assert "Striker Two" in names
    assert "Defender X" not in names  # own goal excluded
    assert "Old Timer" not in names  # outside the 365-day lookback
    top = next(r for r in scorers if r["player"] == "Striker One")
    assert top["goals"] == 2


def test_get_awards_reports_international_scorers_and_honest_gaps(tmp_path, monkeypatch):
    """The current-season branch calls out to football-data.org (golden_boot_projection);
    a unit test must never hit the real network, so it's stubbed here - the real live
    call is verified separately (see this session's proof in the commit message and
    test_football_data_org.py)."""
    from kickcast_api import awards as awards_module

    monkeypatch.setattr(
        awards_module.golden_boot_projection, "project",
        lambda session, code: {"available": False, "reason": "stubbed for this unit test"},
    )
    s = seeded_session(tmp_path)
    out = get_awards(s)
    assert out["season"] == "2026-27"
    assert "by_league" in out["golden_boot"]
    for code in ("en.1", "es.1", "it.1", "de.1", "fr.1"):
        entry = out["golden_boot"]["by_league"][code]
        assert entry["available"] in (True, False)
        if not entry["available"]:
            assert entry["reason"]
    intl = out["golden_boot"]["international_top_scorers_also_available"]
    names = {r["player"] for r in intl["international_top_scorers"]}
    assert "Striker One" in names and "Defender X" not in names
    assert out["ballon_dor"]["available"] is False
    assert out["puskas"]["available"] is False
    for key in ("ballon_dor", "puskas"):
        assert out[key]["reason"]


def test_domestic_golden_boot_uses_real_cached_data_when_present(tmp_path):
    """When data/api_football_cache/ is populated (as it is in this dev environment - see
    scripts/fetch_api_football.py), the domestic Golden Boot must show real players with
    a plausible single-season goal/appearance shape, not placeholder or fabricated data."""
    from kickcast_api import domestic_scorers

    if not domestic_scorers.available("es.1"):
        return  # no cache in this environment (e.g. CI without it) - nothing to check here
    s = seeded_session(tmp_path)
    # Explicit past season, not "2026-27" (the seeded current one) - exercises the "not
    # current, but the one cached past season we have" branch, never touching the live
    # football-data.org projection path (no network in this test).
    out = get_awards(s, season=domestic_scorers.SEASON_LABEL)
    la_liga = out["golden_boot"]["by_league"]["es.1"]
    assert la_liga["available"] is True
    assert la_liga["season"] == domestic_scorers.SEASON_LABEL
    assert la_liga["tag"] == "Final"
    assert la_liga["top_scorers"], "expected at least one real scorer"
    top = la_liga["top_scorers"][0]
    assert top["goals"] > 0
    assert top["appearances"] <= 38  # data-quality filter: a real single season, not cumulative


def test_get_awards_never_silently_falls_back_for_an_unmapped_season(tmp_path):
    """An explicit season that is neither the current one nor the one past season we have
    real cached data for must say so honestly - never substitute a different season's
    numbers. No network/projection call should happen for this season at all."""
    s = seeded_session(tmp_path)
    out = get_awards(s, season="2015-16")
    assert out["season"] == "2015-16"
    for code, entry in out["golden_boot"]["by_league"].items():
        assert entry["available"] is False, code
        assert "2015-16" in entry["reason"]
    # The default-view-only international scorers block must not leak into a past-season view.
    assert "international_top_scorers_also_available" not in out["golden_boot"]


def test_champions_league_has_no_past_season_data_source(tmp_path):
    """domestic_scorers only covers the 5 domestic leagues - CL must never fall through to
    someone else's cached data for a past season, even if the season string matches."""
    from kickcast_api import domestic_scorers

    s = seeded_session(tmp_path)
    out = get_awards(s, season=domestic_scorers.SEASON_LABEL)
    cl = out["golden_boot"]["by_league"]["CL"]
    assert cl["available"] is False
    assert domestic_scorers.SEASON_LABEL in cl["reason"]
