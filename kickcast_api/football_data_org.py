"""football-data.org v4 client (free tier: 10 requests/minute, no documented daily cap).
Key-gated on FOOTBALL_DATA_ORG_API_KEY.

VERIFIED against a real key and one real call (2026-09-23): GET /v4/competitions/CL
returned 200 and confirmed the exact header names the free tier actually sends (header
names are case-insensitive over HTTP and `requests` normalizes lookups, but the raw
response had them as "X-RequestCounter-Reset" and "x-requests-available-minute") -
X-RequestCounter-Reset is seconds until the per-minute window resets, and
x-requests-available-minute is calls left in the current window. Also confirmed the
Champions League's real competition code is "CL" (id 2001) - used by item 5's fixtures
work. Body shape for /competitions/{code} confirmed: area/id/name/code/type/emblem/
currentSeason/seasons/lastUpdated.

Throttling: football-data.org tells us its own real-time rate-limit state on every
response, so we track it client-side (module-level - this project runs one backend
process, so this is sufficient; a multi-process deployment would need a shared store
instead) and sleep BEFORE a call if the last known remaining count was 0, rather than
firing a request we already know will be rejected. This keeps us under 10 calls/minute
for real, not just by assumption. A 429 (the server disagreeing with our tracking, e.g.
after a fresh process start with no prior state) forces a full-minute backoff rather
than retrying immediately.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping

import requests

from . import settings

BASE_URL = "https://api.football-data.org/v4"

# module-level, single-process throttle state - see docstring
_state: dict[str, float | None] = {"available_minute": None, "reset_at": None}


def available() -> bool:
    return bool(os.environ.get("FOOTBALL_DATA_ORG_API_KEY")) and settings.enable_football_data_org()


def _headers() -> dict[str, str]:
    return {"X-Auth-Token": os.environ["FOOTBALL_DATA_ORG_API_KEY"]}


def _throttle_if_needed() -> None:
    remaining = _state["available_minute"]
    reset_at = _state["reset_at"]
    if remaining is not None and remaining <= 0 and reset_at is not None:
        wait = reset_at - time.monotonic()
        if wait > 0:
            time.sleep(wait)


def _record_headers(headers: Mapping[str, str]) -> None:
    avail = headers.get("x-requests-available-minute")
    reset = headers.get("x-requestcounter-reset")
    if avail is not None:
        try:
            _state["available_minute"] = int(avail)
        except ValueError:
            pass
    if reset is not None:
        try:
            _state["reset_at"] = time.monotonic() + int(reset)
        except ValueError:
            pass


def get(path: str, params: dict | None = None) -> dict | None:
    """GET a football-data.org v4 endpoint, e.g. get("/competitions/CL/matches"). Returns
    the parsed JSON body, or None if unavailable/throttled-and-declined/errored - callers
    must treat None as "try again later", never fabricate a response."""
    if not available():
        return None
    _throttle_if_needed()
    try:
        resp = requests.get(f"{BASE_URL}{path}", params=params, headers=_headers(), timeout=15)
    except requests.RequestException:
        return None
    _record_headers(resp.headers)
    if resp.status_code == 429:
        # Server disagrees with our tracking (e.g. fresh process, or another caller in
        # this process raced us) - back off a full minute rather than retry immediately.
        _state["available_minute"] = 0
        _state["reset_at"] = time.monotonic() + 60
        return None
    try:
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError):
        return None
