"""Server-side conversation context: the last recognised match / teams / player per
conversation, so follow-ups like "a video link", "highlights", "who scored" or "and the table?"
resolve to what was just discussed. In memory only, 30-minute sliding expiry, and it stores
nothing personal - no question text, no user identity, just team ids/names, one match record and
a player name. The conversation id is an opaque random string made by the browser.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field

TTL_SECONDS = 30 * 60
MAX_CONVERSATIONS = 2000
_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


@dataclass
class Context:
    teams: list[dict] = field(default_factory=list)  # [{"id", "name"}], up to 2
    match: dict | None = None  # the last match record discussed (our own match_dict)
    player: str | None = None
    expires_at: float = 0.0

    @property
    def league_code(self) -> str | None:
        return self.match["league_code"] if self.match else None


_store: dict[str, Context] = {}
_lock = threading.Lock()


def _now() -> float:
    return time.monotonic()


def valid_id(conversation_id: str | None) -> bool:
    return bool(conversation_id and _ID.match(conversation_id))


def _prune(now: float) -> None:
    for key in [k for k, c in _store.items() if c.expires_at <= now]:
        del _store[key]
    while len(_store) > MAX_CONVERSATIONS:
        del _store[min(_store, key=lambda k: _store[k].expires_at)]


def get(conversation_id: str | None) -> Context | None:
    if not valid_id(conversation_id):
        return None
    with _lock:
        now = _now()
        _prune(now)
        return _store.get(conversation_id)  # type: ignore[arg-type]


def remember(
    conversation_id: str | None, *, teams: list[dict] | None = None, match: dict | None = None,
    player: str | None = None, reset: bool = False,
) -> None:
    """Update the context. reset=True starts a new topic (the question named its own entities), so
    a stale match/player from the previous topic is dropped rather than carried over."""
    if not valid_id(conversation_id):
        return
    with _lock:
        now = _now()
        _prune(now)
        ctx = Context() if reset or conversation_id not in _store else _store[conversation_id]  # type: ignore[index]
        if teams:
            ctx.teams = [{"id": t["id"], "name": t["name"]} for t in teams[:2]]
        if match is not None:
            ctx.match = {
                "id": match["id"], "league_code": match["league_code"], "date": match["date"], "status": match["status"],
                "home_team": {"id": match["home_team"]["id"], "name": match["home_team"]["name"]},
                "away_team": {"id": match["away_team"]["id"], "name": match["away_team"]["name"]},
            }
        if player:
            ctx.player = player
        ctx.expires_at = now + TTL_SECONDS
        _store[conversation_id] = ctx  # type: ignore[index]


def clear() -> None:
    with _lock:
        _store.clear()
