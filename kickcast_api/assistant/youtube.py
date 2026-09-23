"""YouTube Data API v3 search, restricted to official channels, used ONLY to find a link
for an already-established fact (e.g. "here's the highlights for the match we already
told you the score of") - never as a source of the answer itself. Key-gated on
YOUTUBE_API_KEY; returns None (not an error) when missing so callers degrade gracefully.
"""

from __future__ import annotations

import json
import os

import requests
from sqlalchemy.orm import Session

from . import quota

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


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
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return None
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
        return None
    if not items:
        return None
    video = items[0]
    video_id = video.get("id", {}).get("videoId")
    if not video_id:
        return None
    return {
        "title": video["snippet"]["title"],
        "channel": video["snippet"]["channelTitle"],
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "published_at": video["snippet"]["publishedAt"],
    }
