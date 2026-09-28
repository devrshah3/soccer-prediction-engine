"""Seed snapshot: a small compressed file of result / goal-event / match-stat rows, committed to the
repo (seed/seed.json.gz, written by scripts/export_seed.py) and loaded at build time and at startup
BEFORE the live refresh, so a fresh Render disk (which resets to the build snapshot) starts from it.

Scope, on purpose: OPEN-LICENSED provenance only - martj42/international_results (CC0),
openfootball/football.json (CC0) and football-data.co.uk results/stats. Nothing from ESPN or
API-Football (LiveEvent / LiveMatchState rows, or any match those sources touched) is ever exported:
neither has terms permitting redistribution in a public repo. Those are fetched live by the running
server instead (kickcast_api/live/, backfill_from_espn).

Loading never overwrites: a match that is already finished keeps its result, existing goal events
and stats are left alone, and rows for matches the database doesn't have are skipped.
"""

from __future__ import annotations

import gzip
import json
import logging
import sys
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from .models import Goalscorer, LiveEvent, LiveMatchState, Match, MatchStats

log = logging.getLogger("uvicorn.error")

SEED_PATH = Path(__file__).resolve().parents[1] / "seed" / "seed.json.gz"
OPEN_MATCH_SOURCES = ("martj42/international_results", "openfootball/football.json", "football-data.co.uk")
OPEN_GOAL_SOURCES = ("martj42/international_results",)
OPEN_STATS_SOURCES = ("football-data.co.uk",)
STATS_FIELDS = [
    "home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target", "home_corners", "away_corners",
    "home_fouls", "away_fouls", "home_yellow", "away_yellow", "home_red", "away_red",
    "closing_odds_home", "closing_odds_draw", "closing_odds_away", "odds_source", "source",
]


def _key(m: Match) -> list:
    return [m.league_code, m.date.isoformat(), m.home_team_id, m.away_team_id]


def export_snapshot(session: Session, since: date) -> dict:
    touched_by_live = {r[0] for r in session.query(LiveMatchState.match_id)} | {r[0] for r in session.query(LiveEvent.match_id)}
    matches = (
        session.query(Match)
        .filter(Match.date >= since, Match.status == "finished", Match.source.in_(OPEN_MATCH_SOURCES))
        .all()
    )
    matches = [m for m in matches if m.id not in touched_by_live and m.home_goals is not None]
    by_id = {m.id: m for m in matches}
    ids = list(by_id)
    goals = [
        [*_key(by_id[g.match_id]), g.team_id, g.scorer_name, g.minute, g.own_goal, g.penalty, g.source]
        for g in session.query(Goalscorer).filter(Goalscorer.source.in_(OPEN_GOAL_SOURCES)).all()
        if g.match_id in by_id
    ]
    stats = [
        [*_key(by_id[s.match_id]), *[getattr(s, f) for f in STATS_FIELDS]]
        for s in session.query(MatchStats).filter(MatchStats.source.in_(OPEN_STATS_SOURCES)).all()
        if s.match_id in by_id
    ]
    return {
        "format": 1,
        "since": since.isoformat(),
        "licences": "martj42/international_results CC0; openfootball/football.json CC0; football-data.co.uk results/stats",
        "stats_fields": STATS_FIELDS,
        "results": [[*_key(m), m.home_goals, m.away_goals, m.source] for m in matches],
        "goals": goals,
        "stats": stats,
        "_ids": len(ids),
    }


def write_snapshot(snapshot: dict, path: Path = SEED_PATH) -> int:
    snapshot = {k: v for k, v in snapshot.items() if k != "_ids"}
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump(snapshot, fh, separators=(",", ":"), sort_keys=True)
    return path.stat().st_size


def load_seed(session: Session, path: Path = SEED_PATH) -> dict:
    report = {"results": 0, "goals": 0, "stats": 0}
    if not path.exists():
        return report
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    matches = {
        (m.league_code, m.date.isoformat(), m.home_team_id, m.away_team_id): m
        for m in session.query(Match).filter(Match.date >= date.fromisoformat(data["since"]))
    }
    for lc, d, h, a, hg, ag, src in data["results"]:
        m = matches.get((lc, d, h, a))
        if m is not None and m.status != "finished":  # never overwrite a real result
            m.status, m.home_goals, m.away_goals = "finished", hg, ag
            report["results"] += 1
    have_goals = {r[0] for r in session.query(Goalscorer.match_id).filter(Goalscorer.match_id.isnot(None))}
    for lc, d, h, a, team, scorer, minute, og, pen, src in data["goals"]:
        m = matches.get((lc, d, h, a))
        if m is not None and m.id not in have_goals:
            session.add(Goalscorer(match_id=m.id, date=m.date, team_id=team, scorer_name=scorer, minute=minute,
                                   own_goal=og, penalty=pen, source=src))
            report["goals"] += 1
    have_stats = {r[0] for r in session.query(MatchStats.match_id)}
    for row in data["stats"]:
        m = matches.get(tuple(row[:4]))
        if m is not None and m.id not in have_stats:
            session.add(MatchStats(match_id=m.id, **dict(zip(data["stats_fields"], row[4:], strict=True))))
            report["stats"] += 1
    session.commit()
    log.info("seed loaded: %s", report)
    return report


if __name__ == "__main__":  # build step: python -m kickcast_api.seed
    from .db import SessionLocal

    s = SessionLocal()
    try:
        print("seed:", load_seed(s))
    finally:
        s.close()
    sys.exit(0)
