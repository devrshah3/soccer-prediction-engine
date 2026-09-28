"""Top-level assistant orchestration (B1-B5 in MORNING_REPORT.md): DB facts first (or
Wikipedia for anything that isn't a plain lookup), then - quota and config permitting -
Gemini phrases those facts into a natural answer with at most one grounded extra
observation. Gemini is never allowed to state a fact we didn't already look up ourselves.
If Gemini is disabled, unavailable, or the call fails, the plain DB template (or the raw
Wikipedia extract + link) is used instead, with a note that AI phrasing is paused. This is
the only entry point routes/assistant.py should call.

Modes returned: "db" (DB facts, plain template - no Gemini), "gemini+db" (DB facts phrased
by Gemini, or the older DB-tools-plus-reasoning path for a question that isn't a plain
lookup), "wikipedia+gemini" (Wikipedia facts phrased by Gemini), "fallback" (nothing
matched a lookup shape and Wikipedia had nothing usable either, or a Wikipedia extract is
shown as-is because Gemini couldn't phrase it).
"""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from . import cache, fallback, gemini_client, text_format, wikipedia, youtube

_VIDEO_WORDS = ("watch", "video", "highlight", "highlights", "clip", "link")
_CHANNEL_HINTS = (
    ("champions league", "UEFA"), ("europa league", "UEFA"), ("uefa", "UEFA"),
    ("nations league", "UEFA"), ("premier league", "Premier League"),
    ("la liga", "LaLiga"), ("laliga", "LaLiga"), ("serie a", "Serie A"),
    ("bundesliga", "Bundesliga"), ("ligue 1", "Ligue 1"),
)

AI_PAUSED_NOTE = " (AI phrasing paused for today.)"


def _all_tools_missed(sources: list[dict]) -> bool:
    tool_results = [s for s in sources if s.get("type") == "kickcast_tool"]
    if not tool_results:
        return True  # no tool was even called - question is probably outside our DB
    return all(isinstance(s.get("result"), dict) and s["result"].get("found") is False for s in tool_results)


# Phrases the SYSTEM_INSTRUCTION explicitly primes Gemini to use ("say plainly that you
# don't know rather than guessing") when its tool calls found data, but not the RIGHT
# data - e.g. resolve_team + team_recent_results both succeed (found=True) for a team,
# but the specific match asked about (an old European final, say) isn't in our DB at
# all. _all_tools_missed alone can't catch this (every individual tool call DID find
# something), so also check the model's own final answer for a decline.
_DECLINE_PHRASES = (
    "don't know", "do not know", "don't have", "do not have", "cannot answer",
    "can't answer", "no access", "not available in", "couldn't find", "could not find",
    "not in our database", "not in my database", "outside our database", "no data",
)


def _looks_like_decline(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in _DECLINE_PHRASES)


def _guess_channel(text: str) -> str | None:
    t = text.lower()
    for hint, channel in _CHANNEL_HINTS:
        if hint in t:
            return channel
    return None


def _maybe_attach_video(session: Session, question: str, result: dict) -> dict:
    """Only for questions that actually ask for one ("give me a link to watch it" etc.) -
    YouTube is never used as a source of facts, only to find a link for an answer
    already established from a tool or Wikipedia."""
    if not any(w in question.lower() for w in _VIDEO_WORDS):
        return result
    wiki_sources = [s for s in result["sources"] if s.get("type") == "wikipedia"]
    topic = wiki_sources[0]["title"] if wiki_sources else question
    channel = _guess_channel(topic)
    video = youtube.find_official_highlight(session, f"{topic} highlights", channel=channel)
    if video is None:
        return result
    return {**result, "sources": [*result["sources"], {"type": "youtube", **video}]}


def _fact_cache_key(question: str, facts: str) -> str:
    """Content-addressed: the key is the question PLUS the exact facts it was answered
    from, so if the underlying data changes (a match gets rescheduled, a new result comes
    in), fallback.answer()/wikipedia.lookup() naturally produce different facts text next
    time - a different key, a fresh cache miss, no explicit invalidation needed."""
    return hashlib.sha256(f"{question.strip().lower()}\x00{facts}".encode()).hexdigest()


def _gemini_lookup_ready() -> bool:
    return gemini_client.gemini_for_lookups_enabled() and gemini_client.available()


