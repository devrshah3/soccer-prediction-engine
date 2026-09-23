"""Ingestion idempotency: running the same source rows through scripts/ingest.py's upsert
helpers twice must not duplicate matches. Uses a throwaway engine/session (not the module-level
singleton in kickcast_api.db) so this doesn't touch data/kickcast.db.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.models import Base, Match, Team

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
