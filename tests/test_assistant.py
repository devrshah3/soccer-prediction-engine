from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.assistant import cache, fallback, quota, service
from kickcast_api.assistant import tools as assistant_tools
from kickcast_api.models import Base, League, Match, Team


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'assistant.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(League(code="test.1", name="Test League", country="Testland", kind="domestic_league"))
    for i in range(8):
        s.add(Team(id=f"team-{i}", name=f"Rovers {i}" if i else "Ridgeway United", country="Testland"))
    s.commit()
    d = date(2024, 8, 1)
    for match_id in range(1, 25):
        i = match_id - 1
        h, a = i % 8, (i + 1) % 8
        s.add(
            Match(
                league_code="test.1", season="2024-25", date=d, kickoff=None,
                home_team_id=f"team-{h}", away_team_id=f"team-{a}",
                home_goals=match_id % 4, away_goals=(match_id + 1) % 3,
                status="finished", round=f"Matchday {match_id}", neutral=False,
                source="synthetic", source_id=f"synthetic:{match_id}",
            )
        )
        d += timedelta(days=7)
    s.add(
        Match(
            league_code="test.1", season="2024-25", date=d, kickoff=None,
            home_team_id="team-0", away_team_id="team-1", home_goals=None, away_goals=None,
            status="scheduled", round="Matchday 25", neutral=False,
            source="synthetic", source_id="synthetic:upcoming",
        )
    )
    s.commit()
    return s


# ---------------------------------------------------------------- tools.py


def test_resolve_team_matches_substring(session):
    hits = assistant_tools.resolve_team(session, "Ridgeway")
    assert hits["found"] is True
    assert any(h["id"] == "team-0" for h in hits["teams"])


def test_team_next_match_found_and_not_found(session):
    r = assistant_tools.team_next_match(session, "team-0")
    assert r["found"] is True
    assert r["match"]["home_team"]["id"] == "team-0"
    r2 = assistant_tools.team_next_match(session, "team-7")  # never home/away in the scheduled fixture
    assert r2["found"] is False


def test_league_standings_top_and_position(session):
    r = assistant_tools.league_standings_top(session, "test.1", n=3)
    assert r["found"] is True
    assert len(r["table"]) == 3
    pos = assistant_tools.team_league_position(session, "team-0")
    assert pos["found"] is True
    assert pos["league_code"] == "test.1"


def test_match_prediction_lookup_real_numbers(session):
    r = assistant_tools.match_prediction_lookup(session, "team-0", "team-1")
    assert r["found"] is True
    probs = r["prediction"]["probabilities"]
    assert abs(sum(probs.values()) - 1) < 1e-6


def test_tool_never_reports_found_for_unknown_team(session):
    r = assistant_tools.team_next_match(session, "definitely-not-a-real-team-id")
    assert r["found"] is False


# ---------------------------------------------------------------- fallback.py


def test_fallback_answers_next_match_from_real_data(session):
    r = fallback.answer(session, "When does Ridgeway United play next?")
    assert r["found"] is True
    assert "Ridgeway United" in r["text"]


def test_fallback_declines_unmatched_question_honestly():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    r = fallback.answer(s, "What's the meaning of life?")
    assert r["found"] is False
    assert "only answer from our own database" in r["text"].lower()


def test_fallback_declines_specific_past_year_instead_of_guessing_most_recent_match(session):
    """Regression for a real bug: 'scored' matched _RESULT_WORDS's 'score' substring, so
    "Who scored the winning goal for Ridgeway United in the 2016 Champions League final?"
    silently returned Ridgeway United's most recent (unrelated, 2024) synthetic result as
    if it answered the question about 2016 - a confident-looking wrong answer, exactly
    what the "never invent a fact" rule exists to prevent. The fallback tools only ever
    look up next/most-recent/current, never a specific year, so any other year must decline."""
    r = fallback.answer(
        session,
        "Who scored the winning goal for Ridgeway United in the 2016 Champions League final?",
    )
    assert r["found"] is False
    assert "2016" in r["text"]
    assert r["sources"] == []


