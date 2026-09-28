"""Live current-season Golden Boot scorer data from football-data.org's free-tier
GET /competitions/{code}/scorers endpoint - real per-player goals-so-far for the
CURRENT season, unlike kickcast_api.domestic_scorers (a static 2024-25 snapshot from
API-Football, because that tier can't see the live season at all).

VERIFIED with one real call per competition (2026-09-28, key present): all 6 (5
domestic + CL) returned 200 with real 2026-27 in-progress data, e.g. PL: Haaland
5 goals/5 played, matchday 6. A historical `?season=2015` request against the SAME
endpoint returned a real 403 Forbidden ("restricted... check your subscription") - this
plan's /scorers endpoint has NO past-season access at all, confirmed live, not assumed.
Past seasons must come from a different source (kickcast_api.domestic_scorers, when the
exact season matches) or be reported as unavailable - see golden_boot_projection.py and
awards.py for how the two are combined.

Cached to disk (TTL below): this is a live source that shifts as the season
progresses, but a top scorer's tally doesn't meaningfully change minute to minute, and
re-fetching on every page view would burn the free tier's 10 req/min budget for nothing.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from kickcast_engine.data.team_aliases import canonical

from . import football_data_org

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "football_data_scorer_cache"
CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours - see module docstring

FD_CODES: dict[str, str] = {
    "en.1": "PL", "es.1": "PD", "it.1": "SA", "de.1": "BL1", "fr.1": "FL1", "CL": "CL",
}


def _cache_path(league_code: str) -> Path:
    return CACHE_DIR / f"{league_code.replace('.', '_')}.json"


def fetch_scorers(league_code: str, limit: int = 15, network: bool = True) -> dict | None:
    """Returns {"season_label": str, "scorers": [{player, team_id, team_name, goals,
    played_matches}]}, or None if unavailable (no key, this competition isn't on the
    free tier, throttled, or errored) - callers must show an honest "not available"
    state, never fabricate a response."""
    fd_code = FD_CODES.get(league_code)
    if fd_code is None:
        return None

    path = _cache_path(league_code)
    if path.exists():
        cached = json.loads(path.read_text())
        if not network or time.time() - cached["fetched_at"] < CACHE_TTL_SECONDS:
            return cached["data"]

    if not network or not football_data_org.available():
        return None
    payload = football_data_org.get(f"/competitions/{fd_code}/scorers", params={"limit": limit})
    if payload is None or "scorers" not in payload:
        return None

    season = payload.get("season", {})
    start, end = season.get("startDate", "")[:4], season.get("endDate", "")[:4]
    season_label = f"{start}-{end[2:]}" if start and end else "unknown"
    scorers = [
        {
            "player": s["player"]["name"],
            "team_id": canonical(s["team"]["name"]),
            "team_name": s["team"]["name"],
            "goals": s.get("goals") or 0,
            "played_matches": s.get("playedMatches") or 0,
        }
        for s in payload["scorers"]
    ]
    data = {"season_label": season_label, "scorers": scorers}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": time.time(), "data": data}))
    return data
