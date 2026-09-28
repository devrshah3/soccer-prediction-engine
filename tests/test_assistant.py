from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.assistant import cache, fallback, quota, service, text_format
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
    assert pos["league_name"] == "Test League"  # the real DB name, never the raw code, in any user-facing text


def test_prediction_sentence_uses_fixture_order_not_question_order(session):
    """Real failure: "Predict Real Madrid vs Barcelona" said "Real Madrid 56%, a draw 21%, and
    Barcelona 24%" while the fixture (and the card) had Barcelona at home with 56%. The
    sentence must take home/away order, venue and probabilities from the fixture record."""
    r = assistant_tools.match_prediction_lookup(session, "team-0", "team-1")
    fixture = r["match"]
    assert fixture["home_team"]["id"] == "team-0"  # Ridgeway United is the home side in the record
    probs = r["prediction"]["probabilities"]

    # The question names the AWAY team first.
    out = fallback.answer(session, "Predict Rovers 1 vs Ridgeway United")
    assert out["found"] is True
    text = out["text"]
    assert text.startswith("Ridgeway United (home) vs Rovers 1 on ")
    assert f"Ridgeway United {probs['home']:.0%}" in text
    assert f"Rovers 1 {probs['away']:.0%}" in text
    assert f"a draw {probs['draw']:.0%}" in text
    assert text.index("Ridgeway United") < text.index("Rovers 1")
    # Same answer whichever order the user typed it.
    assert fallback.answer(session, "Predict Ridgeway United vs Rovers 1")["text"] == text
    # the source card data agrees with the sentence
    assert out["sources"][0]["data"]["match"]["home_team"]["name"] == "Ridgeway United"


def test_prediction_sentence_uses_next_fixture_and_says_when_several_exist(session):
    later = date(2030, 1, 1)
    session.add(Match(
        league_code="test.1", season="2024-25", date=later, kickoff=None, home_team_id="team-1",
        away_team_id="team-0", home_goals=None, away_goals=None, status="scheduled", round="Matchday 40",
        neutral=False, source="synthetic", source_id="synthetic:later-return",
    ))
    session.commit()
    text = fallback.answer(session, "Predict Rovers 1 vs Ridgeway United")["text"]
    assert "the next of 2 scheduled fixtures between them" in text
    assert text.startswith("Ridgeway United (home) vs Rovers 1 on ")  # the EARLIER fixture, not the 2030 one
    assert "2030" not in text


def test_prediction_without_a_fixture_says_it_is_hypothetical(session):
    text = fallback.answer(session, "Predict Rovers 2 vs Rovers 3")["text"]
    assert "no scheduled fixture between Rovers 2 and Rovers 3" in text
    assert "hypothetical with Rovers 2 as the home side" in text


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


def test_fallback_standing_answer_uses_league_name_not_code(session):
    """Item 4 regression: a "where do they stand" answer used to say "in test.1" (the
    internal DB code) instead of the real league name - a raw code must never reach a
    user-facing answer."""
    r = fallback.answer(session, "Where does Ridgeway United stand in the table?")
    assert r["found"] is True
    assert "Test League" in r["text"]
    assert "test.1" not in r["text"]
    assert "test.1" not in r["facts"]


def test_fallback_declines_unmatched_question_honestly():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    r = fallback.answer(s, "What's the meaning of life?")
    assert r["found"] is False
    assert r["text"].startswith("I don't recognize that one.")
    assert r["text"].count('"') == 6  # exactly three quoted example questions


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


# ---------------------------------------------------------------- fallback.is_simple_lookup


def test_is_simple_lookup_true_for_next_match_result_table_and_predict(session):
    assert fallback.is_simple_lookup(session, "When does Ridgeway United play next?") is True
    assert fallback.is_simple_lookup(session, "What was the score for Ridgeway United?") is True
    assert fallback.is_simple_lookup(session, "Where are Ridgeway United in the table?") is True
    assert fallback.is_simple_lookup(session, "Predict Ridgeway United vs Rovers 1") is True


def test_is_simple_lookup_false_for_specific_past_year_even_with_a_result_keyword(session):
    # Contains "won" (_RESULT_WORDS) but names a specific past match by year - needs a
    # real write-up (Wikipedia/Gemini), not our "most recent result" lookup.
    assert fallback.is_simple_lookup(session, "How did Real Madrid win the 2016 Champions League final?") is False


def test_is_simple_lookup_false_for_unrecognized_question():
    assert fallback.is_simple_lookup(None, "Who is the best young player right now?") is False


# ---------------------------------------------------------------- text_format.py


def test_strip_markdown_removes_bold_italic_code_headers_and_links():
    raw = "**October 10, 2026** vs *maybe* - see `docs` for more.\n## Heading\n[KickCast](https://kickcast.example)"
    out = text_format.strip_markdown(raw)
    assert "*" not in out
    assert "#" not in out
    assert "`" not in out
    assert "October 10, 2026" in out
    assert "KickCast (https://kickcast.example)" in out


# ---------------------------------------------------------------- gemini_client.py


