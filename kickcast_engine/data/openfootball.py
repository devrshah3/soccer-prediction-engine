"""openfootball/football.json loader (CC0, free, no rate limit).

Gives ~13-17 seasons per big-5 league: real history for training, plus the
current season's played results and not-yet-played fixtures for the site.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ..models.dixon_coles import MatchResult

SOURCE = "openfootball/football.json"
LEAGUES: dict[str, dict] = {
    "en.1": {"name": "Premier League", "country": "England"},
    "es.1": {"name": "La Liga", "country": "Spain"},
    "it.1": {"name": "Serie A", "country": "Italy"},
    "de.1": {"name": "Bundesliga", "country": "Germany"},
    "fr.1": {"name": "Ligue 1", "country": "France"},
}


def _full_time(m: dict) -> list[int] | None:
    s = m.get("score")
    if isinstance(s, dict):
        return s.get("ft")
    if isinstance(s, list) and len(s) == 2:
        return s
    return None


def load_season(repo_dir: Path, code: str, season: str) -> list[dict]:
    """Raw rows (played + upcoming) for one league-season, e.g. code='en.1', season='2026-27'."""
    f = repo_dir / season / f"{code}.json"
    if not f.exists():
        return []
    data = json.loads(f.read_text())
    out = []
    for m in data["matches"]:
        ft = _full_time(m)
        out.append(
            {
                "source": SOURCE,
                "competition": LEAGUES[code]["name"],
                "country": LEAGUES[code]["country"],
                "season": season,
                "round": m.get("round"),
                "date": m["date"],
                "kickoff": m.get("time"),
                "home": m["team1"],
                "away": m["team2"],
                "home_goals": ft[0] if ft else None,
                "away_goals": ft[1] if ft else None,
                "status": "finished" if ft else "scheduled",
            }
        )
    out.sort(key=lambda r: (r["date"], r.get("kickoff") or ""))
    return out


def load_all_seasons(repo_dir: Path, code: str) -> list[dict]:
    rows = []
    for season_dir in sorted(repo_dir.glob("20??-??")):
        rows += load_season(repo_dir, code, season_dir.name)
    return rows


def to_training_matches(rows: list[dict]) -> list[MatchResult]:
    return [
        MatchResult(date.fromisoformat(r["date"]), r["home"], r["away"], r["home_goals"], r["away_goals"])
        for r in rows
        if r["status"] == "finished"
    ]


def standings(rows: list[dict], season: str) -> list[dict]:
    """Played/W/D/L/GF/GA/GD/Pts table for one season, sorted, with last-5 form."""
    table: dict[str, dict] = {}

    def row(team: str) -> dict:
        return table.setdefault(
            team, {"team": team, "played": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "form": []}
        )

    for r in rows:
        if r["season"] != season or r["status"] != "finished":
            continue
        h, a = row(r["home"]), row(r["away"])
        hg, ag = r["home_goals"], r["away_goals"]
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
    out = []
    for t in table.values():
        t["gd"] = t["gf"] - t["ga"]
        t["pts"] = t["w"] * 3 + t["d"]
        t["form"] = t["form"][-5:]
        out.append(t)
    out.sort(key=lambda t: (-t["pts"], -t["gd"], -t["gf"], t["team"]))
    for i, t in enumerate(out, 1):
        t["position"] = i
    return out


def team_fixtures(rows: list[dict], team: str, season: str) -> list[dict]:
    return [r for r in rows if r["season"] == season and (r["home"] == team or r["away"] == team)]
