from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.awards import get_awards, international_top_scorers
from kickcast_api.models import Base, Goalscorer, Team


def seeded_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'awards.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add_all([Team(id="team-a", name="Team A", country=None), Team(id="team-b", name="Team B", country=None)])
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


def test_get_awards_reports_international_scorers_and_honest_gaps(tmp_path):
    s = seeded_session(tmp_path)
    out = get_awards(s)
    # golden_boot's availability now depends on whether data/api_football_cache/ exists in
    # THIS environment (real cached data if scripts/fetch_api_football.py has run, absent
    # on e.g. a bare clone) - both are legitimate, so don't assert a fixed value; just
    # assert the shape is honest either way.
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
    out = get_awards(s)
    la_liga = out["golden_boot"]["by_league"]["es.1"]
    assert la_liga["available"] is True
    assert la_liga["season"] == domestic_scorers.SEASON_LABEL
    assert la_liga["top_scorers"], "expected at least one real scorer"
    top = la_liga["top_scorers"][0]
    assert top["goals"] > 0
    assert top["appearances"] <= 38  # data-quality filter: a real single season, not cumulative
