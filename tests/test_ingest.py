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

from kickcast_api.models import Base, Match

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
