"""One-time data cleanup (A3): merge the "atletico" team id into "atletico madrid".

Found while verifying standings against real-world data: canonical_id()'s generic
" de madrid" suffix strip turned openfootball's "Club Atlético de Madrid" into "atletico"
instead of "atletico madrid" (the id football-data.co.uk's "Ath Madrid" already correctly
maps to via OVERRIDES) - see kickcast_engine/data/team_aliases.py, now fixed for future
ingests. This script cleans up the rows that were already split across both ids before
that fix existed:

  - Most of "atletico"'s 274 match rows are exact duplicates of a row that already exists
    under "atletico madrid" (same league_code/date/opponent - the same real match,
    ingested twice under two different team-id spellings). Those duplicates are deleted.
  - The remainder (not yet present under "atletico madrid" - mostly the live 2026-27
    season and Champions League matches) are renamed onto "atletico madrid" in place.
  - The now-unreferenced "atletico" Team row is deleted.
  - Meta.data_version is bumped so cached prediction models refit against the merged,
    now-complete history.

Safe to re-run: reports and does nothing once "atletico" has no more rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kickcast_api.db import SessionLocal
from kickcast_api.models import Match, MatchStats, Meta, Team

OLD_ID = "atletico"
NEW_ID = "atletico madrid"


def main() -> None:
    session = SessionLocal()
    old_matches = (
        session.query(Match).filter((Match.home_team_id == OLD_ID) | (Match.away_team_id == OLD_ID)).all()
    )
    if not old_matches:
        print(f"No rows reference {OLD_ID!r}. Nothing to do.")
        return

    deleted_duplicates = 0
    renamed = 0
    for m in old_matches:
        home = NEW_ID if m.home_team_id == OLD_ID else m.home_team_id
        away = NEW_ID if m.away_team_id == OLD_ID else m.away_team_id
        collision = (
            session.query(Match)
            .filter(Match.league_code == m.league_code, Match.date == m.date, Match.home_team_id == home, Match.away_team_id == away)
            .filter(Match.id != m.id)
            .first()
        )
        if collision is not None:
            session.query(MatchStats).filter(MatchStats.match_id == m.id).delete()
            session.delete(m)
            deleted_duplicates += 1
        else:
            m.home_team_id, m.away_team_id = home, away
            renamed += 1
    session.flush()

    remaining = session.query(Match).filter((Match.home_team_id == OLD_ID) | (Match.away_team_id == OLD_ID)).count()
    assert remaining == 0, f"{remaining} rows still reference {OLD_ID!r} after merge - aborting commit"

    old_team = session.get(Team, OLD_ID)
    if old_team is not None:
        session.delete(old_team)

    version_row = session.get(Meta, "data_version")
    next_version = str(int(version_row.value) + 1) if version_row else "1"
    if version_row is None:
        session.add(Meta(key="data_version", value=next_version))
    else:
        version_row.value = next_version

    session.commit()

    print(f"Merged {OLD_ID!r} into {NEW_ID!r}:")
    print(f"  {deleted_duplicates} duplicate row(s) deleted (already existed under {NEW_ID!r})")
    print(f"  {renamed} row(s) renamed onto {NEW_ID!r}")
    print(f"  Team row {OLD_ID!r} removed" if old_team is not None else f"  (no Team row for {OLD_ID!r} existed)")
    print(f"  data_version -> {next_version} - prediction models will refit on next request")


if __name__ == "__main__":
    main()
