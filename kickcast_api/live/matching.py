"""Shared fixture -> Match matching for the live/result sources (API-Football's poller.py and
results_updater.py, and espn.py). See find_match for the rules."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from sqlalchemy.orm import Session

from kickcast_engine.data import international
from kickcast_engine.data.api_football_crosswalk import crosswalk_id, load_team_crosswalk

from ..models import LiveEvent, Match, Team

CROSSWALK_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "api_football_cache"

_crosswalk: dict[int, str] | None = None


def team_crosswalk() -> dict[int, str]:
    global _crosswalk
    if _crosswalk is None:
        _crosswalk = load_team_crosswalk(CROSSWALK_CACHE_DIR) if CROSSWALK_CACHE_DIR.exists() else {}
    return _crosswalk


def _norm(name: str) -> str:
    """Accent-, punctuation- and 'and'/'&'-insensitive form: 'Bosnia-Herzegovina' and
    'Bosnia and Herzegovina' and 'bosnia-and-herzegovina' all become 'bosnia herzegovina'."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    return " ".join(t for t in re.sub(r"[^a-z0-9]+", " ", text).split() if t not in {"and", "fc", "afc"})


def _fixture_keys(name: str) -> set[str]:
    return {_norm(name), _norm(international.canonical(name)), _norm(crosswalk_id(name))}


def _team_keys(session: Session, team_id: str, cache: dict[str, set[str]]) -> set[str]:
    if team_id not in cache:
        team = session.get(Team, team_id)
        keys = {_norm(team_id)}
        if team is not None:
            keys |= {_norm(team.name), _norm(international.canonical(team.name))}
        cache[team_id] = keys
    return cache[team_id]


def find_match(session: Session, candidates: list[Match], fx: dict) -> Match | None:
    """Verified id crosswalk first (big-5 clubs only); otherwise normalised-name equality
    against OUR team's id/name. Never substring matching, and an ambiguous result (two
    candidates match) is no match - a wrong pairing would put a real score on the wrong game."""
    cw = team_crosswalk()
    home_af, away_af = fx.get("home_team_id"), fx.get("away_team_id")
    home_id = cw.get(home_af) if isinstance(home_af, int) else None
    away_id = cw.get(away_af) if isinstance(away_af, int) else None
    if home_id and away_id:
        hits = [m for m in candidates if m.home_team_id == home_id and m.away_team_id == away_id]
        return hits[0] if len(hits) == 1 else None
    home_name, away_name = fx.get("home_team_name"), fx.get("away_team_name")
    if not home_name or not away_name:
        return None
    home_keys, away_keys = _fixture_keys(home_name), _fixture_keys(away_name)
    cache: dict[str, set[str]] = {}
    hits = [
        m for m in candidates
        if home_keys & _team_keys(session, m.home_team_id, cache) and away_keys & _team_keys(session, m.away_team_id, cache)
    ]
    return hits[0] if len(hits) == 1 else None


def sync_events(session: Session, m: Match, events: list[dict], source: str = "api-football") -> None:
    """A provider's event list is the full authoritative list for the match as of this poll,
    not a delta - replace what we had rather than appending, so a VAR reversal or corrected
    minute is reflected too."""
    session.query(LiveEvent).filter(LiveEvent.match_id == m.id).delete()
    cache: dict[str, set[str]] = {}
    home_keys, away_keys = _team_keys(session, m.home_team_id, cache), _team_keys(session, m.away_team_id, cache)
    for e in events:
        keys = _fixture_keys(e["team_name"]) if e.get("team_name") else set()
        # A name that fits BOTH teams (or neither) stays unresolved rather than guessed.
        team_id = m.home_team_id if keys & home_keys and not keys & away_keys else m.away_team_id if keys & away_keys and not keys & home_keys else None
        session.add(
            LiveEvent(
                match_id=m.id,
                minute=e.get("minute") or 0,
                event_type=e.get("event_type") or "other",
                team_id=team_id,
                player=e.get("player"),
                detail=e.get("detail"),
                source=source,
            )
        )
