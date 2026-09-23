"""API-Football v3 client (free tier: 100 requests/day). Key-gated on API_FOOTBALL_KEY.

CAVEAT (see MORNING_REPORT.md): written against API-Football v3's documented response
shape from public documentation, NEVER exercised against a live key (none was provided).
The response-parsing in `_parse_fixture`/`_parse_event` is best-effort and should be
verified/adjusted against a real response the first time a real key is added - tests
here use a hand-built mock response shaped like the documented format, which proves our
parsing/quota/batching logic is internally consistent, not that it matches the live API
byte-for-byte.

Ground rules honored: ONE batched call fetches ALL live fixtures at once
(`/fixtures?live=all`), never one call per match; per-match event detail
(`/fixtures/events`) is fetched only for matches we're actually about to show, to
conserve the 100/day budget; nothing here is called from a request handler - only from
kickcast_api.live.poller, itself only invoked by a scheduled job, never page load.
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
    }


def _parse_event(e: dict) -> dict:
    return {
        "minute": (e.get("time") or {}).get("elapsed"),
        "event_type": {"Goal": "goal", "Card": "card", "subst": "substitution"}.get(str(e.get("type")), "other"),
        "team_name": (e.get("team") or {}).get("name"),
        "player": (e.get("player") or {}).get("name"),
        "detail": e.get("detail"),
    }
