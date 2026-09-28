"""Engine/session setup. Default DB is data/kickcast.db (gitignored build artifact,
rebuilt by scripts/ingest.py); override with KICKCAST_DB_PATH (used by tests to point
at a throwaway file/`:memory:`-equivalent temp path).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

REPO_ROOT = Path(__file__).resolve().parents[1]


def _db_path() -> Path:
    return Path(os.environ.get("KICKCAST_DB_PATH", REPO_ROOT / "data" / "kickcast.db"))


def make_engine(db_path: Path | None = None):
    path = db_path or _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Default QueuePool (size 5, overflow 10 = 15 total) is too small for this API: a single
    # page load fans out into dozens of concurrent per-request DB sessions (e.g. the homepage
    # firing one request per league's fixtures plus one per candidate prediction), which was
    # exhausting the pool and surfacing as real 500s (sqlalchemy.exc.TimeoutError) under
    # ordinary browsing, not just heavy load. pool_pre_ping avoids handing out a connection
    # that's gone stale (e.g. after the SQLite file was replaced by a fresh ingest.py run).
    return create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        pool_size=20,
        max_overflow=20,
        pool_pre_ping=True,
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# C.9: SQLAlchemy's create_all() only creates MISSING TABLES - it never alters an
# existing one, so a real column added to an existing model (like Match.previous_date/
# previous_kickoff) needs an explicit ALTER TABLE against a database file created before
# that column existed. This project has no migration framework (Alembic etc. would be
# overkill here); this is a small, idempotent, additive-only substitute: nullable columns
# only, added if missing, never dropped or altered further.
_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "matches": [
        ("previous_date", "DATE"),
        ("previous_kickoff", "VARCHAR"),
    ],
}


def _run_migrations(bind) -> None:
    inspector = inspect(bind)
    if not inspector.has_table("matches"):
        return  # a fresh DB - create_all() above already created it with every column
    with bind.begin() as conn:
        for table, columns in _MIGRATIONS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, sql_type in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def init_db(bind=None) -> None:
    target = bind or engine
    Base.metadata.create_all(target)
    _run_migrations(target)


def get_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
