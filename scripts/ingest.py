"""Idempotent ingestion: openfootball + football-data.co.uk (domestic leagues),
martj42 international results/goalscorers + the UEFA Nations League fixture list
(international) -> data/kickcast.db.

Safe to re-run: matches are upserted on a natural key (league_code, date, home_team_id,
away_team_id), so running this twice does not duplicate rows. Bumps meta.data_version
so the API knows to refit its cached prediction models.

For the 2010-11+ overlap window, openfootball is the source of truth for score/status
(it's what the live 2026-27 season comes from); football-data.co.uk's match-stat/card/
closing-odds columns are attached to the *same* match row when the two join on
(canonical team id, date). Pre-2010-11 history (back to 2005-06) comes from
football-data.co.uk alone, extending training history for the "full history warm start"
finding in reports/backtest_openfootball.json.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kickcast_api.db import SessionLocal, engine, init_db
from kickcast_api.models import Goalscorer, League, Match, MatchStats, Meta, Team
from kickcast_engine.data import footballdata_uk, international, openfootball
from kickcast_engine.data.kickoff import LEAGUE_TIMEZONES, to_utc_hhmm
from kickcast_engine.data.team_aliases import canonical

REPO_ROOT = Path(__file__).resolve().parents[1]
OPENFOOTBALL_DIR = REPO_ROOT / "data" / "openfootball_raw"
FOOTBALLDATA_DIR = REPO_ROOT / "data" / "footballdata_uk"
RESULTS_CSV = REPO_ROOT / "data" / "results.csv"
GOALSCORERS_CSV = REPO_ROOT / "data" / "goalscorers.csv"
NATIONS_LEAGUE_JSON = REPO_ROOT / "data" / "nations_league_2026_27_md1_4.json"

INTERNATIONAL_SINCE = date(2000, 1, 1)  # DB keeps 2000+ for size/relevance; results.csv has full history to 1872


def slug(name: str) -> str:
    return name.lower().replace("'", "").replace(".", "").replace(" ", "-")


def upsert_league(session, code: str, name: str, country: str | None, kind: str) -> None:
    row = session.get(League, code)
    if row is None:
        session.add(League(code=code, name=name, country=country, kind=kind))
    else:
        row.name, row.country, row.kind = name, country, kind


def upsert_team(session, team_id: str, name: str, country: str | None, cache: dict) -> None:
    if team_id in cache:
        return
    row = session.get(Team, team_id)
    if row is None:
        session.add(Team(id=team_id, name=name, country=country))
    else:
        row.name, row.country = name, country
    cache[team_id] = True


def upsert_match(session, existing: dict, key: tuple, fields: dict) -> Match:
    m = existing.get(key)
    if m is None:
        m = Match(league_code=key[0], date=key[1], home_team_id=key[2], away_team_id=key[3])
        session.add(m)
        existing[key] = m
    for k, v in fields.items():
        setattr(m, k, v)
    return m


def upsert_stats(session, match: Match, stats: dict) -> None:
    row = session.get(MatchStats, match.id) if match.id else None
    if row is None:
        row = MatchStats(match_id=match.id, source=footballdata_uk.SOURCE)
        session.add(row)
    for k, v in stats.items():
        setattr(row, k, v)


def load_existing_matches(session, league_code: str) -> dict:
    return {
        (m.league_code, m.date, m.home_team_id, m.away_team_id): m
        for m in session.query(Match).filter(Match.league_code == league_code)
    }


def ingest_domestic(session, kc_code: str, fd_code: str, name: str, country: str) -> int:
    upsert_league(session, kc_code, name, country, "domestic_league")
    existing = load_existing_matches(session, kc_code)
    team_cache: dict = {}
    n = 0

    # football-data.co.uk first (2005-06+): establishes base rows + stats/odds, and team
    # display names as a fallback for teams openfootball's window never reaches.
    for fd_row in footballdata_uk.load_all_seasons(FOOTBALLDATA_DIR, fd_code):
        upsert_team(session, fd_row["home"], fd_row["home_raw"], country, team_cache)
        upsert_team(session, fd_row["away"], fd_row["away_raw"], country, team_cache)
        key = (kc_code, date.fromisoformat(fd_row["date"]), fd_row["home"], fd_row["away"])
        m = upsert_match(
            session, existing, key,
            {
                "season": fd_row["season"], "kickoff": None,
                "home_goals": fd_row["home_goals"], "away_goals": fd_row["away_goals"],
                "status": fd_row["status"], "round": None, "neutral": False,
                "source": footballdata_uk.SOURCE, "source_id": f"{kc_code}:{fd_row['date']}",
            },
        )
        session.flush()  # need m.id before attaching stats
        stat_fields = {v: fd_row[v] for v in footballdata_uk.STAT_COLUMNS.values() if v in fd_row}
        stat_fields.update({v: fd_row[v] for v in footballdata_uk.CARD_COLUMNS.values() if v in fd_row})
        if "closing_odds" in fd_row:
            co = fd_row["closing_odds"]
            stat_fields.update(
                closing_odds_home=co["home"], closing_odds_draw=co["draw"], closing_odds_away=co["away"],
                odds_source=co["source"],
            )
        if stat_fields:
            upsert_stats(session, m, stat_fields)
        n += 1

    # openfootball second: overwrites score/status/round with its values where the two overlap
    # (it's the live-season source of truth), keeps whatever stats row football-data.co.uk set.
    for of_row in openfootball.load_all_seasons(OPENFOOTBALL_DIR, kc_code):
        home_id, away_id = canonical(of_row["home"]), canonical(of_row["away"])
        upsert_team(session, home_id, of_row["home"], country, team_cache)
        upsert_team(session, away_id, of_row["away"], country, team_cache)
        match_date = date.fromisoformat(of_row["date"])
        key = (kc_code, match_date, home_id, away_id)
        local_kickoff = of_row.get("kickoff")
        kickoff_utc = (
            to_utc_hhmm(match_date, local_kickoff, LEAGUE_TIMEZONES[kc_code]) if local_kickoff else None
        )
        upsert_match(
            session, existing, key,
            {
                "season": of_row["season"], "kickoff": kickoff_utc,
                "home_goals": of_row["home_goals"], "away_goals": of_row["away_goals"],
                "status": of_row["status"], "round": of_row.get("round"), "neutral": False,
                "source": openfootball.SOURCE, "source_id": f"{kc_code}:{of_row['date']}",
            },
        )
        n += 1
    return n


def ingest_international(session) -> int:
    upsert_league(session, "international", "International", None, "international")
    existing = load_existing_matches(session, "international")
    team_cache: dict = {}
    n = 0

    tourn = international.tournaments(RESULTS_CSV)
    for m in international.load_results(RESULTS_CSV, INTERNATIONAL_SINCE, friendly_weight=0.5):
        home_id, away_id = slug(international.canonical(m.home)), slug(international.canonical(m.away))
        upsert_team(session, home_id, international.canonical(m.home), None, team_cache)
        upsert_team(session, away_id, international.canonical(m.away), None, team_cache)
        key = ("international", m.date, home_id, away_id)
        upsert_match(
            session, existing, key,
            {
                "season": str(m.date.year), "kickoff": None,
                "home_goals": m.home_goals, "away_goals": m.away_goals,
                "status": "finished", "round": tourn.get((m.date.isoformat(), m.home, m.away), None),
                "neutral": m.neutral,
                "source": international.SOURCE, "source_id": f"international:{m.date}:{m.home}:{m.away}",
            },
        )
        n += 1

    if NATIONS_LEAGUE_JSON.exists():
        payload = json.loads(NATIONS_LEAGUE_JSON.read_text())
        for fx in payload["fixtures"]:
            d = date.fromisoformat(fx["date"])
            home_id, away_id = slug(international.canonical(fx["home"])), slug(international.canonical(fx["away"]))
            upsert_team(session, home_id, international.canonical(fx["home"]), None, team_cache)
            upsert_team(session, away_id, international.canonical(fx["away"]), None, team_cache)
            key = ("international", d, home_id, away_id)
            local_kickoff = fx.get("kickoff_cet")
            kickoff_utc = (
                to_utc_hhmm(d, local_kickoff, LEAGUE_TIMEZONES["international"]) if local_kickoff else None
            )
            upsert_match(
                session, existing, key,
                {
                    "season": "2026-27", "kickoff": kickoff_utc,
                    "home_goals": None, "away_goals": None,
                    "status": fx["status"], "round": f"{fx['competition']} MD{fx['matchday']} Group {fx['group']}",
                    "neutral": False,
                    "source": payload["source"], "source_id": f"nations-league:{fx['date']}:{fx['home']}:{fx['away']}",
                },
            )
            n += 1
    return n


def ingest_goalscorers(session) -> int:
    session.query(Goalscorer).delete()  # small table, cheap to fully rebuild each run (keeps it simple+idempotent)
    match_index = {
        (m.date, m.home_team_id, m.away_team_id): m.id
        for m in session.query(Match).filter(Match.league_code == "international")
    }
    n = 0
    with open(GOALSCORERS_CSV, newline="", encoding="utf-8") as fh:
        import csv

        for r in csv.DictReader(fh):
            d = date.fromisoformat(r["date"])
            if d < INTERNATIONAL_SINCE:
                continue
            home_id = slug(international.canonical(r["home_team"]))
            away_id = slug(international.canonical(r["away_team"]))
            team_id = slug(international.canonical(r["team"]))
            match_id = match_index.get((d, home_id, away_id))
            session.add(
                Goalscorer(
                    match_id=match_id, date=d, team_id=team_id, scorer_name=r["scorer"] or "unknown",
                    minute=int(r["minute"]) if r.get("minute") not in (None, "", "NA") else None,
                    own_goal=r["own_goal"].upper() == "TRUE", penalty=r["penalty"].upper() == "TRUE",
                    source=international.SOURCE,
                )
            )
            n += 1
    return n


DOMESTIC_LEAGUES = [
    ("en.1", "E0", "Premier League", "England"),
    ("es.1", "SP1", "La Liga", "Spain"),
    ("it.1", "I1", "Serie A", "Italy"),
    ("de.1", "D1", "Bundesliga", "Germany"),
    ("fr.1", "F1", "Ligue 1", "France"),
]


def main() -> None:
    init_db()
    session = SessionLocal()
    counts = {}
    try:
        for kc_code, fd_code, name, country in DOMESTIC_LEAGUES:
            counts[kc_code] = ingest_domestic(session, kc_code, fd_code, name, country)
            session.commit()
            print(f"{kc_code:8} {name:16} {counts[kc_code]:6} match rows upserted")
        counts["international"] = ingest_international(session)
        session.commit()
        print(f"{'intl':8} {'International':16} {counts['international']:6} match rows upserted")
        counts["goalscorers"] = ingest_goalscorers(session)
        session.commit()
        print(f"{'':8} {'Goalscorers':16} {counts['goalscorers']:6} rows")

        version_row = session.get(Meta, "data_version")
        next_version = str(int(version_row.value) + 1) if version_row else "1"
        if version_row is None:
            session.add(Meta(key="data_version", value=next_version))
        else:
            version_row.value = next_version
        ingested_row = session.get(Meta, "ingested_at")
        now = datetime.now(timezone.utc).isoformat()
        if ingested_row is None:
            session.add(Meta(key="ingested_at", value=now))
        else:
            ingested_row.value = now
        session.commit()
        print(f"\ndata_version -> {next_version}, ingested_at -> {now}")
    finally:
        session.close()
    engine.dispose()


if __name__ == "__main__":
    main()
