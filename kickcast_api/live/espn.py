"""ESPN's public scoreboard as a second, keyless results/live source.

Why it exists: API-Football's free plan is 100 calls/day and football-data.org's free tier has
no Nations League (and no goal/booking detail for anything) - on 2026-09-28 that left every
Nations League match without a score, all day. ESPN's scoreboard endpoint
(`site.api.espn.com/apis/site/v2/sports/soccer/<slug>/scoreboard?dates=YYYYMMDD`) returned,
for all 8 of that day's Nations League matches, the final score, status and a per-match
`details` list: goals (scorer, minute, penalty/own-goal flags) and yellow/red cards.

It is an UNDOCUMENTED, unofficial endpoint with no published terms, so - like API-Football -
it is on by default in development and OFF in production unless ENABLE_ESPN is set (see
settings.enable_espn and DEPLOY.md). It is only ever called from the scheduled job
(scheduler.py), never a request handler, and only inside the same match-window logic as the
other results source.

Output matches api_football._parse_fixture's shape so results_updater._apply_fixtures can
treat both identically; teams are matched by NAME (find_match), never by an ESPN id.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import requests

from .. import settings

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# our league_code -> ESPN league slugs to ask for. 'international' covers the competitions
# our fixtures list actually contains; a slug with no games that day just returns no events.
SLUGS: dict[str, list[str]] = {
    "en.1": ["eng.1"], "es.1": ["esp.1"], "it.1": ["ita.1"], "de.1": ["ger.1"], "fr.1": ["fra.1"],
    "CL": ["uefa.champions"],
    "international": ["uefa.nations", "fifa.friendly", "fifa.world", "uefa.euroq", "fifa.worldq.uefa"],
}

# ESPN status.type.name -> the API-Football short codes the rest of the code already understands.
_STATUS = {
    "STATUS_FIRST_HALF": "1H", "STATUS_HALFTIME": "HT", "STATUS_SECOND_HALF": "2H",
    "STATUS_EXTRA_TIME": "ET", "STATUS_END_OF_REGULATION": "2H", "STATUS_END_OF_EXTRA_TIME": "ET",
    "STATUS_SHOOTOUT": "P", "STATUS_FULL_TIME": "FT", "STATUS_FINAL": "FT",
    "STATUS_FINAL_AET": "AET", "STATUS_FINAL_PEN": "PEN",
}
_CLOCK = re.compile(r"(\d+)'(?:\s*\+\s*(\d+)')?")


# Last outcome per request, for /meta - so a deployment can say WHY it has no live results
# (disabled, blocked, network) without anyone needing its logs.
status: dict = {"last_attempt": None, "last_ok": None, "last_error": None}


def available() -> bool:
    return settings.enable_espn()


def _minute(display: str | None) -> int | None:
    m = _CLOCK.search(display or "")
    return int(m.group(1)) + int(m.group(2) or 0) if m else None


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_event(ev: dict) -> dict | None:
    """One ESPN scoreboard event -> our fixture dict, or None if it hasn't started (or is
    postponed/cancelled - no result to record)."""
    comp = (ev.get("competitions") or [{}])[0]
    code = _STATUS.get(((ev.get("status") or {}).get("type") or {}).get("name", ""))
    if code is None:
        return None
    teams = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    home, away = teams.get("home"), teams.get("away")
    if not home or not away:
        return None
    names = {(c.get("team") or {}).get("id"): (c.get("team") or {}).get("displayName") for c in (home, away)}

    events: list[dict] = []
    for d in comp.get("details", []):
        if d.get("shootout"):
            continue
        who = ((d.get("athletesInvolved") or [{}])[0]).get("displayName")
        minute = _minute((d.get("clock") or {}).get("displayValue"))
        team = names.get((d.get("team") or {}).get("id"))
        if d.get("scoringPlay"):
            detail = "Own Goal" if d.get("ownGoal") else "Penalty" if d.get("penaltyKick") else "Normal Goal"
            events.append({"minute": minute, "event_type": "goal", "team_name": team, "player": who, "detail": detail})
        elif d.get("redCard") or d.get("yellowCard"):
            events.append({
                "minute": minute, "event_type": "card", "team_name": team, "player": who,
                "detail": "Red Card" if d.get("redCard") else "Yellow Card",
            })
    return {
        "fixture_id": None,
        "minute": _minute((ev["status"]).get("displayClock")),
        "match_status": code,
        "home_team_id": None, "away_team_id": None,
        "home_team_name": (home.get("team") or {}).get("displayName"),
        "away_team_name": (away.get("team") or {}).get("displayName"),
        "home_score": _int(home.get("score")), "away_score": _int(away.get("score")),
        "events": events,
        "source": "espn",
        "events_authoritative": True,  # the list is complete as of this poll - even an empty one (0-0)
    }


def fetch_fixtures(day_iso: str, league_codes: set[str]) -> list[dict] | None:
    """Every started/finished fixture on `day_iso` for the ESPN slugs behind `league_codes`.
    None if disabled or NO slug could be fetched (so the caller doesn't record a check)."""
    if not available():
        return None
    status["last_attempt"] = datetime.now(timezone.utc).isoformat()
    slugs = [s for code in sorted(league_codes) for s in SLUGS.get(code, [])]
    out: list[dict] = []
    ok = False
    for slug in slugs:
        try:
            resp = requests.get(
                f"{BASE_URL}/{slug}/scoreboard", params={"dates": day_iso.replace("-", "")}, timeout=15,
                # library-default User-Agent on purpose: verified 2026-09-28, a custom UA string got HTTP 403
                # from this endpoint while the default got 200.
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            status["last_error"] = f"{slug}: {type(exc).__name__}: {str(exc)[:120]}"
            continue
        ok = True
        out.extend(f for e in payload.get("events", []) if (f := parse_event(e)) is not None)
    if ok:
        status["last_ok"] = status["last_attempt"]
    return out if ok else None
