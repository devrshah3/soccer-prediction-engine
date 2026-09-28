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
import re

from sqlalchemy.orm import Session

from ..models import League
from ..serialize import match_dict
from . import cache, conversation, fallback, gemini_client, quota, text_format, tools, wikipedia, youtube
from .entities import (
    Entity,
    find_entities,
    find_players,
    find_teams,
    mentions_entity,
    normalize,
    team_title_variants,
)
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
    plain_text = f"From Wikipedia ({wiki['title']}): {text_format.first_sentences(wiki['extract'], 2)}\n\nSource: {wiki['url']}"

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


def _video_answer(session: Session, question: str, teams: list[dict]) -> dict:
    """Video/highlights questions never touch Wikipedia or Gemini. The match comes from OUR
    records (the latest finished one for the named teams), the search is built from that record,
    and only a validated official-channel video is ever offered."""
    if not teams:
        return _plain(fallback.ASK_WHICH_MATCH)
    match = tools.latest_finished_match(session, [t["id"] for t in teams])
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


_PRONOUN = re.compile(r"\b(he|his|him|she|her|they|their|them|the club|the team|that player|that team)\b", re.IGNORECASE)


def _context_entities(session: Session, ctx: conversation.Context) -> list[Entity]:
    out = [Entity("player", ctx.player, (normalize(ctx.player),))] if ctx.player else []
    for t in ctx.teams:
        out.append(Entity("team", t["name"], tuple(team_title_variants(session, t["id"])) or (normalize(t["name"]),)))
    return out


def _remember(conversation_id: str | None, named: list[dict], teams: list[dict], players: list[str], sources: list[dict]) -> None:
    """Record what was just discussed. Naming a team/player starts a new topic (reset); a pure
    follow-up keeps the topic and only updates what the answer adds."""
    match = None
    for src in sources:
        data = src.get("data") if isinstance(src, dict) else None
        if src.get("type") == "kickcast_match" and data:
            match = data
        elif src.get("type") == "kickcast_prediction" and data and data.get("match"):
            match = data["match"]
    if match and not named:
        teams = [match["home_team"], match["away_team"]]
    conversation.remember(
        conversation_id, teams=teams, match=match, player=players[0] if players else None,
        reset=bool(named or players),
    )


def _gated_wikipedia(session: Session, question: str, ctx: conversation.Context | None = None) -> dict | None:
    """Wikipedia for general history/context only, and only with a relevance gate: the search is
    built from RECOGNISED entities (team, player, competition, year) - never the raw sentence, so
    filler like "give em" or "I wanna" can't steer it - and the article is accepted only if its
    title or lead mentions one of them. Anything else is treated as unknown."""
    entities = find_entities(session, question)
    if not any(e.kind != "year" for e in entities) and ctx and _PRONOUN.search(question):
        # "tell me about his history": the entity is whoever was last discussed
        entities = _context_entities(session, ctx) + entities
    if not any(e.kind != "year" for e in entities):
        return None  # nothing football-shaped recognised: don't search at all
    wiki = wikipedia.lookup(session, " ".join(e.display for e in entities))
    if wiki is None or not wiki.get("found"):
        return None
    lead = wiki["extract"].strip().split("\n\n", 1)[0][:600]
    if not mentions_entity(f"{wiki['title']} {lead}", entities):
        return None
    return wiki


def ask(session: Session, question: str, conversation_id: str | None = None) -> dict:
    question = question.strip()
    if not question:
        return {"text": "Ask me something about a team, fixture, table, or prediction.", "sources": [], "mode": "invalid", "cached": False}

    intent = classify(question)
    ctx = conversation.get(conversation_id)
    named = find_teams(session, question)
    # A follow-up ("a video link", "who scored", "and the table?") names no team: it means whatever
    # was last discussed in this conversation. Naming a team starts a new topic.
    teams = named or (ctx.teams if ctx else [])
    players = find_players(session, question)

    # 1. Video/highlights: its own path, decided before any lookup.
    if intent is Intent.VIDEO:
        result = _video_answer(session, question, teams)
        if named or players or result["sources"]:
            _remember(conversation_id, named, teams, players, result["sources"])
        return result

    # 2. A DB question (prediction, table, top scorers, result, next match): facts from our own
    # tools first, always; Gemini only rephrases those facts when it is usable.
    if intent in DB_INTENTS:
        # "and the table?" after a match means that match's LEAGUE table, not one team's position:
        # only a team named in THIS question gets a team-position answer.
        asked = named if intent is Intent.TABLE else teams
        fb = fallback.answer(session, question, intent, asked, ctx.league_code if ctx and not named else None)
        if fb["found"] or named or players:
            _remember(conversation_id, named, teams, players, fb["sources"])
        if not fb["found"]:
            # Nothing to phrase - an honest "not on record" is already the whole answer.
            return _plain(fb["text"], fb["sources"])
        return _db_lookup_answer(session, question, fb)

    # 3. General history/context: Wikipedia (free, no quota) before any Gemini call.
    if intent is Intent.HISTORY:
        wiki = _gated_wikipedia(session, question, ctx)
        if wiki is not None:
            wiki_answer = _wikipedia_answer(session, question, wiki)
            if wiki_answer is not None:
                return wiki_answer

    # 4. Open-ended reasoning (e.g. "who is the best young player right now") - only when Gemini
    # is actually usable; cached by the raw question since it costs quota.
    if _gemini_usable(session):
        cached = cache.get_cached(session, question)
        if cached is not None:
            return {**cached, "cached": True}

        gemini_result = gemini_client.ask_gemini(session, question)
        if gemini_result is not None:
            if _all_tools_missed(gemini_result["sources"]) or _looks_like_decline(gemini_result["text"]):
                outside_db = gemini_client.ask_gemini_with_search(session, question)
                if outside_db is not None:
                    gemini_result = outside_db
            answer = {"text": text_format.strip_markdown(gemini_result["text"]), "sources": gemini_result["sources"], "mode": "gemini+db"}
            cache.set_cached(session, question, answer)  # only Gemini answers are cached - they cost quota
            return {**answer, "cached": False}

    fb = fallback.unknown_reply()
    return _plain(fb["text"], fb["sources"], mode="fallback")
