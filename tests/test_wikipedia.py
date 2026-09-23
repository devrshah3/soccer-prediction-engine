from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.assistant import wikipedia
from kickcast_api.models import Base, WikipediaCache


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'wiki.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_real_lookup_2016_champions_league_final(tmp_path):
    """Real network call (no key needed - MediaWiki is free/keyless). Confirms the
    exintro-must-be-omitted fix (see wikipedia.py's module docstring) actually gets the
    full article, not the 958-char truncated intro."""
    s = _session(tmp_path)
    result = wikipedia.lookup(s, "2016 UEFA Champions League Final")
    assert result is not None and result["found"] is True
    assert result["title"] == "2016 UEFA Champions League final"
    assert result["source"] == "Wikipedia (CC BY-SA)"
    assert len(result["extract"]) > 5000  # full article, not the intro-only truncation
    assert "Ramos" in result["extract"]
    assert "Carrasco" in result["extract"]
    assert "Ronaldo" in result["extract"]


def test_lookup_is_cached(tmp_path, monkeypatch):
    s = _session(tmp_path)
    calls = {"n": 0}
    real_get = wikipedia._get

    def counting_get(params):
        calls["n"] += 1
        return real_get(params)

    monkeypatch.setattr(wikipedia, "_get", counting_get)
    wikipedia.lookup(s, "2016 UEFA Champions League Final")
    first_calls = calls["n"]
    assert first_calls > 0
    wikipedia.lookup(s, "2016 UEFA Champions League Final")
    assert calls["n"] == first_calls  # second call served entirely from cache, no new HTTP requests
    assert s.query(WikipediaCache).count() == 1


def test_lookup_of_nonsense_query_is_found_false_not_none(tmp_path):
    s = _session(tmp_path)
    result = wikipedia.lookup(s, "zzqxv nonexistent kickcast query 12345 asdkjfh")
    assert result is not None
    assert result["found"] is False
