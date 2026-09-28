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

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import League, Match
from ..serialize import match_dict
from . import cache, fallback, gemini_client, quota, text_format, wikipedia, youtube
from .entities import find_teams
from .intent import DB_INTENTS, Intent, classify

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

    composed = gemini_client.ask_gemini_with_context(session, question, facts, "Soccer Prediction Engine database facts")
    if composed is not None and not _looks_like_decline(composed["text"]):
        answer = {"text": text_format.strip_markdown(composed["text"]), "sources": sources, "mode": "gemini+db"}
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
    cache.set_cached(session, cache_key, answer)
    return {**answer, "cached": False}


NO_VERIFIED_LINK = "I don't have a verified official highlights link for that match."


def _gemini_usable(session: Session) -> bool:
    return gemini_client.available() and quota.gemini_quota_remaining(session) > 0


def _plain(text: str, sources: list[dict] | None = None, mode: str = "db") -> dict:
    return {"text": text_format.strip_markdown(text), "sources": sources or [], "mode": mode, "cached": False}


def _latest_finished_match(session: Session, team_ids: list[str]) -> Match | None:
    """The most recent finished match between the two teams (or, given one team, that team's)."""
    q = session.query(Match).filter(Match.status == "finished")
    if len(team_ids) >= 2:
        a, b = team_ids[0], team_ids[1]
        q = q.filter(
            or_(
                (Match.home_team_id == a) & (Match.away_team_id == b),
                (Match.home_team_id == b) & (Match.away_team_id == a),
            )
        )
    else:
        q = q.filter(or_(Match.home_team_id == team_ids[0], Match.away_team_id == team_ids[0]))
    return q.order_by(Match.date.desc(), Match.kickoff.desc()).first()


def _video_answer(session: Session, question: str) -> dict:
    """Video/highlights questions never touch Wikipedia or Gemini. The match comes from OUR
    records (the latest finished one for the named teams), the search is built from that record,
    and only a validated official-channel video is ever offered."""
    teams = find_teams(session, question)
    if not teams:
        return _plain(fallback.ASK_WHICH_MATCH)
    match = _latest_finished_match(session, [t["id"] for t in teams])
    if match is None:
        names = " and ".join(t["name"] for t in teams)
        return _plain(f"I don't have a finished match on record for {names}, so there are no highlights to look for.")

    m = match_dict(session, match)
    league = session.get(League, match.league_code)
    when = match.date.strftime("%a %b %d, %Y").replace(" 0", " ")
    head = (
        f"{m['home_team']['name']} {m['home_goals']}-{m['away_goals']} {m['away_team']['name']}, {when}"
        + (f" ({league.name})" if league else "")
        + "."
    )
    sources: list[dict] = [{"type": "kickcast_match", "data": m}]

    found = youtube.find_match_highlight(session, match)
    status = found["status"]
    if status == "found":
        video = found["video"]
        sources.append({"type": "youtube", "title": video["title"], "url": video["url"], "channel": video["channel"]})
        return _plain(f"{head} Official highlights ({video['channel']}): {video['title']} - {video['url']}", sources)
    if status == "none":
        return _plain(f"{head} No verified official highlights link was found for that match.", sources)
    if status == "quota":
        return _plain(f"{head} I've used today's allowance for checking YouTube, so I can't look for a link right now.", sources)
    if status == "error":
        return _plain(f"{head} I couldn't reach YouTube just now, so I can't offer a link.", sources)
    return _plain(f"{head} {NO_VERIFIED_LINK}", sources)  # no verified channel / no API key


def ask(session: Session, question: str) -> dict:
    question = question.strip()
    if not question:
        return {"text": "Ask me something about a team, fixture, table, or prediction.", "sources": [], "mode": "invalid", "cached": False}

    intent = classify(question)

    # 1. Video/highlights: its own path, decided before any lookup.
    if intent is Intent.VIDEO:
        return _video_answer(session, question)

    # 2. A DB question (prediction, table, top scorers, result, next match): facts from our own
    # tools first, always; Gemini only rephrases those facts when it is usable.
    if intent in DB_INTENTS:
        fb = fallback.answer(session, question, intent)
        if not fb["found"]:
            # Nothing to phrase - an honest "not on record" is already the whole answer.
            return _plain(fb["text"], fb["sources"])
        return _db_lookup_answer(session, question, fb)

    # 3. General history/context: Wikipedia (free, no quota) before any Gemini call.
    if intent is Intent.HISTORY:
        wiki = wikipedia.lookup(session, question)
        if wiki is not None and wiki.get("found"):
            wiki_answer = _wikipedia_answer(session, question, wiki)
            if wiki_answer is not None:
                return wiki_answer

    # 4. Open-ended reasoning (e.g. "who is the best young player right now") - only when Gemini
    # is actually usable; cached by the raw question since it costs quota.
    if _gemini_usable(session):
        cached = cache.get_cached(session, question)
        if cached is not None:
            return {**cached, "cached": True}

        result = gemini_client.ask_gemini(session, question)
        if result is not None:
            if _all_tools_missed(result["sources"]) or _looks_like_decline(result["text"]):
                outside_db = gemini_client.ask_gemini_with_search(session, question)
                if outside_db is not None:
                    result = outside_db
            answer = {"text": text_format.strip_markdown(result["text"]), "sources": result["sources"], "mode": "gemini+db"}
            cache.set_cached(session, question, answer)  # only Gemini answers are cached - they cost quota
            return {**answer, "cached": False}

    fb = fallback.unknown_reply()
    return _plain(fb["text"], fb["sources"], mode="fallback")
