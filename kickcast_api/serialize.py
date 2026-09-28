"""Shared read helpers: standings table + last-5 form, used by both the leagues and
teams routes so the numbers can't drift apart.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import LiveMatchState, Match, Team


def team_names(session: Session, team_ids: set[str]) -> dict[str, str]:
    return {t.id: t.name for t in session.query(Team).filter(Team.id.in_(team_ids))}


def _live_info(session: Session, m: Match) -> dict | None:
    """Provider live state for a not-yet-finished match, only if the poller has written
    one (needs API_FOOTBALL_KEY) - otherwise None, and the frontend falls back to elapsed
    time since kickoff rather than inventing a live flag or score."""
    if m.status == "finished":
        return None
    state = session.get(LiveMatchState, m.id)
    if state is None:
        return None
    return {
        "match_status": state.match_status,
        "minute": state.minute,
        "home_score": state.home_score,
        "away_score": state.away_score,
    }


def match_dict(session: Session, m: Match) -> dict:
    names = team_names(session, {m.home_team_id, m.away_team_id})
    return {
        "id": m.id,
        "league_code": m.league_code,
        "season": m.season,
        "date": m.date.isoformat(),
        "kickoff": m.kickoff,
        "round": m.round,
        "status": m.status,
        "home_team": {"id": m.home_team_id, "name": names.get(m.home_team_id, m.home_team_id)},
        "away_team": {"id": m.away_team_id, "name": names.get(m.away_team_id, m.away_team_id)},
        "home_goals": m.home_goals,
        "away_goals": m.away_goals,
        "neutral": m.neutral,
        "source": m.source,
        "live": _live_info(session, m),
    }


def latest_season(session: Session, league_code: str) -> str | None:
    row = (
        session.query(Match.season)
        .filter(Match.league_code == league_code)
        .order_by(Match.date.desc())
        .first()
    )
    return row[0] if row else None


def seasons(session: Session, league_code: str) -> list[str]:
    rows = session.query(Match.season).filter(Match.league_code == league_code).distinct().all()
    return sorted((r[0] for r in rows), reverse=True)


def standings(session: Session, league_code: str, season: str) -> list[dict[str, Any]]:
    matches = (
        session.query(Match)
        .filter(Match.league_code == league_code, Match.season == season, Match.status == "finished")
        .order_by(Match.date)
        .all()
    )
    table: dict[str, dict[str, Any]] = {}

    def row(team_id: str) -> dict[str, Any]:
        return table.setdefault(
            team_id, {"team_id": team_id, "played": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "form": []}
        )

    for m in matches:
        h, a = row(m.home_team_id), row(m.away_team_id)
        hg, ag = m.home_goals or 0, m.away_goals or 0
        h["played"] += 1
        a["played"] += 1
        h["gf"] += hg
        h["ga"] += ag
        a["gf"] += ag
        a["ga"] += hg
        if hg > ag:
            h["w"] += 1
            a["l"] += 1
            h["form"].append("W")
            a["form"].append("L")
        elif hg < ag:
            a["w"] += 1
            h["l"] += 1
            a["form"].append("W")
            h["form"].append("L")
        else:
            h["d"] += 1
            a["d"] += 1
            h["form"].append("D")
            a["form"].append("D")

    team_names = {t.id: t.name for t in session.query(Team).filter(Team.id.in_(table.keys()))}
    out = []
    for t in table.values():
        t["gd"] = t["gf"] - t["ga"]
        t["pts"] = t["w"] * 3 + t["d"]
        t["form"] = t["form"][-5:]
        t["team_name"] = team_names.get(t["team_id"], t["team_id"])
        out.append(t)
    out.sort(key=lambda t: (-t["pts"], -t["gd"], -t["gf"], t["team_name"]))
    for i, t in enumerate(out, 1):
        t["position"] = i
    return out


def team_position(session: Session, league_code: str, season: str, team_id: str) -> int | None:
    for row in standings(session, league_code, season):
        if row["team_id"] == team_id:
            return row["position"]
    return None
