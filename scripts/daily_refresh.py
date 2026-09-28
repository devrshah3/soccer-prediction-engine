"""C.9: one-command daily refresh - re-pulls openfootball + martj42, re-ingests
(idempotent - see scripts/ingest.py), recomputes predictions, and logs what changed (new
fixtures, moved dates, new results) by comparing a snapshot of every match before and
after. football-data.org (Champions League) is refreshed as part of the same ingest run;
its client (kickcast_api/football_data_org.py) already enforces the real 10 calls/minute
limit, so no separate throttling is needed here.

Run manually, or schedule via cron - see README.md's "Keeping data fresh" section for a
real crontab line. This is the one command that section documents.

Usage: python scripts/daily_refresh.py
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kickcast_api.db import SessionLocal
from kickcast_api.models import Match

REPO_ROOT = Path(__file__).resolve().parents[1]


def _snapshot(session) -> dict[int, tuple]:
    return {m.id: (m.date, m.kickoff, m.status, m.home_goals, m.away_goals) for m in session.query(Match).all()}


def main() -> None:
    session = SessionLocal()
    before = _snapshot(session)
    session.close()

    started = datetime.now(UTC).isoformat()
    print(f"=== daily refresh started {started} ===")
    subprocess.run(["bash", str(REPO_ROOT / "scripts" / "fetch_open_data.sh"), "--force"], check=True, cwd=REPO_ROOT)
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "fetch_footballdata_uk.py")], check=True, cwd=REPO_ROOT)
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "ingest.py")], check=True, cwd=REPO_ROOT)

    session = SessionLocal()
    after = _snapshot(session)
    session.close()

    new_fixtures = [mid for mid in after if mid not in before]
    moved = [mid for mid in after if mid in before and after[mid][0] != before[mid][0]]
    new_results = [
        mid for mid in after if mid in before and before[mid][2] != "finished" and after[mid][2] == "finished"
    ]
    print(
        f"changed: {len(new_fixtures)} new fixture(s), {len(moved)} moved date(s), "
        f"{len(new_results)} new result(s)"
    )
    print(f"=== daily refresh finished {datetime.now(UTC).isoformat()} ===")


if __name__ == "__main__":
    main()
