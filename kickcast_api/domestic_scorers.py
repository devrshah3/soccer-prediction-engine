"""Domestic-league likely-scorer probabilities + a historical Golden Boot leaderboard,
from real API-Football free-tier topscorer data (season=2024 - see
scripts/fetch_api_football.py for why that's the most recent season this plan can see,
NOT the live 2026-27 season; a paid plan would be needed for that).

Real data-quality issue found and filtered for: API-Football's free-tier topscorers
endpoint sometimes returns CUMULATIVE stats across a player's whole tenure at their
CURRENT club in a league, not a clean single-season total, for a player who changed
clubs within the tracked window - one real entry (Matheus Cunha, Manchester United,
Premier League) showed 66 appearances for a competition with 38 fixtures/season, an
impossible single-season figure. Filtered out: any entry whose appearances exceed the
league's real single-season match cap (38 for the 20-team leagues, 34 for the
18-team ones) - the other 4 of 5 leagues' top scorers all looked clean (30-36 apps).

NOT walk-forward backtested, unlike every other model in this codebase - deliberately,
not an oversight. The project's international scorer model (kickcast_engine.models.
goalscorers) can be validated because goalscorers.csv has per-goal, per-match, dated
events across many seasons, so a share-of-recent-goals prediction can be checked
against what actually happened next. This module only has ONE season's worth of
SEASON-TOTAL goal counts (no per-goal timestamps, and the free API-Football tier
won't serve additional historical seasons beyond 2022-2024 - see
scripts/fetch_api_football.py) - there is no held-out future to walk forward into, and
no per-event data to build a walk-forward target from even if there were. What WAS
done instead: the data-quality filter above (caught and removed a real bad row), and a
real spot-check that the resulting leaders match public knowledge (Mbappé/Real Madrid,
Kane/Bayern, Retegui/Genoa, Greenwood/Marseille all check out as their leagues' real
2024-25 top scorers). Treat likely-scorer probabilities from this module as a
real-data-grounded heuristic, not a validated, calibrated model - said explicitly in
every API response via the "method" field, not left implicit.
"""

from __future__ import annotations

import json
from pathlib import Path

from kickcast_engine.data.api_football_crosswalk import crosswalk_id
from kickcast_engine.models.goalscorers import likely_scorers

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "api_football_cache"
SEASON_LABEL = "2024-25"  # API-Football's season=2024
SOURCE = "API-Football (free tier, 2024-25 season - most recent this plan can access)"

LEAGUE_MAX_APPEARANCES = {"en.1": 38, "es.1": 38, "it.1": 38, "de.1": 34, "fr.1": 34}
LEAGUE_CACHE_NAMES = {
    "en.1": "premier_league", "es.1": "la_liga", "it.1": "serie_a", "de.1": "bundesliga", "fr.1": "ligue_1",
}


def _load_raw(league_code: str) -> list[dict]:
    name = LEAGUE_CACHE_NAMES.get(league_code)
    if name is None:
        return []
    f = CACHE_DIR / f"topscorers_{name}.json"
    if not f.exists():
        return []
    data: dict = json.loads(f.read_text())
    return data.get("response", [])


def _clean_entries(league_code: str) -> list[dict]:
    max_apps = LEAGUE_MAX_APPEARANCES.get(league_code, 38)
    out = []
    for entry in _load_raw(league_code):
        stats = entry["statistics"][0]
        apps = stats["games"]["appearences"] or 0
        goals = stats["goals"]["total"] or 0
        if apps > max_apps or goals <= 0:
            continue  # likely cross-club cumulative stats, not a clean single-season total - see module docstring
        out.append({
            "player": entry["player"]["name"],
            "team_id": crosswalk_id(stats["team"]["name"]),
            "team_name": stats["team"]["name"],
            "goals": goals,
            "appearances": apps,
        })
    return out


def available(league_code: str) -> bool:
    return league_code in LEAGUE_CACHE_NAMES and (CACHE_DIR / f"topscorers_{LEAGUE_CACHE_NAMES[league_code]}.json").exists()


def team_likely_scorers(league_code: str, team_id: str, expected_goals: float) -> list[dict]:
    goals = [(e["player"], e["goals"]) for e in _clean_entries(league_code) if e["team_id"] == team_id]
    return likely_scorers(goals, expected_goals)


def league_top_scorers(league_code: str, limit: int = 10) -> list[dict]:
    entries = sorted(_clean_entries(league_code), key=lambda r: -r["goals"])
    return entries[:limit]