def test_fallback_current_season_year_still_answers_normally(session):
    from datetime import UTC, datetime

    current_year = datetime.now(UTC).year
    r = fallback.answer(session, f"When does Ridgeway United play next in {current_year}?")
    assert r["found"] is True


def test_fallback_never_fabricates_result_for_team_with_no_finished_matches(session):
    session.add(Team(id="team-new", name="Brand New FC", country="Testland"))
    session.commit()
    r = fallback.answer(session, "What was the score for Brand New FC?")
    assert r["found"] is False
    assert r["sources"] == []


# ---------------------------------------------------------------- cache.py


def test_cache_round_trip(session):
    assert cache.get_cached(session, "hello?") is None
    cache.set_cached(session, "hello?", {"text": "hi", "sources": [], "mode": "gemini"})
    got = cache.get_cached(session, "hello?")
    assert got["text"] == "hi"


def test_cache_key_is_normalized(session):
    cache.set_cached(session, "  What TIME  is it? ", {"text": "x", "sources": [], "mode": "gemini"})
    assert cache.get_cached(session, "what time is it?") is not None


# ---------------------------------------------------------------- quota.py


def test_quota_decrements_and_records(session):
    limit_before = quota.gemini_quota_remaining(session)
    quota.record_gemini_call(session)
    assert quota.gemini_quota_remaining(session) == limit_before - 1


# ---------------------------------------------------------------- service.py orchestration


def test_service_uses_db_fallback_when_no_gemini_key(session, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = service.ask(session, "When does Ridgeway United play next?")
    assert result["mode"] == "db_fallback"
    assert "Ridgeway United" in result["text"]


def test_service_never_fabricates_when_gemini_and_search_both_miss(session, monkeypatch):
    """The exact scenario the brief calls out: a question with nothing in our DB and no
    search result. We can't control what a REAL Gemini model would say (that's a live-API
    concern, documented in gemini_client.py), but we CAN verify our harness passes through
    an honest "don't know" rather than inventing anything, and never calls search when the
    mocked tool call already came back not-found without falling through correctly."""

    def fake_ask_gemini(sess, question):
        return {
            "text": "I don't have that in my database and couldn't find it.",
            "sources": [{"type": "kickcast_tool", "tool": "team_next_match", "args": {"team_id": "ghost"},
                         "result": {"found": False}}],
            "used_search": False,
        }

    def fake_ask_gemini_with_search(sess, question):
        return None  # simulates: search grounding also found nothing

    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini", fake_ask_gemini)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_search", fake_ask_gemini_with_search)
    monkeypatch.setattr(service.wikipedia, "lookup", lambda s, q: None)  # simulates: Wikipedia also has nothing

    result = service.ask(session, "What happened in a match that doesn't exist?")
    assert result["mode"] == "gemini"
    assert "don't have" in result["text"] or "couldn't find" in result["text"]
    assert not any(w in result["text"].lower() for w in ("scored", "final score was", "the result was"))


def test_service_augments_with_search_when_db_tools_miss(session, monkeypatch):
    def fake_ask_gemini(sess, question):
        return {
            "text": "not found in db",
            "sources": [{"type": "kickcast_tool", "tool": "resolve_team", "args": {}, "result": {"found": False}}],
            "used_search": False,
        }

    def fake_ask_gemini_with_search(sess, question):
        return {"text": "Found via search: real news answer.", "sources": [{"title": "Example", "url": "https://example.com"}], "used_search": True}

    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini", fake_ask_gemini)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_search", fake_ask_gemini_with_search)

    result = service.ask(session, "some question not in our db")
    assert result["text"] == "Found via search: real news answer."
    assert result["sources"][0]["url"] == "https://example.com"


