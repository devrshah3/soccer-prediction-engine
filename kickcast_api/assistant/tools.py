"""DB-backed "tools": the only way either the Gemini-powered assistant or the keyless
DB-only fallback are allowed to state a fact (score, scorer, minute, table position,
prediction). Neither path may state a fact that didn't come from calling one of these.

Each entry in TOOLS pairs a JSON-schema function declaration (for Gemini's native
function-calling: https://ai.google.dev/gemini-api/docs/function-calling) with the
Python callable that actually answers it, `run(session, **args) -> dict`, so the two
never drift apart.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import League, Match, Team
from ..predictions import get_model
from ..serialize import latest_season, match_dict, standings


def resolve_team(session: Session, name_fragment: str) -> dict:
    """Find teams whose name contains the given text (case-insensitive). Use this FIRST
    to turn a team name mentioned in a question into a team_id for the other tools."""
    rows = session.query(Team).filter(Team.name.ilike(f"%{name_fragment}%")).limit(8).all()
    teams = [{"id": t.id, "name": t.name, "country": t.country} for t in rows]
    return {"found": bool(teams), "teams": teams}


def team_next_match(session: Session, team_id: str) -> dict:
    m = (
        session.query(Match)
        .filter(or_(Match.home_team_id == team_id, Match.away_team_id == team_id), Match.status == "scheduled")
        .order_by(Match.date.asc())
        .first()
    )
    if m is None:
        return {"found": False}
    return {"found": True, "match": match_dict(session, m)}


def team_recent_results(session: Session, team_id: str, limit: int = 5) -> dict:
    rows = (
        session.query(Match)
        .filter(or_(Match.home_team_id == team_id, Match.away_team_id == team_id), Match.status == "finished")
        .order_by(Match.date.desc())
        .limit(limit)
        .all()
    )
    return {"found": bool(rows), "matches": [match_dict(session, m) for m in rows]}


def league_standings_top(session: Session, league_code: str, n: int = 6) -> dict:
    season = latest_season(session, league_code)
    if season is None:
        return {"found": False}
    table = standings(session, league_code, season)[:n]
    return {"found": True, "season": season, "table": table}


def team_league_position(session: Session, team_id: str) -> dict:
    row = (
        session.query(Match.league_code)
        .filter(or_(Match.home_team_id == team_id, Match.away_team_id == team_id), Match.league_code != "international")
        .order_by(Match.date.desc())
        .first()
    )
    if row is None:
        return {"found": False}
    league_code = row[0]
    season = latest_season(session, league_code)
    if season is None:
        return {"found": False}
    # league_name is the real display name from the leagues table (e.g. "Premier League"),
    # not the internal code - never state "en.1" to a user, see fallback.py's callers.
    league = session.get(League, league_code)
    league_name = league.name if league else league_code
    for r in standings(session, league_code, season):
        if r["team_id"] == team_id:
            return {"found": True, "league_code": league_code, "league_name": league_name, "season": season, **r}
    return {"found": False}


def match_prediction_lookup(session: Session, home_team_id: str, away_team_id: str) -> dict:
    """Our own model's prediction for a matchup (uses the next scheduled fixture between
    these two teams if one exists, else predicts the matchup directly)."""
    upcoming = (
        session.query(Match)
        .filter(
            or_(
                (Match.home_team_id == home_team_id) & (Match.away_team_id == away_team_id),
                (Match.home_team_id == away_team_id) & (Match.away_team_id == home_team_id),
            ),
            Match.status == "scheduled",
        )
        .order_by(Match.date.asc(), Match.kickoff.asc())
        .all()
    )
    m = upcoming[0] if upcoming else None
    league_code = m.league_code if m else _guess_league(session, home_team_id, away_team_id)
    if league_code is None:
        return {"found": False, "reason": "couldn't determine which competition these teams play in"}
    model = get_model(session, league_code)
    if model is None:
        return {"found": False, "reason": "not enough finished-match history to fit a model yet"}
    home, away = (m.home_team_id, m.away_team_id) if m else (home_team_id, away_team_id)
    pred = model.predict(home, away, neutral=(m.neutral if m else False))
    # "match" is the fixture record: its home/away order is the ONLY source of who is at home
    # (never the order teams appear in the question). fixtures_upcoming lets the caller say
    # "the next of N" when several fixtures exist.
    return {
        "found": True, "match": match_dict(session, m) if m else None, "prediction": pred,
        "fixtures_upcoming": len(upcoming),
    }


def _guess_league(session: Session, home_team_id: str, away_team_id: str) -> str | None:
    for team_id in (home_team_id, away_team_id):
        row = (
            session.query(Match.league_code)
            .filter(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
            .order_by(Match.date.desc())
            .first()
        )
        if row:
            return row[0]
    return None


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[..., dict]


TOOLS: list[Tool] = [
    Tool(
        "resolve_team", "Find team IDs matching a name mentioned in the question. Call this "
        "before any other tool that needs a team_id.",
        {"type": "object", "properties": {"name_fragment": {"type": "string"}}, "required": ["name_fragment"]},
        resolve_team,
    ),
    Tool(
        "team_next_match", "The next scheduled match for a team.",
        {"type": "object", "properties": {"team_id": {"type": "string"}}, "required": ["team_id"]},
        team_next_match,
    ),
    Tool(
        "team_recent_results", "A team's most recent finished match results with scores.",
        {"type": "object", "properties": {"team_id": {"type": "string"}, "limit": {"type": "integer"}},
         "required": ["team_id"]},
        team_recent_results,
    ),
    Tool(
        "league_standings_top", "Top of a league table for its current season. league_code is "
        "one of en.1 (Premier League), es.1 (La Liga), it.1 (Serie A), de.1 (Bundesliga), "
        "fr.1 (Ligue 1), or 'international'.",
        {"type": "object", "properties": {"league_code": {"type": "string"}, "n": {"type": "integer"}},
         "required": ["league_code"]},
        league_standings_top,
    ),
    Tool(
        "team_league_position", "A team's current league position/points/form.",
        {"type": "object", "properties": {"team_id": {"type": "string"}}, "required": ["team_id"]},
        team_league_position,
    ),
    Tool(
        "match_prediction_lookup", "Our model's win/draw/loss prediction for a matchup between "
        "two teams (by team_id).",
        {"type": "object", "properties": {"home_team_id": {"type": "string"}, "away_team_id": {"type": "string"}},
         "required": ["home_team_id", "away_team_id"]},
        match_prediction_lookup,
    ),
]

TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}
