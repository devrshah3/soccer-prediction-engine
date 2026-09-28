"""Ingestion idempotency: running the same source rows through scripts/ingest.py's upsert
helpers twice must not duplicate matches. Uses a throwaway engine/session (not the module-level
singleton in kickcast_api.db) so this doesn't touch data/kickcast.db.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api import football_data_org
from kickcast_api.models import Base, League, Match, Team

REPO_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ingest", REPO_ROOT / "scripts" / "ingest.py")
assert spec and spec.loader
ingest = importlib.util.module_from_spec(spec)
sys.modules["ingest"] = ingest
spec.loader.exec_module(ingest)


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test_ingest.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_upsert_match_relabels_a_past_dated_scheduled_row_as_not_played(tmp_path):
    """A2: a source reporting "scheduled" (no final score) for a match whose date has
    already passed - a postponed/abandoned fixture it never updated, or an old-season data
    gap - must not be treated as a real upcoming fixture. This is what let stale rows
    (fr.1 2019-20, es.1/it.1's 2024-25 finale) surface as "next match" on real pages."""
    session = _session(tmp_path)
    existing, by_round = {}, {}
    key = ("test.1", (datetime.now(UTC) - timedelta(days=30)).date(), "home", "away")
    m = ingest.upsert_match(session, existing, by_round, key, {"season": "2024-25", "kickoff": None, "status": "scheduled"})
    assert m.status == "not_played"


def test_upsert_match_keeps_a_future_scheduled_row_scheduled(tmp_path):
    session = _session(tmp_path)
    existing, by_round = {}, {}
    key = ("test.1", (datetime.now(UTC) + timedelta(days=30)).date(), "home", "away")
    m = ingest.upsert_match(session, existing, by_round, key, {"season": "2026-27", "kickoff": None, "status": "scheduled"})
    assert m.status == "scheduled"


def test_upsert_match_leaves_finished_rows_alone_regardless_of_date(tmp_path):
    session = _session(tmp_path)
    existing, by_round = {}, {}
    key = ("test.1", (datetime.now(UTC) - timedelta(days=30)).date(), "home", "away")
    m = ingest.upsert_match(
        session, existing, by_round, key,
        {"season": "2024-25", "kickoff": None, "status": "finished", "home_goals": 1, "away_goals": 0},
    )
    assert m.status == "finished"


def test_upsert_match_records_history_when_a_fixture_moves_by_round(tmp_path):
    """C.9: the same fixture (matched by league/season/round/teams) now reported on a
    different date/kickoff - update in place, keep the old date/kickoff rather than
    silently discarding them, and don't create a duplicate row."""
    session = _session(tmp_path)
    existing, by_round = {}, {}
    original_date = (datetime.now(UTC) + timedelta(days=10)).date()
    key1 = ("test.1", original_date, "home", "away")
    m1 = ingest.upsert_match(
        session, existing, by_round, key1,
        {
            "season": "2026-27", "kickoff": "15:00", "status": "scheduled", "round": "Matchday 5",
            "source": "synthetic", "source_id": "synthetic:1",
        },
    )
    session.flush()
    match_id = m1.id

    moved_date = original_date + timedelta(days=2)
    key2 = ("test.1", moved_date, "home", "away")
    m2 = ingest.upsert_match(
        session, existing, by_round, key2,
        {"season": "2026-27", "kickoff": "18:00", "status": "scheduled", "round": "Matchday 5"},
    )
    assert m2.id == match_id  # same row, not a new one
    assert m2.date == moved_date
    assert m2.previous_date == original_date
    assert m2.previous_kickoff == "15:00"


def test_upsert_match_does_not_match_across_different_teams_with_the_same_round(tmp_path):
    session = _session(tmp_path)
    existing, by_round = {}, {}
    d1 = (datetime.now(UTC) + timedelta(days=10)).date()
    ingest.upsert_match(
        session, existing, by_round, ("test.1", d1, "home", "away"),
        {"season": "2026-27", "kickoff": "15:00", "status": "scheduled", "round": "Matchday 5"},
    )
    d2 = (datetime.now(UTC) + timedelta(days=11)).date()
    m2 = ingest.upsert_match(
        session, existing, by_round, ("test.1", d2, "other-home", "other-away"),
        {"season": "2026-27", "kickoff": "15:00", "status": "scheduled", "round": "Matchday 5"},
    )
    assert m2.home_team_id == "other-home"
    assert m2.previous_date is None  # a genuinely different fixture, not a moved one


def test_domestic_ingest_is_idempotent(tmp_path):
    session = _session(tmp_path)
    n1 = ingest.ingest_domestic(session, "en.1", "E0", "Premier League", "England")
    session.commit()
    count1 = session.query(Match).count()
    assert count1 > 0 and n1 > 0

    n2 = ingest.ingest_domestic(session, "en.1", "E0", "Premier League", "England")
    session.commit()
    count2 = session.query(Match).count()
    assert n2 == n1  # same rows processed
    assert count2 == count1  # no duplicates inserted


def test_international_ingest_is_idempotent(tmp_path):
    session = _session(tmp_path)
    ingest.ingest_international(session)
    session.commit()
    count1 = session.query(Match).filter(Match.league_code == "international").count()
    assert count1 > 0

    ingest.ingest_international(session)
    session.commit()
    count2 = session.query(Match).filter(Match.league_code == "international").count()
    assert count2 == count1


def test_real_madrid_survives_international_ingest_without_id_collision(tmp_path):
    """Real bug found while wiring the assistant: results.csv has a genuine 2013 friendly
    between Spanish REGIONAL sides, "Madrid" vs "Andalusia" (2013-06-07) - slug("Madrid")
    collides with canonical("Real Madrid") == "madrid" (canonical() strips the "Real "
    prefix). Ingesting international results AFTER domestic leagues used to silently
    overwrite the club's Team row with the regional side's name - breaking every
    Real Madrid lookup (predictions, the assistant's resolve_team tool, etc). Domestic
    ingestion must run first so ingest_international can see and avoid the collision."""
    session = _session(tmp_path)
    ingest.ingest_domestic(session, "es.1", "SP1", "La Liga", "Spain")
    session.commit()
    real_madrid = session.get(Team, "madrid")
    assert real_madrid is not None and real_madrid.name == "Real Madrid"

    ingest.ingest_international(session)
    session.commit()

    real_madrid_after = session.get(Team, "madrid")
    assert real_madrid_after.name == "Real Madrid", (
        "Real Madrid's club Team row was overwritten by the international ingest - "
        "the id-collision disambiguation in _domestic_team_ids/_intl_team_id regressed"
    )
    regional_side = session.get(Team, "madrid-intl")
    assert regional_side is not None and regional_side.name == "Madrid"
    regional_match = (
        session.query(Match)
        .filter(Match.league_code == "international", Match.home_team_id == "madrid-intl")
        .first()
    )
    assert regional_match is not None and regional_match.away_team_id == "andalusia"


FAKE_CL_PAYLOAD = {
    "matches": [
        {
            "id": 900001,
            "season": {"startDate": "2026-09-08", "endDate": "2027-01-27"},
            "utcDate": "2026-09-08T16:45:00Z",
            "status": "FINISHED",
            "matchday": 1,
            "stage": "LEAGUE_STAGE",
            "homeTeam": {"name": "Real Madrid CF"},
            "awayTeam": {"name": "Club Brugge KV"},
            "score": {"fullTime": {"home": 3, "away": 1}},
        },
        {
            "id": 900002,
            "season": {"startDate": "2026-09-08", "endDate": "2027-01-27"},
            "utcDate": "2026-10-01T19:00:00Z",
            "status": "TIMED",
            "matchday": 2,
            "stage": "LEAGUE_STAGE",
            "homeTeam": {"name": "Club Brugge KV"},
            "awayTeam": {"name": "Real Madrid CF"},
            "score": {"fullTime": {"home": None, "away": None}},
        },
    ]
}


def test_champions_league_ingest_is_a_noop_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("FOOTBALL_DATA_ORG_API_KEY", raising=False)
    session = _session(tmp_path)
    assert ingest.ingest_champions_league(session) == 0
    assert session.query(Match).filter(Match.league_code == "CL").count() == 0


def test_champions_league_ingest_real_shape_and_idempotency(tmp_path, monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_ORG_API_KEY", "fake-key")
    monkeypatch.setattr(football_data_org, "get", lambda path, params=None: FAKE_CL_PAYLOAD)

    session = _session(tmp_path)
    n1 = ingest.ingest_champions_league(session)
    session.commit()
    assert n1 == 2
    league = session.get(League, "CL")
    assert league is not None and league.kind == "continental_cup"

    finished = session.query(Match).filter(Match.league_code == "CL", Match.status == "finished").one()
    assert finished.home_goals == 3 and finished.away_goals == 1
    assert finished.season == "2026-27"
    assert finished.kickoff == "16:45"  # utcDate is already real UTC - no conversion needed
    assert finished.round == "LEAGUE_STAGE MD1"

    scheduled = session.query(Match).filter(Match.league_code == "CL", Match.status == "scheduled").one()
    assert scheduled.home_goals is None and scheduled.away_goals is None

    n2 = ingest.ingest_champions_league(session)
    session.commit()
    assert n2 == 2  # same rows re-processed
    assert session.query(Match).filter(Match.league_code == "CL").count() == 2  # no duplicates


def test_champions_league_ingest_never_overwrites_an_existing_teams_name_or_country(tmp_path, monkeypatch):
    """Real bug avoided (same class as the Real Madrid/regional-side collision):
    football-data.org's match payload has no usable per-team country field, so CL
    ingestion must never blindly overwrite a team that already exists from domestic
    ingestion (e.g. Real Madrid, correctly "Real Madrid"/"Spain" from La Liga)."""
    monkeypatch.setenv("FOOTBALL_DATA_ORG_API_KEY", "fake-key")
    monkeypatch.setattr(ingest.football_data_org, "get", lambda path, params=None: FAKE_CL_PAYLOAD)

    session = _session(tmp_path)
    ingest.ingest_domestic(session, "es.1", "SP1", "La Liga", "Spain")
    session.commit()
    real_madrid_before = session.get(Team, "madrid")
    assert real_madrid_before.name == "Real Madrid" and real_madrid_before.country == "Spain"

    ingest.ingest_champions_league(session)
    session.commit()

    real_madrid_after = session.get(Team, "madrid")
    assert real_madrid_after.name == "Real Madrid" and real_madrid_after.country == "Spain"
    brugge = session.get(Team, "brugge kv")  # canonical_id() strips the "club " prefix
    assert brugge is not None  # a genuinely new CL-only club still gets created
