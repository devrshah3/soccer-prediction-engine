"""Public-deployment behaviour: build artifacts, "never compute per request" in production, the
background catch-up, /health, and the provider kill switches."""

from __future__ import annotations

import subprocess
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api import artifacts, awards, build, catchup, domestic_scorers, settings, trophy_odds
from kickcast_api import cards as cards_module
from kickcast_api import predictions as predictions_module
from kickcast_api.db import get_session
from kickcast_api.live import api_football
from kickcast_api.main import app
from kickcast_api.models import Base, League, Match, Meta, Team


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELS_DIR", str(tmp_path / "models"))
    predictions_module._cache.clear()
    cards_module._cache.clear()
    trophy_odds._cache.clear()
    engine = create_engine(f"sqlite:///{tmp_path / 'deploy.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(League(code="test.1", name="Test League", country="Testland", kind="domestic_league"))
    s.add_all(Team(id=f"team-{i}", name=f"Club {i}") for i in range(8))
    s.add(Meta(key="data_version", value="1"))
    s.commit()
    d = date(2026, 8, 1)
    for n in range(24):
        s.add(Match(
            league_code="test.1", season="2026-27", date=d, kickoff=None, home_team_id=f"team-{n % 8}",
            away_team_id=f"team-{(n + 1) % 8}", home_goals=n % 4, away_goals=(n + 1) % 3, status="finished",
            round=f"Matchday {n + 1}", neutral=False, source="synthetic", source_id=f"synthetic:{n}",
        ))
        d += timedelta(days=7)
    for k in range(3):
        s.add(Match(
            league_code="test.1", season="2026-27", date=date(2027, 3, 1 + k), kickoff=None, home_team_id=f"team-{k}",
            away_team_id=f"team-{k + 4}", home_goals=None, away_goals=None, status="scheduled", round="Later",
            neutral=False, source="synthetic", source_id=f"synthetic:later-{k}",
        ))
    s.commit()
    yield s
    predictions_module._cache.clear()
    cards_module._cache.clear()


def production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")


def boom(*args, **kwargs):
    raise AssertionError("heavy work ran inside a request")


# ------------------------------------------------------------------ health and settings


def test_health_does_no_database_work(monkeypatch):
    def broken_session():
        raise AssertionError("/health must not open a database session")
        yield  # pragma: no cover

    app.dependency_overrides[get_session] = broken_session
    try:
        r = TestClient(app).get("/health")
        assert r.status_code == 200 and r.json() == {"status": "ok"}
    finally:
        app.dependency_overrides.clear()


def test_production_defaults_are_safe(monkeypatch):
    for name in ("ENABLE_DOCS", "PRECOMPUTED_ONLY", "ENABLE_API_FOOTBALL", "FRONTEND_ORIGIN", "STARTUP_CATCHUP"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    assert settings.enable_docs() and settings.enable_api_football() and not settings.precomputed_only()
    assert "http://localhost:3000" in settings.frontend_origins()
    production(monkeypatch)
    assert not settings.enable_docs() and not settings.enable_api_football()
    assert settings.precomputed_only() and settings.startup_catchup()
    assert settings.frontend_origins() == []  # nothing is allowed until FRONTEND_ORIGIN says so
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://app.example.com/, https://b.example.com")
    assert settings.frontend_origins() == ["https://app.example.com", "https://b.example.com"]
    monkeypatch.setenv("ENABLE_API_FOOTBALL", "true")
    assert settings.enable_api_football()  # explicit opt-in still works


def test_api_football_is_fully_off_in_production_even_with_a_key(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "fake")
    production(monkeypatch)
    assert api_football.available() is False and domestic_scorers.available("en.1") is False
    monkeypatch.setenv("ENABLE_API_FOOTBALL", "true")
    assert api_football.available() is True


# ------------------------------------------------------------------ artifacts


def test_payload_and_model_artifacts_round_trip(session):
    artifacts.put_payload(session, "k", {"a": 1})
    artifacts.put_payload(session, "k", {"a": 2})  # overwrite
    assert artifacts.get_payload(session, "k") == {"a": 2} and artifacts.get_payload(session, "missing") is None
    artifacts.save_model("goals", "en.1", {"model": "m"})
    assert artifacts.load_model("goals", "en.1") == {"model": "m"}
    assert artifacts.load_model("goals", "es.1") is None
    (artifacts.models_dir() / "goals__es_1.pkl").write_bytes(b"not a pickle")
    assert artifacts.load_model("goals", "es.1") is None  # a corrupt artifact degrades, never crashes


def test_production_serves_the_built_model_and_never_fits_in_a_request(session, monkeypatch):
    built = predictions_module.fit_model(session, "test.1", persist=True)  # what the build step does
    assert built is not None and (artifacts.models_dir() / "goals__test_1.pkl").exists()

    predictions_module._cache.clear()  # a fresh process after a cold start
    production(monkeypatch)
    monkeypatch.setattr(predictions_module, "fit_model", boom)
    served = predictions_module.get_model(session, "test.1")
    assert served is not None
    assert served.predict("team-0", "team-1")["probabilities"] == built.predict("team-0", "team-1")["probabilities"]
    assert predictions_module.get_model_computed_at(session, "test.1")

    # stale data_version doesn't trigger a refit either
    session.get(Meta, "data_version").value = "99"
    session.commit()
    assert predictions_module.get_model(session, "test.1") is served


def test_production_without_an_artifact_degrades_instead_of_fitting(session, monkeypatch):
    production(monkeypatch)
    monkeypatch.setattr(predictions_module, "fit_model", boom)
    monkeypatch.setattr(cards_module, "fit_card_model", boom)
    assert predictions_module.get_model(session, "test.1") is None
    assert cards_module.get_card_model(session, "test.1") is None


def test_production_trophy_odds_only_read_the_stored_payload(session, monkeypatch):
    odds = trophy_odds.compute_trophy_odds(session, "test.1", "2026-27")
    assert odds and odds["teams"]
    artifacts.put_payload(session, trophy_odds.payload_key("test.1", "2026-27"), odds)
    production(monkeypatch)
    monkeypatch.setattr(trophy_odds, "compute_trophy_odds", boom)
    assert trophy_odds.get_trophy_odds(session, "test.1", "2026-27") == odds
    assert trophy_odds.get_trophy_odds(session, "test.1", "2020-21") is None  # nothing stored -> honest None


def test_production_awards_read_the_stored_projection_and_never_call_a_provider(session, monkeypatch):
    stored = {"available": True, "season": "2026-27", "source": "football-data.org (live)", "method": "m", "scorers": []}
    artifacts.put_payload(session, awards.golden_boot_payload_key("test.1"), stored)
    production(monkeypatch)
    monkeypatch.setattr(awards.golden_boot_projection, "project", boom)
    result = awards.golden_boot_for_league(session, "test.1", "2026-27")
    assert result["available"] is True and result["tag"] == "Current season"
    missing = awards.golden_boot_for_league(session, "en.1", "2026-27")  # nothing stored, no matches
    assert missing["available"] is False


def test_build_everything_writes_every_artifact_and_survives_a_failing_step(session, monkeypatch):
    report = build.build_everything(session, network=False)
    assert all(v >= 0 for v in report.values()), report
    assert artifacts.load_model("goals", "test.1") is not None
    assert artifacts.get_payload(session, trophy_odds.payload_key("test.1", "2026-27")) is None  # only the 5 real domestic codes get odds
    assert artifacts.get_payload(session, awards.golden_boot_payload_key("CL")) is not None

    monkeypatch.setattr(build, "build_trophy_odds", boom)
    report = build.build_everything(session, network=False)
    assert report["trophy_odds"] == -1.0 and report["golden_boot"] >= 0  # one failure doesn't stop the rest


# ------------------------------------------------------------------ catch-up


def test_current_season_dir_rolls_over_in_july():
    assert catchup.current_season_dir(datetime(2026, 9, 28, tzinfo=UTC)) == "2026-27"
    assert catchup.current_season_dir(datetime(2027, 3, 1, tzinfo=UTC)) == "2026-27"
    assert catchup.current_season_dir(datetime(2027, 7, 1, tzinfo=UTC)) == "2027-28"


def test_catchup_is_skipped_when_data_is_fresh_and_runs_when_stale(session, monkeypatch):
    monkeypatch.setattr(catchup, "SessionLocal", lambda: session)
    monkeypatch.setattr(session, "close", lambda: None)
    steps = []
    monkeypatch.setattr(catchup, "fetch_fresh_sources", lambda: steps.append("fetch") or 7)
    monkeypatch.setattr(catchup, "precompute_predictions", lambda s: steps.append("precompute") or 12)
    seen_env = {}

    def fake_run(cmd, **kw):
        steps.append("ingest")
        seen_env.update(kw["env"])
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(catchup.subprocess, "run", fake_run)

    session.add(Meta(key="ingested_at", value=datetime.now(UTC).isoformat()))
    session.commit()
    assert "skipped" in catchup.run_catchup()  # just built: nothing to do
    assert steps == []

    session.get(Meta, "ingested_at").value = (datetime.now(UTC) - timedelta(hours=5)).isoformat()
    session.commit()
    assert catchup.run_catchup() == {"fetched": 7, "ingest": "ok", "predictions": 12}
    assert steps == ["fetch", "ingest", "precompute"]
    assert seen_env["INGEST_SKIP_PRECOMPUTE"] == "1"  # the subprocess never fits models


def test_catchup_reports_a_failed_ingest_and_only_one_runs_at_a_time(session, monkeypatch):
    monkeypatch.setattr(catchup, "SessionLocal", lambda: session)
    monkeypatch.setattr(catchup, "fetch_fresh_sources", lambda: 0)
    monkeypatch.setattr(catchup.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom"))
    assert catchup.run_catchup(force=True)["ingest"] == "failed"
    assert catchup._lock.acquire(blocking=False)
    try:
        assert "already running" in catchup.run_catchup(force=True)["skipped"]
    finally:
        catchup._lock.release()