def test_humanize_league_codes_strips_raw_code_for_gemini(session):
    """Item 4 regression: a real live call ("Where does Arsenal stand?") produced "...in
    en.1 for the 2026-27 season..." because the raw tool result (with a league_code key)
    was handed to Gemini verbatim. This scrub runs on every tool result before Gemini
    sees it - checked here at any nesting depth, since match_dict-shaped results nest a
    league_code inside other tools' output too."""
    from kickcast_api.assistant import gemini_client

    raw = {"found": True, "league_code": "test.1", "season": "2024-25", "nested": {"league_code": "test.1"}}
    clean = gemini_client._humanize_league_codes(session, raw)
    assert clean["league_name"] == "Test League"
    assert "league_code" not in clean
    assert clean["nested"]["league_name"] == "Test League"
    assert "league_code" not in clean["nested"]


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


def test_service_hybrid_phrases_a_db_lookup_with_gemini_using_only_given_facts(session, monkeypatch):
    """B1: a recognized DB-lookup question is now phrased by Gemini (when available/
    enabled), grounded strictly on the facts fallback.answer() already looked up -
    verified here by asserting the exact facts string reaches ask_gemini_with_context,
    and that ask_gemini (the free-form tool-calling path) is never touched for it."""
    seen = {}

    def fake_context(sess, question, context, label):
        seen["context"] = context
        seen["label"] = label
        return {"text": "Ridgeway United host Rovers 1 next.", "used_search": False}

    def _must_not_be_called(sess, question):
        raise AssertionError("ask_gemini (tool-calling) should not run for a plain DB lookup")

    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_context", fake_context)
    monkeypatch.setattr(service.gemini_client, "ask_gemini", _must_not_be_called)

    result = service.ask(session, "When does Ridgeway United play next?")
    assert result["mode"] == "gemini+db"
    assert result["text"] == "Ridgeway United host Rovers 1 next."
    assert "Ridgeway United's next match" in seen["context"]
    assert seen["label"] == "Soccer Prediction Engine database facts"


def test_service_db_lookup_falls_back_to_plain_template_when_gemini_disabled_for_lookups(session, monkeypatch):
    """B3: ASSISTANT_GEMINI_FOR_LOOKUPS=false must skip Gemini for a lookup even though a
    key is configured and available - mode "db", plain template, no "paused" note (this
    is an intentional setting, not an outage)."""

    def _must_not_be_called(*a, **k):
        raise AssertionError("Gemini must not be called when ASSISTANT_GEMINI_FOR_LOOKUPS=false")

    monkeypatch.setenv("ASSISTANT_GEMINI_FOR_LOOKUPS", "false")
    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_context", _must_not_be_called)

    result = service.ask(session, "When does Ridgeway United play next?")
    assert result["mode"] == "db"
    assert "Ridgeway United" in result["text"]
    assert "paused" not in result["text"].lower()


def test_service_db_lookup_shows_paused_note_when_gemini_call_fails(session, monkeypatch):
    """B2: Gemini is enabled and available but the call itself fails (or quota is
    exhausted - ask_gemini_with_context returns None either way) - answer from the plain
    template, with the "AI phrasing paused" note, mode stays "db"."""
    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_context", lambda *a, **k: None)

    result = service.ask(session, "When does Ridgeway United play next?")
    assert result["mode"] == "db"
    assert "Ridgeway United" in result["text"]
    assert "AI phrasing paused for today" in result["text"]


def test_service_db_lookup_answer_is_cached_by_question_plus_facts(session, monkeypatch):
    """B1: repeat questions cost no further Gemini calls - and the cache key includes the
    facts, so it naturally invalidates if the underlying data (and therefore the facts
    string) ever changes, with no explicit invalidation step needed."""
    calls = {"n": 0}

    def fake_context(sess, question, context, label):
        calls["n"] += 1
        return {"text": "Ridgeway United host Rovers 1 next.", "used_search": False}

    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_context", fake_context)

    r1 = service.ask(session, "When does Ridgeway United play next?")
    r2 = service.ask(session, "When does Ridgeway United play next?")
    assert calls["n"] == 1
    assert r1["text"] == r2["text"]
    assert r1["cached"] is False and r2["cached"] is True


def test_service_skips_gemini_for_a_not_found_lookup(session, monkeypatch):
    """A recognized lookup shape with nothing on record (team-7 is never scheduled) is
    already a complete, honest answer - no Gemini call is worth spending on rephrasing
    "I don't have that"."""

    def _must_not_be_called(*a, **k):
        raise AssertionError("Gemini should not be called for a not-found lookup")

    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_context", _must_not_be_called)

    result = service.ask(session, "When does Rovers 7 play next?")
    assert result["mode"] == "db"
    assert "don't have a scheduled next match" in result["text"]