def _db_lookup_answer(session: Session, question: str, fb: dict) -> dict:
    """B1: fb["facts"] is a plain-language write-up of exactly what fallback.answer()
    looked up - handed to Gemini as strict grounding (it may phrase it naturally and add
    at most one observation already present in the facts, e.g. the opponent's form or our
    prediction, but must never state anything beyond them). Falls back to the plain
    template - B2 - if Gemini is disabled, unavailable, or the call fails."""
    facts, plain_text, sources = fb["facts"], fb["text"], fb["sources"]
    if not facts or not _gemini_lookup_ready():
        return {"text": text_format.strip_markdown(plain_text), "sources": sources, "mode": "db", "cached": False}

    cache_key = _fact_cache_key(question, facts)
    cached = cache.get_cached(session, cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    composed = gemini_client.ask_gemini_with_context(session, question, facts, "KickCast database facts")
    if composed is not None and not _looks_like_decline(composed["text"]):
        answer = {"text": text_format.strip_markdown(composed["text"]), "sources": sources, "mode": "gemini+db"}
        answer = _maybe_attach_video(session, question, answer)
        cache.set_cached(session, cache_key, answer)
        return {**answer, "cached": False}

    # composed is None (quota exhausted or the call failed) - Gemini WAS expected to run,
    # so this is B2's "paused" case, not a silent fallback.
    return {"text": text_format.strip_markdown(plain_text + AI_PAUSED_NOTE), "sources": sources, "mode": "db", "cached": False}


def _wikipedia_answer(session: Session, question: str, wiki: dict) -> dict | None:
    """Returns None specifically when Gemini looked at this Wikipedia article and
    concluded it doesn't answer the question (a search-relevance miss, not a real "nothing
    exists" - see wikipedia.py's stopword-stripping note) - callers should treat that as
    "Wikipedia had nothing usable" and fall through to the broader reasoning path, not
    surface a decline sourced from the wrong article."""
    sources = [{"type": "wikipedia", "title": wiki["title"], "url": wiki["url"], "license": wiki["source"]}]
    facts = f"Wikipedia article: {wiki['title']}\n\n{wiki['extract']}"
    plain_text = f"From Wikipedia ({wiki['title']}): {wiki['extract'][:1000]}\n\nSource: {wiki['url']}"

    if not _gemini_lookup_ready():
        # B2: no AI available/enabled at all - show the extract + link directly, no
        # "paused" note (nothing was interrupted; this is simply how it's configured).
        return {"text": text_format.strip_markdown(plain_text), "sources": sources, "mode": "fallback", "cached": False}

    cache_key = _fact_cache_key(question, facts)
    cached = cache.get_cached(session, cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    composed = gemini_client.ask_gemini_with_context(session, question, facts, f"Wikipedia article: {wiki['title']}")
    if composed is None:
        return {"text": text_format.strip_markdown(plain_text + AI_PAUSED_NOTE), "sources": sources, "mode": "fallback", "cached": False}
    if _looks_like_decline(composed["text"]):
        return None

    answer = {"text": text_format.strip_markdown(composed["text"]), "sources": sources, "mode": "wikipedia+gemini"}
    answer = _maybe_attach_video(session, question, answer)
    cache.set_cached(session, cache_key, answer)
    return {**answer, "cached": False}


def ask(session: Session, question: str) -> dict:
    question = question.strip()
    if not question:
        return {"text": "Ask me something about a team, fixture, table, or prediction.", "sources": [], "mode": "invalid", "cached": False}

    # 1. A plain DB lookup (next match, last result, table position, head-to-head
    # prediction): get the facts from our own tools first, always.
    if fallback.is_simple_lookup(session, question):
        fb = fallback.answer(session, question)
        if not fb["found"]:
            # Nothing to phrase - an honest "not on record" is already the whole answer,
            # and spending a Gemini call to rephrase "I don't have that" adds no value.
            return {"text": text_format.strip_markdown(fb["text"]), "sources": fb["sources"], "mode": "db", "cached": False}
        return _db_lookup_answer(session, question, fb)

    # 2. Not a plain lookup: try Wikipedia facts (free, no quota) before any Gemini call -
    # DB -> Wikipedia -> Gemini, in that order (see MORNING_REPORT.md's prior session,
    # which found this backwards and fixed the ordering).
    wiki = wikipedia.lookup(session, question)
    if wiki is not None and wiki.get("found"):
        wiki_answer = _wikipedia_answer(session, question, wiki)
        if wiki_answer is not None:
            return wiki_answer
        # else: wrong/irrelevant article for this question - fall through below.

    # 3. Genuine open-ended reasoning (e.g. "who is the best young player right now") -
    # the DB-tools-plus-reasoning path. Cached by the raw question (no separate "facts"
    # exist for this path - it's whatever Gemini's own tool-calling turns up).
    if gemini_client.available():
        cached = cache.get_cached(session, question)
        if cached is not None:
            return {**cached, "cached": True}

        result = gemini_client.ask_gemini(session, question)
        if result is not None:
            if _all_tools_missed(result["sources"]) or _looks_like_decline(result["text"]):
                outside_db = gemini_client.ask_gemini_with_search(session, question)
                if outside_db is not None:
                    result = outside_db
            result = _maybe_attach_video(session, question, result)
            answer = {"text": text_format.strip_markdown(result["text"]), "sources": result["sources"], "mode": "gemini+db"}
            cache.set_cached(session, question, answer)  # only Gemini answers are cached - they cost quota
            return {**answer, "cached": False}

    fb = fallback.answer(session, question)
    return {"text": text_format.strip_markdown(fb["text"]), "sources": fb["sources"], "mode": "fallback", "cached": False}
