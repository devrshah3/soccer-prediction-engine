"""Write seed/seed.json.gz from the local database - run this BEFORE pushing (see DEPLOY.md).

    python scripts/export_seed.py [--since 2026-08-01]

Exports only open-licensed result / goal-event / match-stat rows for matches finished since
`--since` (default: the start of the current season window). Rows that came from ESPN or
API-Football are never exported - see kickcast_api/seed.py. Fails if the file would exceed 5 MB.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kickcast_api.db import SessionLocal
from kickcast_api.seed import SEED_PATH, export_snapshot, write_snapshot

MAX_BYTES = 5 * 1024 * 1024


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-01", type=date.fromisoformat)
    args = ap.parse_args()
    session = SessionLocal()
    try:
        snap = export_snapshot(session, args.since)
    finally:
        session.close()
    size = write_snapshot(snap)
    print(f"wrote {SEED_PATH} ({size:,} bytes): {len(snap['results'])} results, "
          f"{len(snap['goals'])} goal events, {len(snap['stats'])} match-stat rows, since {args.since}")
    if size > MAX_BYTES:
        print(f"ERROR: {size:,} bytes exceeds the {MAX_BYTES:,}-byte cap - raise --since", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
