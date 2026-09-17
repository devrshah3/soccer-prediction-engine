from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from soccer_engine.batch import BatchEngine, BatchJobRequest, PredictionTier
from soccer_engine.batch.schemas import BatchResultStatus
from soccer_engine.features.team import build_match_features
from soccer_engine.models.goals import PoissonGoalModel
from soccer_engine.models.outcome import OutcomeModel
from soccer_engine.services import SoccerService
from soccer_engine.storage import LocalStore
from soccer_engine.training import ModelBundle


def _batch_service(tmp_path: Path, small_matches: pd.DataFrame) -> tuple[SoccerService, str]:
    matches = small_matches.copy()
    kickoff = pd.to_datetime(matches["kickoff"], utc=True).max() + timedelta(days=4)
    template = matches.iloc[-1].to_dict()
    fixtures = []
    for index in range(4):
        row = dict(template)
        row.update(
            {
                "match_id": f"fixture:{index}",
                "provider_match_id": f"future-{index}",
                "kickoff": kickoff,
                "home_team_id": ["a", "b", "c", "d"][index],
                "home_team_name": ["Alpha", "Bravo", "Charlie", "Delta"][index],
                "away_team_id": ["b", "c", "d", "a"][index],
                "away_team_name": ["Bravo", "Charlie", "Delta", "Alpha"][index],
                "status": "postponed" if index == 3 else "scheduled",
                "home_score": None,
                "away_score": None,
                "ingested_at": datetime.now(UTC),
            }
        )
        fixtures.append(row)
    matches = pd.concat([matches, pd.DataFrame(fixtures)], ignore_index=True)
    store = LocalStore(tmp_path / "data")
    store.write_frame("matches", matches)
    model_path = tmp_path / "models" / "champion.joblib"
    features = build_match_features(small_matches).dropna(subset=["outcome"])
    bundle = ModelBundle(
        outcome_model=OutcomeModel(kind="logistic").fit(features),
        goal_model=PoissonGoalModel().fit(features),
        trained_at=datetime.now(UTC),
        training_cutoff=pd.Timestamp(features["kickoff"].max()).to_pydatetime(),
        data_source="synthetic unit test",
    )
    bundle.save(model_path)
    return SoccerService(store, model_path), kickoff.date().isoformat()


def test_batch_is_idempotent_cached_and_status_aware(
    tmp_path: Path, small_matches: pd.DataFrame
) -> None:
    service, date = _batch_service(tmp_path, small_matches)
    engine = BatchEngine(service, tmp_path / "batch")
    request = BatchJobRequest(date=date, workers=3)
    first = engine.run(request)
    assert first.discovered_fixtures == 4
    assert sum(item.status == BatchResultStatus.SUCCESS for item in first.results) == 3
    assert sum(item.status == BatchResultStatus.UNAVAILABLE for item in first.results) == 1
    assert {item.tier for item in first.results if item.status == BatchResultStatus.SUCCESS} == {
        PredictionTier.STANDARD
    }
    second = engine.run(request)
    assert second.job_id == first.job_id
    assert sum(item.cached for item in second.results) == 3
    summary = engine.summary(second)
    assert summary.cached_predictions == 3
    assert summary.standard_tier_predictions == 3


def test_batch_failure_isolation_and_resumable_job(
    tmp_path: Path, small_matches: pd.DataFrame, monkeypatch
) -> None:
    service, date = _batch_service(tmp_path, small_matches)
    engine = BatchEngine(service, tmp_path / "batch")
    original = engine._process

    def fail_one(fixture, context, force):
        if fixture["match_id"] == "fixture:1":
            raise RuntimeError("provider payload malformed")
        return original(fixture, context, force)

    monkeypatch.setattr(engine, "_process", fail_one)
    job = engine.run(BatchJobRequest(date=date, workers=2))
    assert len(job.results) == 4
    assert sum(item.status == BatchResultStatus.FAILED for item in job.results) == 1
    persisted = engine.get_job(job.job_id)
    assert persisted.status == "completed_with_errors"


def test_fixture_change_invalidates_prediction_cache(
    tmp_path: Path, small_matches: pd.DataFrame
) -> None:
    service, date = _batch_service(tmp_path, small_matches)
    engine = BatchEngine(service, tmp_path / "batch")
    request = BatchJobRequest(date=date)
    first = engine.run(request)
    assert not any(item.cached for item in first.results)
    matches = service.matches()
    matches.loc[matches["match_id"] == "fixture:0", "ingested_at"] = datetime.now(UTC) + timedelta(
        minutes=1
    )
    service.store.write_frame("matches", matches)
    second = engine.run(request)
    changed = next(item for item in second.results if item.fixture_id == "fixture:0")
    assert not changed.cached


def test_prediction_tiers_follow_evidence_boundaries(
    tmp_path: Path, small_matches: pd.DataFrame
) -> None:
    service, _ = _batch_service(tmp_path, small_matches)
    engine = BatchEngine(service, tmp_path / "batch")
    fixture = pd.Series({"home_team_id": "a", "away_team_id": "b"})
    empty = pd.DataFrame()

    def feature(history: int) -> pd.DataFrame:
        return pd.DataFrame([{"home_matches_played": history, "away_matches_played": history}])

    base = {"players": empty, "goals": empty}
    assert engine._tier(feature(2), base, fixture) == PredictionTier.UNAVAILABLE
    assert engine._tier(feature(3), base, fixture) == PredictionTier.BASIC
    assert engine._tier(feature(10), base, fixture) == PredictionTier.STANDARD
    full = {
        "players": pd.DataFrame({"team_id": ["a", "b"]}),
        "goals": pd.DataFrame({"event_id": ["goal"]}),
    }
    assert engine._tier(feature(10), full, fixture) == PredictionTier.FULL
