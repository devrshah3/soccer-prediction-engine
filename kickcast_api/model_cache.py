"""Shared cache-key plumbing for kickcast_api.predictions and kickcast_api.cards: both
cache a fitted model per (db, competition), refit only when scripts/ingest.py bumps
meta.data_version.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Meta


def data_version(session: Session) -> str:
    row = session.get(Meta, "data_version")
    return row.value if row else "0"


def cache_key(session: Session, namespace: str, league_code: str) -> tuple[str, str, str]:
    # `.engine` is defined on both Engine and Connection (Engine.engine returns itself),
    # so this works regardless of which one session.get_bind() hands back. Including the
    # DB URL means two different databases never share a cached model over a reused
    # (namespace, league_code) pair.
    return (str(session.get_bind().engine.url), namespace, league_code)
