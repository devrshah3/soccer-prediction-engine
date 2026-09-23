from __future__ import annotations

from fastapi.testclient import TestClient

from kickcast_api.main import app

client = TestClient(app)


def test_list_replay_matches_returns_real_leicester_match():
    r = client.get("/replay/matches")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] and "StatsBomb" in body["source"]
    assert len(body["matches"]) > 0
    leicester = [m for m in body["matches"] if "Leicester" in m["home"]]
    assert leicester
    assert leicester[0]["home_goals"] == 4 and leicester[0]["away_goals"] == 2


def test_get_replay_match_includes_real_event_timeline():
    matches = client.get("/replay/matches").json()["matches"]
    replay_id = next(m["id"] for m in matches if "Leicester" in m["home"])
    r = client.get(f"/replay/matches/{replay_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["timeline"]
    assert any(e["type"] == "goal" and e["player"] == "Jamie Vardy" for e in body["timeline"])
    minutes = [e["minute"] for e in body["timeline"]]
    assert minutes == sorted(minutes)


def test_unknown_replay_match_404():
    assert client.get("/replay/matches/does-not-exist").status_code == 404
