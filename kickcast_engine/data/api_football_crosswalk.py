"""API-Football numeric team ID <-> KickCast canonical team ID (team_aliases.py),
built from REAL /teams responses (data/api_football_cache/teams_*.json, fetched by
scripts/fetch_api_football.py), not guessed.

VERIFIED (2026-09-23): running team_aliases.canonical_id() on every API-Football team
name across the big-5 leagues (98 teams) auto-resolved 96/98 against our own Team
table. The 2 gaps are real API-Football naming quirks not covered by the OTHER
sources' OVERRIDES in team_aliases.py (that dict is scoped to openfootball/
football-data.co.uk spellings):
  - "Celta Vigo" (API-Football drops the "de Vigo") vs our "celta" (from
    football-data.co.uk's short name "Celta")
  - "FSV Mainz 05" (API-Football drops the leading "1.") vs our "mainz" -
    team_aliases.py's prefix list only strips "1 fsv " (with the "1"), not "fsv "
    alone, so "FSV Mainz 05" fell through as "fsv mainz"
Both confirmed by cross-referencing the real cached responses against the real Team
table populated by scripts/ingest.py, not assumed.
"""

from __future__ import annotations

import json
from pathlib import Path

from .team_aliases import canonical

# API-Football's raw team name -> our canonical id, ONLY for names team_aliases.canonical()
# alone can't resolve (see module docstring for how these 2 were found). canonical() (not
# the bare canonical_id() normalizer) is the base here because it already carries the
# openfootball/football-data.co.uk short-name overrides - many of API-Football's own names
# turned out to need those same overrides too (e.g. its "Nott'm Forest" resolves via the
# existing "Nottm Forest"-style entries), so building on canonical_id() alone measured only
# 84/98 auto-resolved; canonical() got 96/98, confirmed with a real cross-check against the
# Team table scripts/ingest.py actually populated.
API_FOOTBALL_OVERRIDES: dict[str, str] = {
    "Celta Vigo": "celta",
    "FSV Mainz 05": "mainz",
}

BIG5_LEAGUE_IDS: dict[str, int] = {
    "en.1": 39, "es.1": 140, "it.1": 135, "de.1": 78, "fr.1": 61,
}


def crosswalk_id(api_football_name: str) -> str:
    return API_FOOTBALL_OVERRIDES.get(api_football_name) or canonical(api_football_name)


def load_team_crosswalk(cache_dir: Path) -> dict[int, str]:
    """API-Football numeric team id -> kickcast canonical team id, for every team seen
    across the cached big-5 /teams responses."""
    out: dict[int, str] = {}
    for f in sorted(cache_dir.glob("teams_*.json")):
        data = json.loads(f.read_text())
        for item in data.get("response", []):
            t = item["team"]
            out[t["id"]] = crosswalk_id(t["name"])
    return out
