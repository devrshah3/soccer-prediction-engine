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


def test_get_awards_reports_domestic_gaps_honestly(tmp_path):
    s = seeded_session(tmp_path)
    out = get_awards(s)
    assert out["golden_boot"]["available"] is False
    assert "international_top_scorers" in out["golden_boot"]
    assert out["ballon_dor"]["available"] is False
    assert out["puskas"]["available"] is False
    # every "not available" entry states why, never silently empty
    for key in ("golden_boot", "ballon_dor", "puskas"):
        assert out[key]["reason"]
