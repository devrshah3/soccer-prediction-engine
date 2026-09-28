"""One-time data cleanup (A2): find every Match row with status="scheduled" whose date
has already passed, and relabel it "not_played" so it stops appearing in every "upcoming"
list, team page, and standings/trophy-odds calculation that filters on status.

These rows are a real, reported bug's root cause: a source (openfootball, football-data.
co.uk) can report "no final score yet" for a match whose date is long past - a postponed/
abandoned fixture the source never updated (fr.1 has rows from March 2020, COVID-era), or
simply a data gap in an old season (es.1/it.1's final matchday of 2024-25, dated May 2025).
scripts/ingest.py's upsert_match() now does this relabeling automatically going forward
(see its docstring) - this script is for the rows that already existed before that fix.

Safe to re-run: matches nothing (and reports zero rows) once the DB has no stale
"scheduled" rows left. Does not touch genuinely-finished or genuinely-future rows.

Usage: python scripts/mark_stale_fixtures_not_played.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kickcast_api.db import SessionLocal
from kickcast_api.models import Match


def main() -> None:
    session = SessionLocal()
    today = datetime.now(UTC).date()
    stale = (
        session.query(Match)
        .filter(Match.status == "scheduled", Match.date < today)
        .order_by(Match.league_code, Match.season, Match.date)
        .all()
    )

    if not stale:
        print(f"No stale 'scheduled' rows found (today: {today}). Nothing to do.")
        return

    by_league_season: dict[tuple[str, str], int] = defaultdict(int)
    for m in stale:
        by_league_season[(m.league_code, m.season)] += 1
        m.status = "not_played"
    session.commit()

    print(f"Marked {len(stale)} stale 'scheduled' row(s) as 'not_played' (today: {today}).\n")
    print(f"{'League':<16}{'Season':<10}{'Rows':>6}")
    for (league_code, season), count in sorted(by_league_season.items()):
        print(f"{league_code:<16}{season:<10}{count:>6}")


if __name__ == "__main__":
    main()
