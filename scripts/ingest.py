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

from kickcast_api import football_data_org
from kickcast_api.db import SessionLocal, engine, init_db
from kickcast_api.models import Goalscorer, League, Match, MatchStats, Meta, Team
from kickcast_api.precompute import PRECOMPUTE_WINDOW_DAYS, precompute_predictions
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


def upsert_match(session, existing: dict, by_round: dict, key: tuple, fields: dict) -> Match:
    """C.9: `key` is (league_code, date, home_team_id, away_team_id) - if a source now
    reports a different date/kickoff for what's otherwise the same fixture, that key
    itself changes, so the usual `existing.get(key)` lookup misses and would otherwise
    silently insert a duplicate row rather than updating the real one in place.

    Falls back to a second lookup by (league_code, season, round, home_team_id,
    away_team_id) - round-based ("Matchday N", a Nations League group's matchday, a cup
    round) - and only when that fallback actually finds the SAME opponents already on
    record under a different date does it treat this as a moved fixture: update in place,
    and record the previous date/kickoff rather than discarding them. A competition
    without a meaningful `round` value (or a real schedule swap between two OTHER teams
    that happens to reuse a round label) won't be caught by this and is treated as a new
    fixture instead - a real, honest limitation, not silently guessed around.
    """
    m = existing.get(key)
    round_key = (key[0], fields.get("season"), fields.get("round"), key[2], key[3]) if fields.get("round") else None
    if m is None and round_key is not None:
        candidate = by_round.get(round_key)
        if candidate is not None and (candidate.date != key[1] or candidate.kickoff != fields.get("kickoff")):
            candidate.previous_date = candidate.date
            candidate.previous_kickoff = candidate.kickoff
            candidate.date = key[1]
            m = candidate
            existing[key] = m
    if m is None:
        m = Match(league_code=key[0], date=key[1], home_team_id=key[2], away_team_id=key[3])
        session.add(m)
        existing[key] = m
    for k, v in fields.items():
        setattr(m, k, v)
    if round_key is not None:
        by_round[round_key] = m
    if m.status == "scheduled" and m.date < datetime.now(timezone.utc).date():
        # A source can report "no final score yet" for a match whose date has already
        # passed (a postponed/abandoned fixture the source never updated, or a data gap
        # in an old season) - that's not a real upcoming fixture, and every "next match"/
        # "upcoming" query treating it as one was a real, reported bug (stale 2020-2025
        # rows surfacing as "upcoming" on team/league/homepage - see A2 in MORNING_REPORT.md
        # and scripts/mark_stale_fixtures_not_played.py, which cleaned up existing rows;
        # this stops new ones from being created the same way on a future ingest).
        m.status = "not_played"
    return m


def upsert_stats(session, match: Match, stats: dict) -> None:
    row = session.get(MatchStats, match.id) if match.id else None
    if row is None:
        row = MatchStats(match_id=match.id, source=footballdata_uk.SOURCE)
        session.add(row)
    for k, v in stats.items():
        setattr(row, k, v)


def load_existing_matches(session, league_code: str) -> tuple[dict, dict]:
    rows = session.query(Match).filter(Match.league_code == league_code).all()
    primary = {(m.league_code, m.date, m.home_team_id, m.away_team_id): m for m in rows}
    by_round = {
        (m.league_code, m.season, m.round, m.home_team_id, m.away_team_id): m for m in rows if m.round
    }
    return primary, by_round


def ingest_domestic(session, kc_code: str, fd_code: str, name: str, country: str) -> int:
    upsert_league(session, kc_code, name, country, "domestic_league")
    existing, by_round = load_existing_matches(session, kc_code)
    team_cache: dict = {}
    n = 0

    # football-data.co.uk first (2005-06+): establishes base rows + stats/odds, and team
    # display names as a fallback for teams openfootball's window never reaches.
    for fd_row in footballdata_uk.load_all_seasons(FOOTBALLDATA_DIR, fd_code):
        upsert_team(session, fd_row["home"], fd_row["home_raw"], country, team_cache)
        upsert_team(session, fd_row["away"], fd_row["away_raw"], country, team_cache)
        key = (kc_code, date.fromisoformat(fd_row["date"]), fd_row["home"], fd_row["away"])
        m = upsert_match(
            session, existing, by_round, key,
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
            session, existing, by_round, key,
            {
                "season": of_row["season"], "kickoff": kickoff_utc,
                "home_goals": of_row["home_goals"], "away_goals": of_row["away_goals"],
                "status": of_row["status"], "round": of_row.get("round"), "neutral": False,
                "source": openfootball.SOURCE, "source_id": f"{kc_code}:{of_row['date']}",
            },
        )
        n += 1
    return n


