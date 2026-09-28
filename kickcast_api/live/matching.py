"""Shared fixture -> Match matching for the two API-Football jobs (poller.py, results_updater.py).

Order: (1) the verified numeric-id crosswalk (big-5 clubs only - built from real /teams
responses); (2) for anything the crosswalk doesn't know - national teams, other leagues -
EXACT equality of canonical team ids (kickcast_engine.data.team_aliases.canonical, the same
normaliser every other source goes through), never substring matching ("Niger" in
"Nigeria"). Candidates are already restricted to the fixture's own date by the callers, and
an ambiguous result (two candidates match) is treated as no match rather than guessed.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from kickcast_engine.data.api_football_crosswalk import crosswalk_id, load_team_crosswalk

from ..models import LiveEvent, Match

CROSSWALK_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "api_football_cache"

_crosswalk: dict[int, str] | None = None


def team_crosswalk() -> dict[int, str]:
    global _crosswalk
    if _crosswalk is None:
        _crosswalk = load_team_crosswalk(CROSSWALK_CACHE_DIR) if CROSSWALK_CACHE_DIR.exists() else {}
    return _crosswalk


def find_match(candidates: list[Match], fx: dict) -> Match | None:
    cw = team_crosswalk()
    home_af, away_af = fx.get("home_team_id"), fx.get("away_team_id")
    home_id = cw.get(home_af) if isinstance(home_af, int) else None
    away_id = cw.get(away_af) if isinstance(away_af, int) else None
    if not (home_id and away_id):
        home_name, away_name = fx.get("home_team_name"), fx.get("away_team_name")
        if not home_name or not away_name:
            return None
        home_id, away_id = crosswalk_id(home_name), crosswalk_id(away_name)
    hits = [m for m in candidates if m.home_team_id == home_id and m.away_team_id == away_id]
    return hits[0] if len(hits) == 1 else None


def sync_events(session: Session, m: Match, events: list[dict]) -> None:
    """API-Football's embedded events list is the full authoritative list for the match
    as of this poll, not a delta - replace what we had rather than appending, so a VAR
    reversal or corrected minute is reflected too."""
    session.query(LiveEvent).filter(LiveEvent.match_id == m.id).delete()
    for e in events:
        team_name = e.get("team_name")
        cid = crosswalk_id(team_name) if team_name else None
        team_id = cid if cid in (m.home_team_id, m.away_team_id) else None
        session.add(
            LiveEvent(
                match_id=m.id,
                minute=e.get("minute") or 0,
                event_type=e.get("event_type") or "other",
                team_id=team_id,
                player=e.get("player"),
                detail=e.get("detail"),
                source="api-football",
            )
        )
