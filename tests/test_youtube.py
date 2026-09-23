from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.assistant import youtube
from kickcast_api.models import Base, YoutubeSearchCache


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'yt.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


REAL_SHAPE_RESPONSE = {
    "items": [
        {
            "id": {"kind": "youtube#video", "videoId": "abc123"},
            "snippet": {
                "publishedAt": "2026-06-01T12:00:00Z",
                "channelTitle": "UEFA",
                "title": "Real Madrid 1-1 Atletico Madrid | Highlights",
            },
        }
    ]
}


def test_unavailable_without_key(session, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert youtube.find_official_highlight(session, "some query") is None


def test_parses_real_response_shape(session, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return REAL_SHAPE_RESPONSE

    monkeypatch.setattr(youtube.requests, "get", lambda *a, **kw: FakeResponse())
    result = youtube.find_official_highlight(session, "Real Madrid Atletico highlights")
    assert result == {
        "title": "Real Madrid 1-1 Atletico Madrid | Highlights",
        "channel": "UEFA",
        "url": "https://www.youtube.com/watch?v=abc123",
        "published_at": "2026-06-01T12:00:00Z",
    }


def test_second_lookup_of_same_query_never_calls_the_api(session, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return REAL_SHAPE_RESPONSE

    def fake_get(*a, **kw):
        calls.append(1)
        return FakeResponse()

    monkeypatch.setattr(youtube.requests, "get", fake_get)
    first = youtube.find_official_highlight(session, "Real Madrid Atletico highlights")
    second = youtube.find_official_highlight(session, "Real Madrid Atletico highlights")
    assert first == second
    assert len(calls) == 1  # cached, not re-searched
    assert session.query(YoutubeSearchCache).count() == 1


def test_no_result_is_cached_as_null_and_not_researched(session, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    calls = []

    class EmptyResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"items": []}

    def fake_get(*a, **kw):
        calls.append(1)
        return EmptyResponse()

    monkeypatch.setattr(youtube.requests, "get", fake_get)
    first = youtube.find_official_highlight(session, "some nonexistent match nobody filmed")
    second = youtube.find_official_highlight(session, "some nonexistent match nobody filmed")
    assert first is None and second is None
    assert len(calls) == 1  # still only one real network call


def test_different_channel_restriction_is_a_different_cache_entry(session, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setenv("YOUTUBE_OFFICIAL_CHANNELS", '{"UEFA": "UCabc"}')
    seen_params = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return REAL_SHAPE_RESPONSE

    def fake_get(url, params=None, timeout=None):
        seen_params.append(params)
        return FakeResponse()

    monkeypatch.setattr(youtube.requests, "get", fake_get)
    youtube.find_official_highlight(session, "final highlights", channel="UEFA")
    youtube.find_official_highlight(session, "final highlights", channel=None)
    assert len(seen_params) == 2  # different cache keys, both hit the network
    assert seen_params[0]["channelId"] == "UCabc"
    assert "channelId" not in seen_params[1]


def test_respects_quota(session, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setenv("YOUTUBE_DAILY_QUOTA", "0")
    assert youtube.find_official_highlight(session, "a fresh uncached query") is None
