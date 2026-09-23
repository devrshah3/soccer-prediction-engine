"""KickCast FastAPI app. Run locally with:

    uvicorn kickcast_api.main:app --reload --port 8000

Expects data/kickcast.db to exist (run `python scripts/ingest.py` first).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .live import scheduler as live_scheduler
from .routes import assistant, awards, leagues, live, matches, replay, teams


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    live_scheduler.start()  # no-op unless API_FOOTBALL_KEY is set
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


@app.get("/")
def root() -> dict:
    return {"name": "KickCast API", "docs": "/docs"}