def test_service_uses_fallback_mode_when_no_gemini_key_and_question_is_unrecognized(session, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(service.wikipedia, "lookup", lambda s, q: None)  # Wikipedia also has nothing
    result = service.ask(session, "What's the meaning of life?")
    assert result["mode"] == "fallback"


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
    assert result["mode"] == "gemini+db"
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
    monkeypatch.setattr(service.wikipedia, "lookup", lambda s, q: None)  # simulates: Wikipedia has nothing either

    result = service.ask(session, "some question not in our db")
    assert result["text"] == "Found via search: real news answer."
    assert result["sources"][0]["url"] == "https://example.com"


def test_service_tries_wikipedia_before_gemini_tool_calling(session, monkeypatch):
    """Issue 2.3: the intended order is DB -> Wikipedia -> Gemini. Verify Wikipedia is
    consulted BEFORE gemini_client.ask_gemini (the tool-calling round trip) - not just
    that Wikipedia's answer wins after both were tried - by making ask_gemini blow up if
    it's ever called for a question Wikipedia can already answer. Also proves markdown
    from the (mocked) LLM-composed answer is stripped before it reaches the caller."""

    def _must_not_be_called(sess, question):
        raise AssertionError("ask_gemini (tool-calling) should not run when Wikipedia already answered")

    def fake_lookup(sess, query):
        return {"found": True, "title": "2016 UEFA Champions League final", "url": "https://en.wikipedia.org/wiki/2016_UEFA_Champions_League_final", "extract": "Real Madrid won 5-3 on penalties.", "source": "Wikipedia (CC BY-SA)"}

    def fake_context(sess, question, context, label):
        assert "Real Madrid won 5-3 on penalties." in context
        return {"text": "**Real Madrid** won on penalties, per the Wikipedia article.", "used_search": False}

    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini", _must_not_be_called)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_search", lambda s, q: None)
    monkeypatch.setattr(service.wikipedia, "lookup", fake_lookup)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_context", fake_context)

    result = service.ask(session, "Who won the 2016 Champions League final?")
    assert result["mode"] == "wikipedia+gemini"
    assert result["text"] == "Real Madrid won on penalties, per the Wikipedia article."
    assert "**" not in result["text"]  # markdown stripped
    wiki_sources = [s for s in result["sources"] if s["type"] == "wikipedia"]
    assert len(wiki_sources) == 1
    assert wiki_sources[0]["license"] == "Wikipedia (CC BY-SA)"


def test_service_falls_through_to_gemini_when_wikipedia_answer_is_a_decline(session, monkeypatch):
    """A Wikipedia hit that's the wrong article (or that the grounded call couldn't use)
    must not get surfaced as a bad decline - fall through to Gemini's own reasoning."""

    def fake_lookup(sess, query):
        return {"found": True, "title": "Unrelated Article", "url": "https://en.wikipedia.org/wiki/x", "extract": "irrelevant text", "source": "Wikipedia (CC BY-SA)"}

    def fake_context(sess, question, context, label):
        return {"text": "I don't know from this source.", "used_search": False}

    def fake_ask_gemini(sess, question):
        return {"text": "Reasoned answer from Gemini's own knowledge.", "sources": [], "used_search": False}

    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.wikipedia, "lookup", fake_lookup)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_context", fake_context)
    monkeypatch.setattr(service.gemini_client, "ask_gemini", fake_ask_gemini)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_search", lambda s, q: None)

    result = service.ask(session, "Who is the best young player right now?")
    assert result["text"] == "Reasoned answer from Gemini's own knowledge."


def _boom(*a, **k):
    raise AssertionError("must not be called for this question type")


def test_video_questions_never_touch_wikipedia_or_gemini(session, monkeypatch):
    """Video/highlights is its own path: Wikipedia and Gemini are never consulted, whatever else
    the question mentions (a year, a final, a person)."""
    monkeypatch.setattr(service.wikipedia, "lookup", _boom)
    monkeypatch.setattr(service.gemini_client, "available", lambda: True)
    monkeypatch.setattr(service.gemini_client, "ask_gemini", _boom)
    monkeypatch.setattr(service.gemini_client, "ask_gemini_with_context", _boom)
    for q in (
        "Who scored in the 2016 Champions League final? Give me a link to watch it.",
        "A video link I wanna watch the highlights",
        "highlights of Drake",
    ):
        result = service.ask(session, q)
        assert result["mode"] == "db"
        assert not any(src.get("type") == "wikipedia" for src in result["sources"])


def test_db_intents_never_touch_wikipedia(session, monkeypatch):
    monkeypatch.setattr(service.wikipedia, "lookup", _boom)
    monkeypatch.setattr(service.gemini_client, "available", lambda: False)
    for q in ("When does Ridgeway United play next?", "Predict Rovers 1 vs Ridgeway United", "Where does Ridgeway United stand in the table?"):
        assert service.ask(session, q)["mode"] == "db"


def test_history_questions_go_to_wikipedia_and_unknown_ones_do_not(session, monkeypatch):
    seen = []
    monkeypatch.setattr(service.gemini_client, "available", lambda: False)
    monkeypatch.setattr(service.wikipedia, "lookup", lambda s, q: seen.append(q))
    service.ask(session, "Who won the 2016 Champions League final?")
    assert seen  # history -> Wikipedia consulted
    seen.clear()
    result = service.ask(session, "asdkjfh qwerty")
    assert seen == [] and result["mode"] == "fallback"


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
