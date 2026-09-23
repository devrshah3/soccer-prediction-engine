"""KickCast FastAPI app. Run locally with:

    uvicorn kickcast_api.main:app --reload --port 8000

Expects data/kickcast.db to exist (run `python scripts/ingest.py` first).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import leagues, matches, teams

app = FastAPI(title="KickCast API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(leagues.router)
app.include_router(teams.router)
app.include_router(matches.router)


@app.get("/")
def root() -> dict:
    return {"name": "KickCast API", "docs": "/docs"}
