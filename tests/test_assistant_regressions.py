"""Regressions from real assistant failures, all with Gemini disabled.

Real failures being locked in:
  - "Predict Real Madrid vs Barcelona" labelled the fixture's home/away probabilities with the
    order the teams appeared in the question (card said Barcelona 56% at home, text said
    Real Madrid 56%).
  - "A video link I wanna watch the highlights" returned a Wikipedia article about a song.
  - "A video link I wanna watch the highlights for Real Madrid vs barcelona" returned Drake or a
    Champions League records page.
  - nonsense questions dumped an unrelated article.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.assistant import conversation, service
from kickcast_api.assistant import tools as assistant_tools
from kickcast_api.models import Base, League, Match, Team

IDS = ["barcelona", "madrid", "t2", "t3", "t4", "t5", "t6", "t7"]
NAMES = {"barcelona": "Barcelona", "madrid": "Real Madrid"}
VIDEO = {
    "title": "FC BARCELONA 2 - 0 REAL MADRID | RESUMEN", "channel": "LALIGA EA SPORTS",
    "url": "https://www.youtube.com/watch?v=JapzT9-KKFo", "published_at": "2026-05-10T22:00:00Z",
}


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'regress.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(League(code="es.1", name="La Liga", country="Spain", kind="domestic_league"))
    s.add_all(Team(id=i, name=NAMES.get(i, f"Club {i}")) for i in IDS)
    s.commit()

    def add(home, away, hg, ag, status, d, rnd):
        s.add(Match(
            league_code="es.1", season="2025-26", date=d, kickoff="19:00", home_team_id=home, away_team_id=away,
            home_goals=hg, away_goals=ag, status=status, round=rnd, neutral=False,
            source="synthetic", source_id=f"synthetic:{home}-{away}-{d}",
        ))

    d = date(2025, 8, 1)
    for n in range(24):  # enough finished matches to fit a model
        h, a = n % 8, (n + 1) % 8
        add(IDS[h], IDS[a], n % 4, (n + 1) % 3, "finished", d, f"Matchday {n + 1}")
        d += timedelta(days=7)
    add("barcelona", "madrid", 2, 0, "finished", date(2026, 5, 10), "Matchday 36")  # the latest Clasico
    add("barcelona", "madrid", None, None, "scheduled", date(2026, 10, 25), "Matchday 10")  # Barcelona at HOME
    add("madrid", "barcelona", None, None, "scheduled", date(2027, 5, 9), "Matchday 36")  # the later return
    s.commit()
    return s


@pytest.fixture(autouse=True)
def _gemini_off_and_traps(monkeypatch):
    conversation.clear()
    monkeypatch.setattr(service.gemini_client, "available", lambda: False)

    def wikipedia_must_not_be_called(sess, query):
        raise AssertionError(f"Wikipedia was consulted for {query!r}")

    monkeypatch.setattr(service.wikipedia, "lookup", wikipedia_must_not_be_called)
    calls: list[Match] = []

    def fake_highlight(sess, match):
        calls.append(match)
        return {"status": "found", "video": VIDEO, "channel": "LaLiga"}

    monkeypatch.setattr(service.youtube, "find_match_highlight", fake_highlight)
    yield calls
    conversation.clear()


def test_prediction_sentence_matches_the_card_whatever_order_the_question_uses(session):
    tool = assistant_tools.match_prediction_lookup(session, "madrid", "barcelona")  # asked Madrid first
    assert tool["match"]["home_team"]["name"] == "Barcelona"  # the record: Barcelona at home
    probs = tool["prediction"]["probabilities"]
    for question in ("Predict Real Madrid vs Barcelona", "Predict Barcelona vs Real Madrid"):
        text = service.ask(session, question)["text"]
        assert text.startswith("Barcelona (home) vs Real Madrid on Sun Oct 25, 2026, the next of 2 scheduled fixtures")
        assert f"Barcelona {probs['home']:.0%}" in text  # home probability sits next to the home team
        assert f"Real Madrid {probs['away']:.0%}" in text
        assert f"Real Madrid {probs['home']:.0%}" not in text or probs["home"] == probs["away"]


def test_a_video_request_with_no_context_is_not_a_wikipedia_search(session):
    result = service.ask(session, "A video link I wanna watch the highlights")
    assert "Which match do you mean?" in result["text"]
    assert result["sources"] == []  # no article, no song


def test_highlights_for_two_named_teams_never_return_an_article(session, _gemini_off_and_traps):
    result = service.ask(session, "A video link I wanna watch the highlights for Real Madrid vs barcelona")
    assert result["text"].startswith("Barcelona 2-0 Real Madrid, Sun May 10, 2026 (La Liga).")
    assert VIDEO["url"] in result["text"]
    assert not any(w in result["text"] for w in ("Drake", "Champions League", "record", "Wikipedia"))
    assert [s["type"] for s in result["sources"]] == ["kickcast_match", "youtube"]
    assert len(_gemini_off_and_traps) == 1 and _gemini_off_and_traps[0].id  # searched OUR match record


def test_nonsense_gets_the_unknown_reply_not_an_article(session):
    for q in ("asdkjfh qwerty zxcv", "purple monkey dishwasher", "?"):
        result = service.ask(session, q)
        assert result["text"].startswith("I don't recognize that one. Try: ")
        assert result["sources"] == []


def test_the_four_real_messages_as_one_conversation(session):
    cid = "conv-real-messages-1"
    predict = service.ask(session, "Predict Real Madrid vs Barcelona", cid)
    assert predict["text"].startswith("Barcelona (home) vs Real Madrid on Sun Oct 25, 2026")

    latest = service.ask(session, "Give em the most recent match highlights of Real Madrid vs barcelona", cid)
    assert latest["text"].startswith("Barcelona 2-0 Real Madrid, Sun May 10, 2026 (La Liga).")
    assert VIDEO["url"] in latest["text"]

    follow_up = service.ask(session, "A video link I wanna watch the highlights", cid)  # resolves to the same pair
    assert follow_up["text"] == latest["text"]

    named = service.ask(session, "A video link I wanna watch the highlights for Real Madrid vs barcelona", cid)
    assert named["text"] == latest["text"]