def _domestic_team_ids(session) -> set[str]:
    """Club team IDs already claimed by a domestic league. results.csv includes real
    sub-national representative sides (e.g. a 2013 friendly, Madrid 1-2 Andalusia -
    Spanish regions occasionally play these) whose slugged name can coincide with a
    club's canonical id (slug("Madrid") == canonical("Real Madrid") == "madrid", since
    canonical() strips the "Real " prefix) - without this check, ingesting that
    friendly AFTER the domestic leagues silently overwrites Real Madrid's Team row
    with the regional side's name. Call after ingest_domestic has run for the season,
    before ingest_international, so this reflects real current claims."""
    rows = session.query(Match.home_team_id, Match.away_team_id).filter(Match.league_code != "international").all()
    ids: set[str] = set()
    for h, a in rows:
        ids.add(h)
        ids.add(a)
    return ids


def _intl_team_id(raw_id: str, domestic_ids: set[str]) -> str:
    return f"{raw_id}-intl" if raw_id in domestic_ids else raw_id


def ingest_international(session) -> int:
    upsert_league(session, "international", "International", None, "international")
    existing, by_round = load_existing_matches(session, "international")
    team_cache: dict = {}
    domestic_ids = _domestic_team_ids(session)
    n = 0

    tourn = international.tournaments(RESULTS_CSV)
    for m in international.load_results(RESULTS_CSV, INTERNATIONAL_SINCE, friendly_weight=0.5):
        home_id = _intl_team_id(slug(international.canonical(m.home)), domestic_ids)
        away_id = _intl_team_id(slug(international.canonical(m.away)), domestic_ids)
        upsert_team(session, home_id, international.canonical(m.home), None, team_cache)
        upsert_team(session, away_id, international.canonical(m.away), None, team_cache)
        key = ("international", m.date, home_id, away_id)
        upsert_match(
            session, existing, by_round, key,
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
            home_id = _intl_team_id(slug(international.canonical(fx["home"])), domestic_ids)
            away_id = _intl_team_id(slug(international.canonical(fx["away"])), domestic_ids)
            upsert_team(session, home_id, international.canonical(fx["home"]), None, team_cache)
            upsert_team(session, away_id, international.canonical(fx["away"]), None, team_cache)
            key = ("international", d, home_id, away_id)
            local_kickoff = fx.get("kickoff_cet")
            kickoff_utc = (
                to_utc_hhmm(d, local_kickoff, LEAGUE_TIMEZONES["international"]) if local_kickoff else None
            )
            upsert_match(
                session, existing, by_round, key,
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


def ingest_champions_league(session) -> int:
    """UEFA Champions League fixtures/results from football-data.org (free tier, 10
    req/min - see kickcast_api/football_data_org.py's real header-driven throttle).
    Key-gated: a no-op (returns 0) when FOOTBALL_DATA_ORG_API_KEY isn't set, exactly
    like the rest of this project's optional data sources.

    Fetched LIVE on every ingest run, not cached to a static file like
    footballdata_uk/api_football - CL results change match to match (TIMED -> FINISHED)
    and football-data.org's 10/min budget easily covers one call per ingest run.
    utcDate is already real UTC (unlike openfootball's local-time convention) - no
    timezone conversion needed here.

    Team ids use the SAME team_aliases.canonical() as the domestic leagues (best-effort,
    not a separately verified crosswalk like API-Football's - in scope here is "ship
    real fixtures/results", not a second verified crosswalk); many CL clubs already
    exist as real Team rows from their domestic league ingestion and will match
    automatically, non-big-5 clubs (e.g. Club Brugge) get a new Team row.

    No prediction model is fit for "CL" (see kickcast_api/predictions.py's explicit
    guard) - a cross-league team-strength rating is a separate, unvalidated research
    task, not something to ship quickly and unvalidated per the project's backtesting
    rule. Real fixtures/results/standings only, honestly, no fake odds.
    """
    if not football_data_org.available():
        return 0
    payload = football_data_org.get("/competitions/CL/matches")
    if payload is None:
        return 0

    upsert_league(session, "CL", "UEFA Champions League", "Europe", "continental_cup")
    existing, by_round = load_existing_matches(session, "CL")
    team_cache: dict = {}
    n = 0
    season_start_year = int(payload["matches"][0]["season"]["startDate"][:4]) if payload["matches"] else None
    season_label = f"{season_start_year}-{str(season_start_year + 1)[2:]}" if season_start_year else "unknown"

    for fx in payload["matches"]:
        home_id = canonical(fx["homeTeam"]["name"])
        away_id = canonical(fx["awayTeam"]["name"])
        # Only CREATE a team row if one doesn't already exist - most big-5 clubs already
        # have a correct name/country from domestic ingestion, and football-data.org's
        # match payload has no usable per-team country field (only the competition's
        # "area", which is "Europe" for every CL match) - upsert_team would otherwise
        # blindly overwrite a real country with None (the exact class of bug fixed
        # earlier for the "Real Madrid" vs regional-side id collision).
        if session.get(Team, home_id) is None:
            upsert_team(session, home_id, fx["homeTeam"]["name"], None, team_cache)
        if session.get(Team, away_id) is None:
            upsert_team(session, away_id, fx["awayTeam"]["name"], None, team_cache)
        match_date = datetime.fromisoformat(fx["utcDate"].replace("Z", "+00:00")).date()
        kickoff_utc = datetime.fromisoformat(fx["utcDate"].replace("Z", "+00:00")).strftime("%H:%M")
        key = ("CL", match_date, home_id, away_id)
        finished = fx["status"] == "FINISHED"
        full_time = fx.get("score", {}).get("fullTime", {}) if finished else {}
        round_label = f"{fx['stage']} MD{fx['matchday']}" if fx.get("matchday") else fx["stage"]
        upsert_match(
            session, existing, by_round, key,
            {
                "season": season_label, "kickoff": kickoff_utc,
                "home_goals": full_time.get("home"), "away_goals": full_time.get("away"),
                "status": "finished" if finished else "scheduled",
                "round": round_label, "neutral": False,
                "source": "football-data.org", "source_id": f"CL:{fx['id']}",
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
    # Domestic club ids as they stand AFTER ingest_international has run (which already
    # disambiguated any collision) - recomputed here (not passed in) so this function
    # stays correct even if called standalone; see _domestic_team_ids's docstring for why
    # this disambiguation exists (a real martj42 regional-side/club name collision).
    domestic_ids = {
        tid for row in session.query(Match.home_team_id, Match.away_team_id)
        .filter(Match.league_code != "international") for tid in row
    }
    n = 0
    with open(GOALSCORERS_CSV, newline="", encoding="utf-8") as fh:
        import csv

        for r in csv.DictReader(fh):
            d = date.fromisoformat(r["date"])
            if d < INTERNATIONAL_SINCE:
                continue
            home_id = _intl_team_id(slug(international.canonical(r["home_team"])), domestic_ids)
            away_id = _intl_team_id(slug(international.canonical(r["away_team"])), domestic_ids)
            team_id = _intl_team_id(slug(international.canonical(r["team"])), domestic_ids)
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
        counts["CL"] = ingest_champions_league(session)  # no-op (0) without FOOTBALL_DATA_ORG_API_KEY
        session.commit()
        if counts["CL"]:
            print(f"{'CL':8} {'Champions League':16} {counts['CL']:6} match rows upserted")
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

        # B.8: precompute predictions for every scheduled match in the next 90 days right
        # after ingest, rather than waiting for the first request (or the nightly
        # schedule) to compute them - keeps GET /matches?date=... a fast DB read.
        precomputed = precompute_predictions(session)
        print(f"precompute: {precomputed} prediction(s) stored for the next {PRECOMPUTE_WINDOW_DAYS} days")
    finally:
        session.close()
    engine.dispose()


if __name__ == "__main__":
    main()
