"""API-Football v3 client (free tier: 100 requests/day). Key-gated on API_FOOTBALL_KEY.

VERIFIED against a real key and real calls (2026-09-23): `/status` confirmed a real
Free-plan account (100 requests/day, matches DEFAULT_API_FOOTBALL_DAILY_QUOTA below).
`/fixtures?live=all` confirmed `_parse_fixture`'s shape assumptions are correct
(fixture.id/status.elapsed/status.short, teams.home/away.name, goals.home/away) against
29 real live fixtures. Also discovered something the docs don't make obvious: each
fixture object in the `live=all` response already embeds its OWN full events array
(`f["events"]`) - cross-checked one live match with 8 goals at the 82nd minute against
a separate `/fixtures/events?fixture=...` call for the same match and got byte-identical
results (8/8 events, same minutes/types/teams). So `fetch_events()` below, which makes a
SEPARATE per-match call, is no longer needed for the normal polling path - poller.py now
reads events straight off the batched live=all response via `_parse_fixture`'s "events"
key, at zero extra quota cost. `fetch_events()` is kept only as a manual/fallback tool
(e.g. to backfill a match's final events if it dropped out of live=all before the last
poll caught its final whistle) - it is NOT called from the automatic poll loop anymore.

Ground rules honored: ONE batched call fetches ALL live fixtures AND their events at
once (`/fixtures?live=all`), never one call per match; nothing here is called from a
request handler - only from kickcast_api.live.poller, itself only invoked by a
scheduled job, never page load.
"""

from __future__ import annotations

import os

import requests
from sqlalchemy.orm import Session

from . import quota

BASE_URL = "https://v3.football.api-sports.io"


def available() -> bool:
    return bool(os.environ.get("API_FOOTBALL_KEY"))


def _headers() -> dict[str, str]:
    return {"x-apisports-key": os.environ["API_FOOTBALL_KEY"]}


def fetch_live_fixtures(session: Session) -> list[dict] | None:
    """One call, all currently-live fixtures across every competition API-Football
    covers. Returns None if unavailable/quota-exhausted/errored."""
    if not available() or quota.api_football_quota_remaining(session) <= 0:
        return None
    try:
        resp = requests.get(f"{BASE_URL}/fixtures", params={"live": "all"}, headers=_headers(), timeout=15)
        quota.record_api_football_call(session)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return None
    return [_parse_fixture(f) for f in payload.get("response", [])]


def fetch_events(session: Session, fixture_id: int) -> list[dict] | None:
    """Per-match event detail - call sparingly (budget is shared with fetch_live_fixtures)."""
    if not available() or quota.api_football_quota_remaining(session) <= 0:
        return None
    try:
        resp = requests.get(f"{BASE_URL}/fixtures/events", params={"fixture": fixture_id}, headers=_headers(), timeout=15)
        quota.record_api_football_call(session)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return None
    return [_parse_event(e) for e in payload.get("response", [])]


def _parse_fixture(f: dict) -> dict:
    fixture = f.get("fixture", {})
    teams = f.get("teams", {})
    goals = f.get("goals", {})
    return {
        "fixture_id": fixture.get("id"),
        "minute": (fixture.get("status") or {}).get("elapsed"),
        "match_status": (fixture.get("status") or {}).get("short"),
        "home_team_name": (teams.get("home") or {}).get("name"),
        "away_team_name": (teams.get("away") or {}).get("name"),
        "home_score": goals.get("home"),
        "away_score": goals.get("away"),
        # embedded in live=all, verified real - see module docstring
        "events": [_parse_event(e) for e in f.get("events") or []],
    }


def _parse_event(e: dict) -> dict:
    return {
        "minute": (e.get("time") or {}).get("elapsed"),
        "event_type": {"Goal": "goal", "Card": "card", "subst": "substitution"}.get(str(e.get("type")), "other"),
        "team_name": (e.get("team") or {}).get("name"),
        "player": (e.get("player") or {}).get("name"),
        "detail": e.get("detail"),
    }
