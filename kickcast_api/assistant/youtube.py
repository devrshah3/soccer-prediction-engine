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
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

from ..models import YoutubeSearchCache
from . import quota

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def _cache_key(query: str, channel: str | None) -> str:
    normalized = " ".join(query.strip().lower().split()) + "|" + (channel or "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def official_channel_ids() -> dict[str, str]:
    """name -> YouTube channel ID (the UC... string, NOT the @handle), restricting
    find_official_highlight() to real official channels rather than an arbitrary search
    result. NOT pre-populated here: we don't have a verified list of real channel IDs
    (guessing/hardcoding one would risk silently pointing at the wrong channel, which is
    worse than finding no link at all). Set YOUTUBE_OFFICIAL_CHANNELS in .env to a JSON
    object, e.g. {"UEFA": "UCxxxxxxxxxxxxxxxxxxxxxx", "Premier League": "UCxxxx..."},
    with IDs confirmed from each channel's real "About" page. Empty by default -
    find_official_highlight() then falls back to un-channel-restricted search."""
    raw = os.environ.get("YOUTUBE_OFFICIAL_CHANNELS")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def find_official_highlight(session: Session, query: str, channel: str | None = None) -> dict | None:
    """Cached by (query, channel) - a repeated lookup never costs quota twice. A cached
    "no result found" is stored too (as null), so a query we already know fails doesn't
    get re-searched either."""
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return None

    key = _cache_key(query, channel)
    cached = session.get(YoutubeSearchCache, key)
    if cached is not None:
        result: dict | None = json.loads(cached.result_json)
        return result

    if quota.youtube_quota_remaining(session) <= 0:
        return None

    params: dict[str, str | int] = {
        "key": api_key, "part": "snippet", "q": query, "type": "video",
        "maxResults": 3, "order": "date",
    }
    channels = official_channel_ids()
    if channel and channel in channels:
        params["channelId"] = channels[channel]

    try:
        resp = requests.get(SEARCH_URL, params=params, timeout=10)
        quota.record_youtube_call(session)
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except requests.RequestException:
        return None  # transient failure - don't cache, worth retrying later

    result = None
    video_id = (items[0].get("id", {}) if items else {}).get("videoId")
    if items and video_id:
        video = items[0]
        result = {
            "title": video["snippet"]["title"],
            "channel": video["snippet"]["channelTitle"],
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "published_at": video["snippet"]["publishedAt"],
        }
    session.add(
        YoutubeSearchCache(
            query_hash=key, query=query, channel=channel,
            result_json=json.dumps(result), created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    session.commit()
    return result
