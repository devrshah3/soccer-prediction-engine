"""Deterministic question classification - works with Gemini off. Runs BEFORE any lookup so a
"video" question can never fall into the Wikipedia/DB paths, and a "prediction" question can
never be treated as a generic article search.

Priority order matters: video first (a question about highlights of a match is not a
"match lookup" even though it names teams), then prediction, table, top scorers, result,
match lookup, history; anything else is unknown.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import Enum


class Intent(str, Enum):
    VIDEO = "video"
    PREDICTION = "prediction"
    TABLE = "table"
    TOP_SCORERS = "top_scorers"
    RESULT = "result"
    MATCH_LOOKUP = "match_lookup"
    HISTORY = "history"
    UNKNOWN = "unknown"


DB_INTENTS = frozenset({Intent.PREDICTION, Intent.TABLE, Intent.TOP_SCORERS, Intent.RESULT, Intent.MATCH_LOOKUP})

_VIDEO = re.compile(r"\b(highlights?|videos?|watch|clips?|replay|replays|goal video|goals video)\b")
_PREDICTION = re.compile(r"\b(predict\w*|odds|chances?|probabilit\w+|who will win|who'?s going to win|favou?rites?)\b")
_TABLE = re.compile(r"\b(table|standings?|position|top of|leading|first place|where are|league table|points)\b")
_TOP_SCORERS = re.compile(r"\b(top scorers?|golden boot|leading scorers?|most goals|goal ?scoring charts?|top goal ?scorers?)\b")
_RESULT = re.compile(r"\b(scores?|results?|beat|lost|won|lose|win against|who scored|scorers?|final score|how did .* (?:do|get on))\b")
_MATCH = re.compile(r"\b(next|when|upcoming|fixtures?|play|playing|kick ?off|schedule|plays)\b")
_HISTORY = re.compile(
    r"\b(history|founded|why|how did|how many times|who won|who is|who was|what is|what was|tell me about|"
    r"when was|biggest|record|legend|greatest|titles?|trophies|stadium|nickname|manager|coach)\b"
)
_HISTORY_STRONG = re.compile(r"\b(when was|founded|history of|tell me about|who is|who was|nickname|biggest win)\b")
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")


def references_other_season(question: str, now: datetime | None = None) -> str | None:
    """A year outside the current season's window (this year +/- 1). The DB tools only ever
    answer current/next/most-recent, so such a question is history, not a lookup."""
    now = now or datetime.now(UTC)
    current = {now.year - 1, now.year, now.year + 1}
    for m in _YEAR.finditer(question):
        if int(m.group(1)) not in current:
            return m.group(1)
    return None


def classify(question: str, now: datetime | None = None) -> Intent:
    q = " ".join(question.lower().split())
    if not q:
        return Intent.UNKNOWN
    if _VIDEO.search(q):
        return Intent.VIDEO
    other_year = references_other_season(q, now) is not None
    for pattern, intent in (
        (_PREDICTION, Intent.PREDICTION),
        (_TOP_SCORERS, Intent.TOP_SCORERS),
        (_TABLE, Intent.TABLE),
        (_HISTORY_STRONG, Intent.HISTORY),
        (_RESULT, Intent.RESULT),
        (_MATCH, Intent.MATCH_LOOKUP),
    ):
        if pattern.search(q):
            # "what was the score of the 2016 final": needs a write-up, not our current-season lookup
            return Intent.HISTORY if other_year else intent
    if _HISTORY.search(q) or other_year:
        return Intent.HISTORY
    return Intent.UNKNOWN
