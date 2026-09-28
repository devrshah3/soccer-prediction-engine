from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.assistant import youtube
from kickcast_api.models import Base, League, Match, Team, YoutubeSearchCache

MATCH_DATE = date(2026, 5, 10)
LALIGA = youtube.DEFAULT_OFFICIAL_CHANNELS["LaLiga"]
UEFA = youtube.DEFAULT_OFFICIAL_CHANNELS["UEFA"]


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'yt.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add_all([
        League(code="es.1", name="La Liga", country="Spain", kind="domestic_league"),
        League(code="international", name="International", country=None, kind="international"),
        Team(id="madrid", name="Real Madrid"), Team(id="barcelona", name="Barcelona"),
        Team(id="atletico madrid", name="Ath Madrid"), Team(id="serbia", name="Serbia"),
        Team(id="netherlands", name="Netherlands"),
    ])
    s.commit()
    return s


def make_match(session, id_=1, league="es.1", home="barcelona", away="madrid", rnd="Matchday 36", d=MATCH_DATE):
    m = Match(
        id=id_, league_code=league, season="2025-26", date=d, kickoff="19:00", home_team_id=home,
        away_team_id=away, home_goals=2, away_goals=0, status="finished", round=rnd, neutral=False,
        source="synthetic", source_id=f"synthetic:{id_}",
    )
    session.add(m)
    session.commit()
    return m


def item(title, channel_id=LALIGA, published="2026-05-10T22:00:00Z", vid="abc123"):
    return {
        "id": {"videoId": vid},
        "snippet": {"title": title, "channelId": channel_id, "channelTitle": "LALIGA EA SPORTS", "publishedAt": published},
    }


class FakeApi:
    def __init__(self, items):
        self.items, self.calls = items, []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append(params)
        outer = self

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"items": outer.items}

        return Resp()


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.delenv("YOUTUBE_OFFICIAL_CHANNELS", raising=False)


def test_all_default_channels_are_present():
    assert set(youtube.official_channel_ids()) >= {"UEFA", "Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1"}


def test_no_key_and_no_channel_are_honest_statuses(session, monkeypatch):
    m = make_match(session)
    monkeypatch.delenv("YOUTUBE_API_KEY")
    assert youtube.find_match_highlight(session, m)["status"] == "no_key"
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    friendly = make_match(session, 2, league="international", home="serbia", away="netherlands", rnd="Friendly")
    assert youtube.find_match_highlight(session, friendly)["status"] == "no_channel"  # no verified channel
    assert youtube.channel_name_for(make_match(session, 3, league="international", home="serbia", away="netherlands",
                                               rnd="UEFA Nations League 2026/27 MD2", d=date(2026, 9, 27))) == "UEFA"


def test_search_is_built_from_our_record_and_restricted_to_the_official_channel(session, monkeypatch):
    m = make_match(session)
    api = FakeApi([item("Barcelona 2-0 Real Madrid | LALIGA EA SPORTS Highlights")])
    monkeypatch.setattr(youtube.requests, "get", api)
    result = youtube.find_match_highlight(session, m)
    assert result["status"] == "found"
    assert result["video"]["url"] == "https://www.youtube.com/watch?v=abc123"
    params = api.calls[0]
    assert params["q"] == "Barcelona Real Madrid highlights"  # team names from the record, nothing from the user
    assert params["channelId"] == LALIGA
    assert params["publishedAfter"].startswith("2026-05-09") and params["publishedBefore"].startswith("2026-05-14")


@pytest.mark.parametrize(
    ("label", "candidate"),
    [
        ("fan channel", item("Barcelona 2-0 Real Madrid | Highlights", channel_id="UCfanfanfan")),
        ("only one team in the title", item("Barcelona 2-0 Girona | Highlights")),
        ("the OTHER Madrid", item("Barcelona 2-0 Atlético Madrid | Highlights")),
        ("published too long after the match", item("Barcelona 2-0 Real Madrid | Highlights", published="2026-05-14T09:00:00Z")),
        ("published long before the match", item("Barcelona 2-0 Real Madrid | Highlights", published="2026-05-01T09:00:00Z")),
        ("no video id", {"id": {}, "snippet": item("Barcelona v Real Madrid")["snippet"]}),
    ],
)
def test_candidates_that_fail_validation_are_rejected(session, monkeypatch, label, candidate):
    m = make_match(session)
    monkeypatch.setattr(youtube.requests, "get", FakeApi([candidate]))
    assert youtube.find_match_highlight(session, m)["status"] == "none", label


def test_known_aliases_and_the_three_day_window_are_accepted(session, monkeypatch):
    m = make_match(session)
    candidate = item("Barça 2-0 Real Madrid | Resumen", published="2026-05-13T09:00:00Z")  # +3 days, alias "Barça"
    monkeypatch.setattr(youtube.requests, "get", FakeApi([candidate]))
    assert youtube.find_match_highlight(session, m)["status"] == "found"


def test_prefers_a_title_that_says_highlights(session, monkeypatch):
    m = make_match(session)
    api = FakeApi([item("Barcelona v Real Madrid | Press conference", vid="pc"), item("Barcelona v Real Madrid | Highlights", vid="hl")])
    monkeypatch.setattr(youtube.requests, "get", api)
    assert youtube.find_match_highlight(session, m)["video"]["url"].endswith("hl")


def test_hits_are_cached_forever_and_misses_only_for_a_short_time(session, monkeypatch):
    m = make_match(session)
    api = FakeApi([item("Barcelona 2-0 Real Madrid | Highlights")])
    monkeypatch.setattr(youtube.requests, "get", api)
    youtube.find_match_highlight(session, m)
    youtube.find_match_highlight(session, m)
    assert len(api.calls) == 1  # cached hit

    m2 = make_match(session, 2, d=date(2026, 3, 1))
    miss = FakeApi([])
    monkeypatch.setattr(youtube.requests, "get", miss)
    assert youtube.find_match_highlight(session, m2)["status"] == "none"
    assert youtube.find_match_highlight(session, m2)["status"] == "none"
    assert len(miss.calls) == 1  # negative cached too...

    row = session.query(YoutubeSearchCache).filter(YoutubeSearchCache.query == "match:2").one()
    assert json.loads(row.result_json) is None
    row.created_at = (datetime.now(UTC) - youtube.NEGATIVE_TTL - timedelta(minutes=1)).isoformat()
    session.commit()
    youtube.find_match_highlight(session, m2)
    assert len(miss.calls) == 2  # ...but re-searched once the short negative TTL has passed


def test_respects_the_youtube_daily_cap(session, monkeypatch):
    m = make_match(session)
    monkeypatch.setenv("YOUTUBE_DAILY_QUOTA", "0")
    api = FakeApi([item("Barcelona 2-0 Real Madrid | Highlights")])
    monkeypatch.setattr(youtube.requests, "get", api)
    assert youtube.find_match_highlight(session, m)["status"] == "quota"
    assert api.calls == []


def test_network_failure_is_reported_and_not_cached(session, monkeypatch):
    m = make_match(session)

    def boom(*a, **k):
        raise youtube.requests.RequestException("down")

    monkeypatch.setattr(youtube.requests, "get", boom)
    assert youtube.find_match_highlight(session, m)["status"] == "error"
    assert session.query(YoutubeSearchCache).count() == 0
