"""kickcast_api/db.py's small migration helper: create_all() only creates missing
tables, never alters an existing one, so a database file created before Match.
previous_date/previous_kickoff existed needs a real ALTER TABLE - this is the substitute
for a full migration framework (Alembic etc. would be overkill for one additive column
pair on one table).
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from kickcast_api.db import init_db
from kickcast_api.models import Base


def test_init_db_adds_missing_columns_to_an_old_schema(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old_schema.db'}")
    # Simulate a database created before previous_date/previous_kickoff existed: create
    # every table, then drop those two columns back off "matches" by rebuilding it
    # without them (SQLite has no DROP COLUMN before 3.35 - rebuild is the real technique).
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        cols = [c["name"] for c in inspect(engine).get_columns("matches") if c["name"] not in ("previous_date", "previous_kickoff")]
        col_list = ", ".join(cols)
        conn.execute(text(f"CREATE TABLE matches_old AS SELECT {col_list} FROM matches"))
        conn.execute(text("DROP TABLE matches"))
        conn.execute(text("ALTER TABLE matches_old RENAME TO matches"))

    before = {c["name"] for c in inspect(engine).get_columns("matches")}
    assert "previous_date" not in before and "previous_kickoff" not in before

    init_db(engine)

    after = {c["name"] for c in inspect(engine).get_columns("matches")}
    assert "previous_date" in after and "previous_kickoff" in after


def test_init_db_is_idempotent_on_an_already_migrated_schema(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'new_schema.db'}")
    init_db(engine)
    init_db(engine)  # must not raise (e.g. "duplicate column") on a second run
    cols = {c["name"] for c in inspect(engine).get_columns("matches")}
    assert "previous_date" in cols and "previous_kickoff" in cols
