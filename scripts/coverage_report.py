"""E.12: for each of the next 90 days, how many matches we have by league/competition, and
where the gaps are (an empty date shows as empty, not silently skipped). Also confirms,
with real numbers: Nations League coverage (before/after C.10's MD5-6 addition - see that
commit message for the actual before/after counts, 25589 -> 25641), what date range
football-data.org's free tier actually returns for Champions League, and the real date
range of each domestic league's openfootball-sourced current season.

Usage: python scripts/coverage_report.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kickcast_api.db import SessionLocal
from kickcast_api.models import League, Match

COVERAGE_DAYS = 90


def per_day_table(session) -> None:
    today = datetime.now(UTC).date()
    horizon = today + timedelta(days=COVERAGE_DAYS)
    rows = (
        session.query(Match.date, Match.league_code)
        .filter(Match.date >= today, Match.date <= horizon, Match.status == "scheduled")
        .all()
    )
    leagues = [row[0] for row in session.query(League.code).order_by(League.code)]
    by_date: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(leagues, 0))
    for d, league_code in rows:
        by_date[d.isoformat()][league_code] = by_date[d.isoformat()].get(league_code, 0) + 1

    col_w = max(8, max(len(lc) for lc in leagues) + 2)
    header = f"{'date':<12}" + "".join(f"{lc:>{col_w}}" for lc in leagues) + f"{'total':>{col_w}}"
    print(header)
    print("-" * len(header))
    empty_days = 0
    d = today
    while d <= horizon:
        iso = d.isoformat()
        counts = by_date.get(iso, dict.fromkeys(leagues, 0))
        total = sum(counts.values())
        if total == 0:
            empty_days += 1
        line = f"{iso:<12}" + "".join(f"{counts.get(lc, 0):>{col_w}}" for lc in leagues) + f"{total:>{col_w}}"
        print(line)
        d += timedelta(days=1)
    print(f"\n{empty_days} of {COVERAGE_DAYS + 1} days have zero scheduled matches (any league).")


def summary(session) -> None:
    print("\n=== Nations League ('international') coverage ===")
    total = session.query(Match).filter(Match.league_code == "international").count()
    scheduled = (
        session.query(Match).filter(Match.league_code == "international", Match.status == "scheduled").count()
    )
    dates = session.query(Match.date).filter(
        Match.league_code == "international", Match.status == "scheduled"
    ).order_by(Match.date).all()
    print(f"Total international rows: {total} ({scheduled} scheduled)")
    if dates:
        print(f"Scheduled date range: {dates[0][0]} .. {dates[-1][0]}")

    print("\n=== Champions League (football-data.org free tier) date range ===")
    cl_dates = session.query(Match.date).filter(Match.league_code == "CL").order_by(Match.date).all()
    if cl_dates:
        print(f"CL rows: {len(cl_dates)}, date range: {cl_dates[0][0]} .. {cl_dates[-1][0]}")
    else:
        print("No CL rows (FOOTBALL_DATA_ORG_API_KEY not set, or not yet ingested).")

    print("\n=== Domestic leagues (openfootball current-season schedule) ===")
    for code in ("en.1", "es.1", "it.1", "de.1", "fr.1"):
        rows = session.query(Match.date, Match.season).filter(Match.league_code == code).order_by(Match.date.desc()).limit(1).all()
        first = session.query(Match.date).filter(Match.league_code == code, Match.season == rows[0][1]).order_by(Match.date).first() if rows else None
        if rows and first:
            print(f"{code}: current season {rows[0][1]}, {first[0]} .. {rows[0][0]}")


def main() -> None:
    session = SessionLocal()
    per_day_table(session)
    summary(session)


if __name__ == "__main__":
    main()
