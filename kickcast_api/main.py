"""Soccer Prediction Engine FastAPI app. Run locally with:

    uvicorn kickcast_api.main:app --reload --port 8000

Expects data/kickcast.db to exist (run `python scripts/ingest.py` first).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import catchup, settings
from .db import get_session
from .live import scheduler as live_scheduler
from .models import Meta
from .routes import assistant, awards, batch, leagues, live, matches, replay, teams


def _load_seed() -> None:
    from .db import SessionLocal
    from .seed import load_seed

    session = SessionLocal()
    try:
        load_seed(session)
    except Exception:  # a bad/missing seed must never stop the API from starting
        logging.getLogger("uvicorn.error").exception("seed load failed; continuing without it")
    finally:
        session.close()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _load_seed()  # before any refresh, so live data lands on top of it
    live_scheduler.start()  # nightly build always; API-Football jobs only if enabled AND a key is set
    if settings.startup_catchup():
        catchup.start_background()  # serve immediately from the built DB; catch up in the background
    yield
    live_scheduler.stop()


app = FastAPI(
    title="Soccer Prediction Engine API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs() else None,
    redoc_url="/redoc" if settings.enable_docs() else None,
    openapi_url="/openapi.json" if settings.enable_docs() else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(leagues.router)
app.include_router(teams.router)
app.include_router(matches.router)
app.include_router(assistant.router)
app.include_router(awards.router)
app.include_router(live.router)
app.include_router(replay.router)
app.include_router(batch.router)


@app.get("/health")
def health() -> dict:
    """For uptime pingers and the host's health check: no database, no provider, no work at all."""
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {"name": "Soccer Prediction Engine API", "docs": "/docs"}


@app.get("/meta")
def meta(session: Session = Depends(get_session)) -> dict:
    """C.9: when the data was last refreshed - the frontend footer's "fixtures updated
    X ago" reads this rather than guessing."""
    ingested_at = session.get(Meta, "ingested_at")
    data_version = session.get(Meta, "data_version")
    return {
        "ingested_at": ingested_at.value if ingested_at else None,
        "data_version": data_version.value if data_version else None,
    }
