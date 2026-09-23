"""Historical Replay: real StatsBomb Open Data events for a small curated set of real
2015/16 Premier League matches (see scripts/build_statsbomb_replays.py), served from the
committed data/statsbomb_replays.json - keyless, works today. Clearly labeled as a
replay, never presented as live.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/replay", tags=["replay"])

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "statsbomb_replays.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    if not DATA_PATH.exists():
        return {"source": None, "matches": []}
    return json.loads(DATA_PATH.read_text())


@router.get("/matches")
def list_replay_matches() -> dict:
    data = _load()
    return {
        "source": data.get("source"),
        "matches": [
            {k: m[k] for k in ("id", "competition", "season", "date", "home", "away", "home_goals", "away_goals")}
            for m in data.get("matches", [])
        ],
    }


@router.get("/matches/{replay_id}")
def get_replay_match(replay_id: str) -> dict:
    data = _load()
    for m in data.get("matches", []):
        if m["id"] == replay_id:
            return m
    raise HTTPException(404, f"unknown replay match {replay_id!r}")
