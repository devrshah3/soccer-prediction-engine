"""KickCast FastAPI app. Run locally with:

    uvicorn kickcast_api.main:app --reload --port 8000

Expects data/kickcast.db to exist (run `python scripts/ingest.py` first).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import get_session
from .live import scheduler as live_scheduler
from .models import Meta
from .routes import assistant, awards, batch, leagues, live, matches, replay, teams


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    live_scheduler.start()  # nightly precompute always runs; API-Football jobs only if a key is set
    yield
    live_scheduler.stop()


app = FastAPI(title="KickCast API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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


@app.get("/")
def root() -> dict:
    return {"name": "KickCast API", "docs": "/docs"}


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
