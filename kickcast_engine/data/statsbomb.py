"""StatsBomb Open Data loader (free, historical only).

Source: https://github.com/statsbomb/open-data  -- attribution required by their licence.
Used for model training, backtests and the Historical Replay. Not a live feed.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import requests

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
SOURCE = "statsbomb_open_data"

# Full-season competitions verified to have complete (~380 match) coverage.
FULL_SEASONS = {
    "Premier League 2015/16": (2, 27),
    "La Liga 2015/16": (11, 27),
    "Serie A 2015/16": (12, 27),
    "Ligue 1 2015/16": (7, 27),
}


def _get_json(path: str, cache_dir: Path) -> object:
    cache_dir.mkdir(parents=True, exist_ok=True)
    local = cache_dir / path.replace("/", "_")
    if local.exists():
        return json.loads(local.read_text())
    r = requests.get(f"{BASE}/{path}", timeout=60)
    r.raise_for_status()
    local.write_text(r.text)
    return r.json()


def load_matches(competition_id: int, season_id: int, cache_dir: Path) -> list[dict]:
    raw = _get_json(f"matches/{competition_id}/{season_id}.json", cache_dir)
    assert isinstance(raw, list)
    out = []
    for m in raw:
        if m.get("match_status") not in (None, "available"):
            continue
        out.append(
            {
                "source": SOURCE,
                "source_id": str(m["match_id"]),
                "competition": m["competition"]["competition_name"],
                "country": m["competition"].get("country_name"),
                "season": m["season"]["season_name"],
                "date": date.fromisoformat(m["match_date"]),
                "kickoff": m.get("kick_off"),
                "home": m["home_team"]["home_team_name"],
                "away": m["away_team"]["away_team_name"],
                "home_goals": int(m["home_score"]),
                "away_goals": int(m["away_score"]),
                "status": "finished",
                "gender": m["home_team"].get("home_team_gender", "male"),
            }
        )
    out.sort(key=lambda r: (r["date"], r["source_id"]))
    return out


def load_events(match_id: str | int, cache_dir: Path) -> list[dict]:
    raw = _get_json(f"events/{match_id}.json", cache_dir)
    assert isinstance(raw, list)
    return raw
