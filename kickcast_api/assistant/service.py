"""Top-level assistant orchestration: cache -> Gemini (DB tools first; for what the
tools couldn't answer, Google Search grounding if it's ever available on this key, else
Wikipedia - see gemini_client.py's module docstring for why Search grounding is
currently inert) -> DB-only fallback. Also attaches a real official-channel YouTube
highlight link when the question asks for one. This is the only entry point
routes/assistant.py should call.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import cache, fallback, gemini_client, text_format, wikipedia, youtube

_VIDEO_WORDS = ("watch", "video", "highlight", "highlights", "clip", "link")
_CHANNEL_HINTS = (
    ("champions league", "UEFA"), ("europa league", "UEFA"), ("uefa", "UEFA"),
    ("nations league", "UEFA"), ("premier league", "Premier League"),
    ("la liga", "LaLiga"), ("laliga", "LaLiga"), ("serie a", "Serie A"),
    ("bundesliga", "Bundesliga"), ("ligue 1", "Ligue 1"),
)


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


def _try_wikipedia(session: Session, question: str) -> dict | None:
    """Real substitute for Search grounding: look the question up on Wikipedia, then
    have Gemini answer strictly from that extract (never from its own unaided
    knowledge). Returns None if Wikipedia has nothing, or if Gemini's grounded call
    fails - callers must not fabricate an answer in either case."""
    wiki = wikipedia.lookup(session, question)
    if wiki is None or not wiki.get("found"):
        return None
    grounded = gemini_client.ask_gemini_with_context(
        session, question, wiki["extract"], f"Wikipedia article: {wiki['title']}"
    )
    if grounded is None:
        return None
    sources = [{"type": "wikipedia", "title": wiki["title"], "url": wiki["url"], "license": wiki["source"]}]
    return {"text": grounded["text"], "sources": sources, "used_search": False}


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


def ask(session: Session, question: str) -> dict:
    question = question.strip()
    if not question:
        return {"text": "Ask me something about a team, fixture, table, or prediction.", "sources": [], "mode": "invalid", "cached": False}

    cached = cache.get_cached(session, question)
    if cached is not None:
        return {**cached, "cached": True}

    # Route pure DB lookups (next match, last result, table position, head-to-head
    # prediction) straight to the DB with zero Gemini calls: an LLM would just call the
    # same tools.py functions to produce the exact same fact, at the cost of real quota.
    if fallback.is_simple_lookup(session, question):
        fb = fallback.answer(session, question)
        return {"text": text_format.strip_markdown(fb["text"]), "sources": fb["sources"], "mode": "db_lookup", "cached": False}

    if gemini_client.available():
        # DB -> Wikipedia -> Gemini: for everything that isn't a simple lookup (write-ups,
        # historical context, "how did X happen"), try the free Wikipedia source BEFORE
        # spending a Gemini tool-calling round trip that our narrow DB tools can't answer
        # anyway. Only treated as final if it didn't come back a decline (a generic/
        # opinion question can hit a wrong or empty Wikipedia article; in that case fall
        # through to Gemini's own reasoning below instead of surfacing a bad decline).
        wiki = _try_wikipedia(session, question)
        if wiki is not None and not _looks_like_decline(wiki["text"]):
            answer = _maybe_attach_video(session, question, wiki)
            answer = {"text": text_format.strip_markdown(answer["text"]), "sources": answer["sources"], "mode": "gemini"}
            cache.set_cached(session, question, answer)
            return {**answer, "cached": False}

        result = gemini_client.ask_gemini(session, question)
        if result is not None:
            if _all_tools_missed(result["sources"]) or _looks_like_decline(result["text"]):
                outside_db = gemini_client.ask_gemini_with_search(session, question)
                if outside_db is not None:
                    result = outside_db
            result = _maybe_attach_video(session, question, result)
            answer = {"text": text_format.strip_markdown(result["text"]), "sources": result["sources"], "mode": "gemini"}
            cache.set_cached(session, question, answer)  # only Gemini answers are cached - they cost quota
            return {**answer, "cached": False}

    fb = fallback.answer(session, question)
    return {"text": text_format.strip_markdown(fb["text"]), "sources": fb["sources"], "mode": "db_fallback", "cached": False}
