"""Download football-data.co.uk historical CSVs (free, no key) once into a local cache.

No formal license/terms-of-use text was found on football-data.co.uk (checked the
homepage, /notes.txt and /disclaimer.php) restricting download or research/personal
use; it is a long-established free dataset widely used in football-analytics
research, and there is no robots.txt disallow. This script downloads once into
data/footballdata_uk/ and records a manifest so we never re-fetch on every run or
scrape the site live per page load, consistent with the project's data ground rules.

Usage: python scripts/fetch_footballdata_uk.py [data/footballdata_uk]
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://www.football-data.co.uk/mmz4281"
UA = "soccer-prediction-engine-research-bot/0.1 (personal, non-commercial football prediction project)"
# code used by football-data.co.uk -> internal league code used by kickcast_engine.data.openfootball
LEAGUES = {"E0": "en.1", "SP1": "es.1", "I1": "it.1", "D1": "de.1", "F1": "fr.1"}
FIRST_SEASON_START = 2001
LAST_SEASON_START = 2026  # inclusive -> season "2026-27"


def season_label(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[2:]}"


def season_code(start_year: int) -> str:
    return f"{str(start_year)[2:]}{str(start_year + 1)[2:]}"


def fetch(url: str) -> tuple[int, bytes]:
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=30) as resp:  # fixed https host built from a constant, not user input
            return resp.status, resp.read()
    except HTTPError as e:
        return e.code, b""
    except URLError:
        return 0, b""


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/footballdata_uk")
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest: dict[str, dict] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    fetched, skipped, failed = 0, 0, 0
    for start_year in range(FIRST_SEASON_START, LAST_SEASON_START + 1):
        label = season_label(start_year)
        code_suffix = season_code(start_year)
        season_dir = out_dir / label
        season_dir.mkdir(exist_ok=True)
        for fd_code, kc_code in LEAGUES.items():
            key = f"{label}/{fd_code}"
            dest = season_dir / f"{fd_code}.csv"
            if dest.exists() and key in manifest and manifest[key].get("status") == 200:
                skipped += 1
                continue
            url = f"{BASE}/{code_suffix}/{fd_code}.csv"
            status, body = fetch(url)
            if status == 200 and body:
                dest.write_bytes(body)
                manifest[key] = {
                    "url": url,
                    "path": str(dest),
                    "league_code": fd_code,
                    "kickcast_league": kc_code,
                    "season": label,
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "bytes": len(body),
                    "status": status,
                }
                fetched += 1
                print(f"fetched {key} ({len(body)} bytes)")
            else:
                manifest[key] = {
                    "url": url,
                    "league_code": fd_code,
                    "kickcast_league": kc_code,
                    "season": label,
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "bytes": 0,
                    "status": status,
                }
                failed += 1
                print(f"MISSING {key} (status={status}) - likely season not yet played or not offered")
            manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
            time.sleep(0.6)

    print(f"\nfetched={fetched} skipped(cached)={skipped} failed/missing={failed}")
    print(f"manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
