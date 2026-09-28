"""kickcast_api/seed.py: open-licensed-only export, non-destructive load."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api import seed
from kickcast_api.models import Base, Goalscorer, League, LiveEvent, LiveMatchState, Match, MatchStats, Team

OPEN = "martj42/international_results"


def _db(path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(League(code="international", name="I", country=None, kind="international"))
    s.add_all([Team(id=t, name=t, country=None) for t in ("a", "b", "c", "d", "e", "f")])
    s.commit()
    return s


def _match(s, h, a, status, hg=None, ag=None, source=OPEN, day=1):
    m = Match(league_code="international", season="2026", date=date(2026, 9, day), kickoff="16:00", home_team_id=h,
              away_team_id=a, home_goals=hg, away_goals=ag, status=status, round=None, neutral=False,
              source=source, source_id=f"{h}{a}")
    s.add(m)
    s.commit()
    return m


@pytest.fixture
def source_db(tmp_path):
    s = _db(tmp_path / "src.db")
    open_m = _match(s, "a", "b", "finished", 2, 1)
    s.add(Goalscorer(match_id=open_m.id, date=open_m.date, team_id="a", scorer_name="Open Scorer", minute=5, own_goal=False, penalty=True, source=OPEN))
    s.add(MatchStats(match_id=open_m.id, home_shots=10, source="football-data.co.uk"))
    espn_m = _match(s, "c", "d", "finished", 3, 0, source=OPEN, day=2)  # result touched by ESPN -> must NOT be exported
    s.add(LiveMatchState(match_id=espn_m.id, match_status="FT", home_score=3, away_score=0, last_updated_at="x", source="espn"))
    s.add(LiveEvent(match_id=espn_m.id, minute=9, event_type="goal", team_id="c", player="ESPN Scorer", detail="Normal Goal", source="espn"))
    _match(s, "e", "f", "finished", 1, 0, source="UEFA.com fixture list", day=3)  # non-open source -> not exported
    return s


def test_export_contains_only_open_licensed_rows(source_db, tmp_path):
    snap = seed.export_snapshot(source_db, date(2026, 8, 1))
    assert [r[:4] for r in snap["results"]] == [["international", "2026-09-01", "a", "b"]]
    assert [g[5] for g in snap["goals"]] == ["Open Scorer"]
    path = tmp_path / "seed.json.gz"
    seed.write_snapshot(snap, path)
    raw = __import__("gzip").open(path, "rt").read()
    assert "ESPN Scorer" not in raw and '"espn"' not in raw.lower()


def test_load_fills_a_fresh_db_and_never_overwrites(source_db, tmp_path):
    path = tmp_path / "seed.json.gz"
    seed.write_snapshot(seed.export_snapshot(source_db, date(2026, 8, 1)), path)

    fresh = _db(tmp_path / "fresh.db")
    a_b = _match(fresh, "a", "b", "scheduled")           # the build snapshot lacks the result
    c_d = _match(fresh, "c", "d", "scheduled", day=2)    # not in the seed at all
    assert seed.load_seed(fresh, path) == {"results": 1, "goals": 1, "stats": 1}
    fresh.refresh(a_b)
    assert (a_b.status, a_b.home_goals, a_b.away_goals) == ("finished", 2, 1)
    fresh.refresh(c_d)
    assert c_d.status == "scheduled"
    assert [g.scorer_name for g in fresh.query(Goalscorer)] == ["Open Scorer"]

    # idempotent, and a result already in the DB (e.g. newer, from a live source) is kept
    assert seed.load_seed(fresh, path) == {"results": 0, "goals": 0, "stats": 0}
    a_b.home_goals = 9
    fresh.commit()
    seed.load_seed(fresh, path)
    fresh.refresh(a_b)
    assert a_b.home_goals == 9


def test_missing_seed_file_is_a_noop(tmp_path):
    assert seed.load_seed(_db(tmp_path / "x.db"), tmp_path / "nope.json.gz") == {"results": 0, "goals": 0, "stats": 0}


def test_committed_seed_is_small_and_loadable():
    assert seed.SEED_PATH.exists() and seed.SEED_PATH.stat().st_size < 5 * 1024 * 1024