def test_service_uses_wikipedia_when_search_grounding_unavailable(session, monkeypatch):
    """Search grounding is genuinely 429'd on the free tier this project uses (see
    gemini_client.py) - this is the real substitute path. Verify it only ever states
    what the (mocked) Wikipedia-grounded call actually said, and cites Wikipedia."""

    def fake_ask_gemini(sess, question):
        return {"text": "not in our db", "sources": [{"type": "kickcast_tool", "tool": "resolve_team", "args": {}, "result": {"found": False}}], "used_search": False}

    def fake_lookup(sess, query):
        return {"found": True, "title": "2016 UEFA Champions League final", "url": "https://en.wikipedia.org/wiki/2016_UEFA_Champions_League_final", "extract": "Real Madrid won 5-3 on penalties.", "source": "Wikipedia (CC BY-SA)"}

    def fake_context(sess, question, context, label):
        assert "Real Madrid won 5-3 on penalties." in context
        return {"text": "Real Madrid won on penalties, per the Wikipedia article.", "used_search": False}

    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini", fake_ask_gemini)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_search", lambda s, q: None)
    monkeypatch.setattr(service.wikipedia, "lookup", fake_lookup)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_context", fake_context)

    result = service.ask(session, "Who won the 2016 Champions League final?")
    assert result["text"] == "Real Madrid won on penalties, per the Wikipedia article."
    wiki_sources = [s for s in result["sources"] if s["type"] == "wikipedia"]
    assert len(wiki_sources) == 1
    assert wiki_sources[0]["license"] == "Wikipedia (CC BY-SA)"


def test_service_attaches_video_link_only_when_asked(session, monkeypatch):
    calls = []

    def fake_ask_gemini(sess, question):
        return {"text": "not in our db", "sources": [], "used_search": False}

    def fake_lookup(sess, query):
        return {"found": True, "title": "2016 UEFA Champions League final", "url": "https://en.wikipedia.org/wiki/x", "extract": "...", "source": "Wikipedia (CC BY-SA)"}

    def fake_context(sess, question, context, label):
        return {"text": "answer text", "used_search": False}

    def fake_highlight(sess, query, channel=None):
        calls.append((query, channel))
        return {"title": "2016 UCL Final Highlights", "url": "https://youtube.com/watch?v=abc", "channel": "UEFA"}

    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini", fake_ask_gemini)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_search", lambda s, q: None)
    monkeypatch.setattr(service.wikipedia, "lookup", fake_lookup)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_context", fake_context)
    monkeypatch.setattr(service.youtube, "find_official_highlight", fake_highlight)

    result = service.ask(session, "Who scored in the 2016 Champions League final? Give me a link to watch it.")
    youtube_sources = [s for s in result["sources"] if s["type"] == "youtube"]
    assert len(youtube_sources) == 1
    assert youtube_sources[0]["url"] == "https://youtube.com/watch?v=abc"
    assert calls[0][1] == "UEFA"  # channel guessed from "Champions League" in the wikipedia title

    calls.clear()
    result2 = service.ask(session, "Who scored in the 2016 Champions League final?")  # no "watch"/"link"
    assert not any(s["type"] == "youtube" for s in result2["sources"])
    assert calls == []


def test_service_caches_gemini_answers_but_not_db_fallback(session, monkeypatch):
    call_count = {"n": 0}

    def fake_ask_gemini(sess, question):
        call_count["n"] += 1
        return {"text": "cached answer", "sources": [], "used_search": False}

    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini", fake_ask_gemini)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_search", lambda s, q: None)
    monkeypatch.setattr(service.wikipedia, "lookup", lambda s, q: None)

    r1 = service.ask(session, "unique question for caching test")
    r2 = service.ask(session, "unique question for caching test")
    assert call_count["n"] == 1  # second call served from cache
    assert r1["text"] == r2["text"]
    assert r2["cached"] is True
