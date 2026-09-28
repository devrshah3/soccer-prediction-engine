"""YouTube Data API v3 search, restricted to official channels, used ONLY to find a link
for an already-established fact (e.g. "here's the highlights for the match we already
told you the score of") - never as a source of the answer itself. Key-gated on
YOUTUBE_API_KEY; returns None (not an error) when missing so callers degrade gracefully.

VERIFIED against a real key and one real call (2026-09-23): GET /youtube/v3/search
returned 200 with the exact shape find_official_highlight() already assumed -
items[0].id.videoId, items[0].snippet.{title,channelTitle,publishedAt}. Also confirmed
WHY the channel restriction matters, not just in theory: an unrestricted `order=date`
search for "UEFA Champions League final highlights" returned fan-compilation/clickbait
channels (e.g. a channel called "GOLVARIO"), not official ones - find_official_highlight
without a resolved `channel` is a real degradation, not a hypothetical one.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy.orm import Session

from ..models import Match, YoutubeSearchCache
from ..serialize import team_names
from . import quota
from .entities import contains_phrase, normalize, team_title_variants

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def _cache_key(query: str, channel: str | None) -> str:
    normalized = " ".join(query.strip().lower().split()) + "|" + (channel or "")
    return hashlib.sha256(normalized.encode()).hexdigest()


# name -> YouTube channel ID (the UC... string, NOT the @handle). These are public,
# stable identifiers, not credentials, so - unlike the 4 API keys - they're safe to check
# into source. VERIFIED for real (2026-09-23) via `channels.list?forHandle=...` (1 quota
# unit each, not the 100-unit search.list), confirming each response's returned title
# actually matches the intended official channel before trusting it:
#   UEFA          -> "UEFA" ("Welcome to the official UEFA YouTube channel...")
#   Premier League-> "Premier League" ("...official Premier League YouTube channel...")
#   LaLiga        -> "LALIGA EA SPORTS" (LaLiga's real channel, sponsor-rebranded title -
#                    not literally "official" in its description, but this IS the
#                    channel linked from laliga.com, not a fan channel)
#   Serie A       -> "Serie A" ("Welcome to the Official Serie A channel...")
#   Bundesliga    -> "Bundesliga" ("...official YouTube page of the Bundesliga...")
#   Ligue 1       -> "Ligue 1 McDonald's" (sponsor-branded official channel, description
#                    literally says "chaîne officielle de la Ligue1 McDonald's")
DEFAULT_OFFICIAL_CHANNELS: dict[str, str] = {
    "UEFA": "UCyGa1YEx9ST66rYrJTGIKOw",
    "Premier League": "UCG5qGWdu8nIRZqJ_GgDwQ-w",
    "LaLiga": "UCTv-XvfzLX3i4IGWAm4sbmA",
    "Serie A": "UCBJeMCIeLQos7wacox4hmLQ",
    "Bundesliga": "UC6UL29enLNe4mqwTfAyeNuw",
    "Ligue 1": "UCQsH5XtIc9hONE1BQjucM0g",
}


def official_channel_ids() -> dict[str, str]:
    """name -> YouTube channel ID, restricting find_official_highlight() to real official
    channels rather than an arbitrary search result. Starts from the verified defaults
    above; YOUTUBE_OFFICIAL_CHANNELS in .env (a JSON object) can add to or override them
    without a code change, e.g. to add a national-team or competition channel."""
    channels = dict(DEFAULT_OFFICIAL_CHANNELS)
    raw = os.environ.get("YOUTUBE_OFFICIAL_CHANNELS")
    if not raw:
        return channels
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            channels.update({str(k): str(v) for k, v in parsed.items()})
    except (json.JSONDecodeError, TypeError):
        pass
    return channels


# competition (league code) -> name of the verified official channel that publishes its highlights.
# The UEFA channel covers the Champions League and UEFA Nations League / European qualifiers only;
# other international matches (friendlies, other confederations, the World Cup) have NO verified
# channel configured, so they honestly get "no verified link".
COMPETITION_CHANNELS: dict[str, str] = {
    "en.1": "Premier League", "es.1": "LaLiga", "it.1": "Serie A", "de.1": "Bundesliga",
    "fr.1": "Ligue 1", "CL": "UEFA",
}
MAX_DAYS_FROM_MATCH = 3
NEGATIVE_TTL = timedelta(hours=6)  # a "nothing found" is re-searched sooner than a hit (highlights get uploaded late)


def channel_name_for(match: Match) -> str | None:
    if match.league_code in COMPETITION_CHANNELS:
        return COMPETITION_CHANNELS[match.league_code]
    if match.league_code == "international" and "UEFA" in (match.round or "").upper():
        return "UEFA"
    return None


def _title_names_both_teams(session: Session, title: str, match: Match) -> bool:
    text = normalize(title)
    return all(
        any(contains_phrase(text, v) for v in team_title_variants(session, team_id))
        for team_id in (match.home_team_id, match.away_team_id)
    )


def _published_within_window(published_at: str, match: Match) -> bool:
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00")).date()
    except ValueError:
        return False
    return abs((published - match.date).days) <= MAX_DAYS_FROM_MATCH


def validate_candidate(session: Session, item: dict, match: Match, allowed_channel_ids: set[str]) -> dict | None:
    """Accept a search hit ONLY if: the channel is on the allowlist, the title names both teams
    (known aliases allowed) and it was published within MAX_DAYS_FROM_MATCH days of the match."""
    snippet = item.get("snippet", {})
    video_id = item.get("id", {}).get("videoId")
    if not video_id or snippet.get("channelId") not in allowed_channel_ids:
        return None
    if not _title_names_both_teams(session, snippet.get("title", ""), match):
        return None
    if not _published_within_window(snippet.get("publishedAt", ""), match):
        return None
    return {
        "title": snippet["title"], "channel": snippet.get("channelTitle", ""),
        "url": f"https://www.youtube.com/watch?v={video_id}", "published_at": snippet["publishedAt"],
    }


def find_match_highlight(session: Session, match: Match) -> dict:
    """Official highlights for ONE of our own match records. The query comes from the record (team
    names, date, competition), never from the user's words. Returns {"status", "video", "channel"}
    with status: found | none (searched, nothing acceptable) | no_channel (no verified channel for
    this competition) | no_key | quota | error."""
    channel_name = channel_name_for(match)
    channels = official_channel_ids()
    if channel_name is None or channel_name not in channels:
        return {"status": "no_channel", "video": None, "channel": channel_name}
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return {"status": "no_key", "video": None, "channel": channel_name}

    key = _cache_key(f"match:{match.id}", channel_name)
    cached = session.get(YoutubeSearchCache, key)
    if cached is not None:
        video: dict | None = json.loads(cached.result_json)
        if video is not None:
            return {"status": "found", "video": video, "channel": channel_name}
        age = datetime.now(timezone.utc) - datetime.fromisoformat(cached.created_at)
        if age < NEGATIVE_TTL:
            return {"status": "none", "video": None, "channel": channel_name}

    if quota.youtube_quota_remaining(session) <= 0:
        return {"status": "quota", "video": None, "channel": channel_name}

    names = team_names(session, {match.home_team_id, match.away_team_id})
    params: dict[str, str | int] = {
        "key": api_key, "part": "snippet", "type": "video", "maxResults": 10,
        "q": f"{names.get(match.home_team_id, match.home_team_id)} {names.get(match.away_team_id, match.away_team_id)} highlights",
        "channelId": channels[channel_name],
        "publishedAfter": f"{(match.date - timedelta(days=1)).isoformat()}T00:00:00Z",
        "publishedBefore": f"{(match.date + timedelta(days=MAX_DAYS_FROM_MATCH + 1)).isoformat()}T00:00:00Z",
    }
    try:
        resp = requests.get(SEARCH_URL, params=params, timeout=10)
        quota.record_youtube_call(session)
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except requests.RequestException:
        return {"status": "error", "video": None, "channel": channel_name}  # transient: not cached

    allowed = set(channels.values())
    accepted = [v for v in (validate_candidate(session, i, match, allowed) for i in items) if v]
    accepted.sort(key=lambda v: "highlight" not in v["title"].lower())  # prefer titles that say so
    video = accepted[0] if accepted else None
    row = cached or YoutubeSearchCache(query_hash=key, query=f"match:{match.id}", channel=channel_name, result_json="null", created_at="")
    row.result_json = json.dumps(video)
    row.created_at = datetime.now(timezone.utc).isoformat()
    session.add(row)
    session.commit()
    return {"status": "found" if video else "none", "video": video, "channel": channel_name}
