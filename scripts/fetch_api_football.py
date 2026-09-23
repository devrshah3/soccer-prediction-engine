"""Fetch and cache a handful of API-Football v3 responses (free tier: 100 requests/day,
shared with kickcast_api.live's polling - this script and the live poller both draw
from the same ExternalApiQuota row, see kickcast_api/live/quota.py) needed for:
  - the API-Football <-> KickCast team ID crosswalk (kickcast_engine/data/api_football_crosswalk.py)
  - domestic-league scorer data (kickcast_api/domestic_scorers.py) for goalscorer
    probabilities / historical Golden Boot

VERIFIED against real calls (2026-09-23): the free plan does NOT have access to the
current (2026) season - GET /teams?league=39&season=2026 returns 0 results with
errors.plan: "Free plans do not have access to this season, try from 2022 to 2024."
Real /leagues confirmed the big-5 IDs (England Premier League=39, Spain La Liga=140,
Italy Serie A=135, Germany Bundesliga=78, France Ligue 1=61 - there are many
same-named lower leagues elsewhere, e.g. Brazil also has a "Serie A"; filtered by
country). SEASON = 2024 below is the most recent season this free plan can see.

Idempotent like fetch_footballdata_uk.py: skips a file that's already on disk and
recorded 200 in the manifest, so re-running this doesn't burn quota again.

Usage: python scripts/fetch_api_football.py [data/api_football_cache]
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://v3.football.api-sports.io"
SEASON = 2024  # most recent season the free plan can see (see module docstring)
BIG5 = {
    "premier_league": 39, "la_liga": 140, "serie_a": 135, "bundesliga": 78, "ligue_1": 61,
}


def fetch(path: str) -> tuple[int, bytes]:
    api_key = os.environ.get("API_FOOTBALL_KEY")
    if not api_key:
        return 0, b""
    req = Request(f"{BASE}{path}", headers={"x-apisports-key": api_key})
    try:
        with urlopen(req, timeout=20) as resp:  # fixed https host built from a constant, not user input
            return resp.status, resp.read()
    except HTTPError as e:
        return e.code, b""
    except URLError:
        return 0, b""


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/api_football_cache")
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest: dict[str, dict] = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    jobs = [("leagues", "/leagues")]
    for name, league_id in BIG5.items():
        jobs.append((f"teams_{name}", f"/teams?league={league_id}&season={SEASON}"))
        jobs.append((f"topscorers_{name}", f"/players/topscorers?league={league_id}&season={SEASON}"))

    fetched, skipped, failed = 0, 0, 0
    for key, path in jobs:
        dest = out_dir / f"{key}.json"
        if dest.exists() and manifest.get(key, {}).get("status") == 200:
            skipped += 1
            continue
        status, body = fetch(path)
        if status == 200 and body:
            dest.write_bytes(body)
            manifest[key] = {
                "url": f"{BASE}{path}", "path": str(dest), "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "bytes": len(body), "status": status,
            }
            fetched += 1
            print(f"fetched {key} ({len(body)} bytes)")
        else:
            manifest[key] = {
                "url": f"{BASE}{path}", "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "bytes": 0, "status": status,
            }
            failed += 1
            print(f"FAILED {key} (status={status})")
        manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
        time.sleep(0.3)

    print(f"\nfetched={fetched} skipped(cached)={skipped} failed={failed}")
    print(f"manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
