"""Concurrent, idempotent, resumable daily prediction engine."""

import hashlib
import json
import logging
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from soccer_engine.batch.schemas import (
    BatchFixtureResult,
    BatchJob,
    BatchJobRequest,
    BatchJobStatus,
    BatchResultStatus,
    DailySummary,
    PredictionTier,
)
from soccer_engine.features.team import build_match_features
from soccer_engine.inference.predictor import predict_fixture
from soccer_engine.schemas import OutcomeProbabilities
from soccer_engine.services import SoccerService
from soccer_engine.training import ModelBundle, elo_baseline

PROVIDER_ATTRIBUTION = {
    "statsbomb_open_data": "StatsBomb Open Data",
    "football_data_org": "football-data.org",
    "football_data_uk": "football-data.co.uk",
}
LOGGER = logging.getLogger(__name__)


class BatchEngine:
    """Run date-level inference while persisting state after every fixture."""

    def __init__(
        self,
        service: SoccerService | None = None,
        root: Path = Path("data/predictions/batch"),
    ) -> None:
        self.service = service or SoccerService()
        self.root = root
        self.jobs_dir = root / "jobs"
        self.cache_dir = root / "cache"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    @staticmethod
    def job_id(request: BatchJobRequest) -> str:
        value = (
            f"{request.date}|{request.competition or '*'}|{request.timezone}|"
            f"{request.allow_historical_replay}"
        )
        return hashlib.sha256(value.encode()).hexdigest()[:16]

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _save_job(self, job: BatchJob) -> None:
        job.updated_at = datetime.now(UTC)
        target = self._job_path(job.job_id)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(job.model_dump_json(indent=2))
        temporary.replace(target)

    def get_job(self, job_id: str) -> BatchJob:
        path = self._job_path(job_id)
        if not path.exists():
            raise KeyError(job_id)
        return BatchJob.model_validate_json(path.read_text())

    def discover(self, request: BatchJobRequest) -> pd.DataFrame:
        """Find and conservatively deduplicate every locally available fixture on a date."""

        try:
            zone = ZoneInfo(request.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown timezone: {request.timezone}") from error
        frame = self.service.matches().copy()
        frame["kickoff"] = pd.to_datetime(frame["kickoff"], utc=True)
        local_date = frame["kickoff"].dt.tz_convert(zone).dt.date
        frame = frame[local_date == pd.Timestamp(request.date).date()].copy()
        if request.competition:
            target = request.competition.casefold()
            frame = frame[
                (frame["competition_name"].str.casefold() == target)
                | (frame["competition_id"].str.casefold() == target)
            ]
        if not request.allow_historical_replay:
            frame = frame[frame["status"] != "finished"]
        if frame.empty:
            return cast(pd.DataFrame, frame)
        normalized_home = frame["home_team_name"].str.casefold().str.replace(r"\W+", "", regex=True)
        normalized_away = frame["away_team_name"].str.casefold().str.replace(r"\W+", "", regex=True)
        frame["_fingerprint"] = (
            frame["kickoff"].dt.floor("h").astype(str) + normalized_home + normalized_away
        )
        if "ingested_at" in frame:
            frame = frame.sort_values("ingested_at")
        return cast(
            pd.DataFrame,
            frame.drop_duplicates("_fingerprint", keep="last").drop(columns="_fingerprint"),
        )

    def _context(self) -> dict[str, Any]:
        matches = self.service.matches()
        return {
            "matches": matches,
            "features": build_match_features(matches),
            "players": self.service.optional_table("player_match_stats"),
            "goals": self.service.optional_table("goal_events"),
            "bundle": ModelBundle.load(self.service.model_path),
        }

    def _cache_key(self, fixture: pd.Series, context: dict[str, Any]) -> str:
        players: pd.DataFrame = context["players"]
        matches: pd.DataFrame = context["matches"]
        features: pd.DataFrame = context["features"]
        bundle: ModelBundle = context["bundle"]
        feature = features[features["match_id"] == str(fixture["match_id"])]
        payload = {
            "fixture": {
                key: str(fixture.get(key))
                for key in (
                    "match_id",
                    "kickoff",
                    "status",
                    "home_team_id",
                    "away_team_id",
                    "neutral_venue",
                    "ingested_at",
                )
            },
            "model": bundle.version,
            "matches": len(matches),
            "latest_match_ingestion": (
                str(matches["ingested_at"].max()) if "ingested_at" in matches else None
            ),
            "feature": feature.to_json(orient="records", date_format="iso"),
            "players": len(players),
            "latest_player_row": str(players["kickoff"].max()) if not players.empty else None,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def _tier(
        self, feature: pd.DataFrame, context: dict[str, Any], fixture: pd.Series
    ) -> PredictionTier:
        row = feature.iloc[0]
        history = min(float(row["home_matches_played"]), float(row["away_matches_played"]))
        players: pd.DataFrame = context["players"]
        team_ids = {str(fixture["home_team_id"]), str(fixture["away_team_id"])}
        player_teams = set(players["team_id"].astype(str)) if not players.empty else set()
        if history >= 10 and team_ids.issubset(player_teams) and not context["goals"].empty:
            return PredictionTier.FULL
        if history >= 10:
            return PredictionTier.STANDARD
        if history >= 3:
            return PredictionTier.BASIC
        return PredictionTier.UNAVAILABLE

    def _process(
        self, fixture: pd.Series, context: dict[str, Any], force: bool
    ) -> BatchFixtureResult:
        started = time.perf_counter()
        fixture_id = str(fixture["match_id"])
        cache_key = self._cache_key(fixture, context)
        cache_path = self.cache_dir / f"{hashlib.sha256(fixture_id.encode()).hexdigest()}.json"
        if cache_path.exists() and not force:
            cached = BatchFixtureResult.model_validate_json(cache_path.read_text())
            if cached.cache_key == cache_key:
                cached.cached = True
                cached.processing_seconds = time.perf_counter() - started
                return cached
        bundle: ModelBundle = context["bundle"]
        timestamp = pd.Timestamp(fixture.get("ingested_at", datetime.now(UTC))).to_pydatetime()
        base = {
            "fixture_id": fixture_id,
            "competition": str(fixture["competition_name"]),
            "kickoff": pd.Timestamp(fixture["kickoff"]).to_pydatetime(),
            "provider": str(fixture["provider"]),
            "fixture_status": str(fixture["status"]),
            "cache_key": cache_key,
            "model_version": bundle.version,
            "data_timestamp": timestamp,
            "provider_attribution": PROVIDER_ATTRIBUTION.get(
                str(fixture["provider"]), str(fixture["provider"])
            ),
        }
        if str(fixture["status"]) in {"postponed", "canceled"}:
            return BatchFixtureResult.model_validate(
                {
                    **base,
                    "status": BatchResultStatus.UNAVAILABLE,
                    "tier": PredictionTier.UNAVAILABLE,
                    "confidence": 0,
                    "reason": f"fixture is {fixture['status']}; prediction withheld",
                    "processing_seconds": time.perf_counter() - started,
                }
            )
        feature: pd.DataFrame = context["features"]
        feature = feature[feature["match_id"] == fixture_id]
        if feature.empty:
            return BatchFixtureResult.model_validate(
                {
                    **base,
                    "status": BatchResultStatus.UNAVAILABLE,
                    "tier": PredictionTier.UNAVAILABLE,
                    "confidence": 0,
                    "reason": "time-safe feature row unavailable",
                    "processing_seconds": time.perf_counter() - started,
                }
            )
        tier = self._tier(feature, context, fixture)
        if tier == PredictionTier.UNAVAILABLE:
            return BatchFixtureResult.model_validate(
                {
                    **base,
                    "status": BatchResultStatus.UNAVAILABLE,
                    "tier": tier,
                    "confidence": 0,
                    "reason": "fewer than three earlier matches for at least one team",
                    "processing_seconds": time.perf_counter() - started,
                }
            )
        prediction = predict_fixture(
            fixture,
            feature,
            bundle,
            player_matches=context["players"] if tier == PredictionTier.FULL else pd.DataFrame(),
            goal_events=context["goals"] if tier == PredictionTier.FULL else pd.DataFrame(),
        )
        if tier == PredictionTier.BASIC:
            probabilities = elo_baseline(feature)[0]
            prediction.outcome = OutcomeProbabilities(
                away_win=float(probabilities[0]),
                draw=float(probabilities[1]),
                home_win=float(probabilities[2]),
            )
            prediction.warnings.append("Basic tier uses results-only Elo and Poisson evidence.")
        elif tier == PredictionTier.STANDARD:
            prediction.warnings.append(
                "Player, confirmed-lineup, and event inputs are unavailable."
            )
        confidence = {
            PredictionTier.FULL: 0.8,
            PredictionTier.STANDARD: 0.65,
            PredictionTier.BASIC: 0.45,
        }[tier]
        result = BatchFixtureResult.model_validate(
            {
                **base,
                "status": BatchResultStatus.SUCCESS,
                "tier": tier,
                "confidence": confidence,
                "prediction": prediction,
                "processing_seconds": time.perf_counter() - started,
            }
        )
        cache_path.write_text(result.model_dump_json(indent=2))
        return result

    def run(self, request: BatchJobRequest) -> BatchJob:
        """Run or resume a deterministic job and isolate per-fixture failures."""

        started = time.perf_counter()
        identifier = self.job_id(request)
        now = datetime.now(UTC)
        try:
            job = self.get_job(identifier)
            job.request = request
        except KeyError:
            job = BatchJob(
                job_id=identifier,
                request=request,
                status=BatchJobStatus.PENDING,
                created_at=now,
                updated_at=now,
            )
        fixtures = self.discover(request)
        job.status = BatchJobStatus.RUNNING
        job.started_at = now
        job.discovered_fixtures = len(fixtures)
        job.results = []
        self._save_job(job)
        LOGGER.info(
            "batch_started",
            extra={"job_id": identifier, "fixtures": len(fixtures), "date": request.date},
        )
        if fixtures.empty:
            job.status = BatchJobStatus.COMPLETED
            job.completed_at = datetime.now(UTC)
            job.processing_seconds = time.perf_counter() - started
            self._save_job(job)
            return job
        context = self._context()
        with ThreadPoolExecutor(max_workers=request.workers) as executor:
            futures = {
                executor.submit(self._process, fixture, context, request.force): fixture
                for _, fixture in fixtures.iterrows()
            }
            for future in as_completed(futures):
                fixture = futures[future]
                try:
                    result = future.result()
                except Exception as error:  # noqa: BLE001 - fixture-level isolation is required
                    LOGGER.exception(
                        "batch_fixture_failed",
                        extra={"job_id": identifier, "fixture_id": str(fixture["match_id"])},
                    )
                    bundle: ModelBundle = context["bundle"]
                    result = BatchFixtureResult(
                        fixture_id=str(fixture["match_id"]),
                        competition=str(fixture["competition_name"]),
                        kickoff=pd.Timestamp(fixture["kickoff"]).to_pydatetime(),
                        provider=str(fixture["provider"]),
                        fixture_status=str(fixture["status"]),
                        status=BatchResultStatus.FAILED,
                        tier=PredictionTier.UNAVAILABLE,
                        confidence=0,
                        cache_key="failed",
                        model_version=bundle.version,
                        data_timestamp=datetime.now(UTC),
                        provider_attribution=PROVIDER_ATTRIBUTION.get(
                            str(fixture["provider"]), str(fixture["provider"])
                        ),
                        reason=f"{type(error).__name__}: {error}",
                    )
                with self._write_lock:
                    job.results.append(result)
                    self._save_job(job)
        failed = any(item.status == BatchResultStatus.FAILED for item in job.results)
        job.status = BatchJobStatus.COMPLETED_WITH_ERRORS if failed else BatchJobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        job.processing_seconds = time.perf_counter() - started
        self._save_job(job)
        LOGGER.info(
            "batch_completed",
            extra={
                "job_id": identifier,
                "status": job.status,
                "seconds": job.processing_seconds,
            },
        )
        return job

    def find_daily_job(self, date: str) -> BatchJob | None:
        matches = []
        for path in self.jobs_dir.glob("*.json"):
            job = BatchJob.model_validate_json(path.read_text())
            if job.request.date == date:
                matches.append(job)
        return max(matches, key=lambda item: item.updated_at) if matches else None

    def summary(self, job: BatchJob) -> DailySummary:
        tiers = Counter(
            item.tier for item in job.results if item.status == BatchResultStatus.SUCCESS
        )
        competitions = Counter(item.competition for item in job.results)
        providers = Counter(item.provider for item in job.results)
        timestamps = [item.data_timestamp for item in job.results]
        return DailySummary(
            date=job.request.date,
            job_id=job.job_id,
            status=job.status,
            total_discovered_fixtures=job.discovered_fixtures,
            full_tier_predictions=tiers[PredictionTier.FULL],
            standard_tier_predictions=tiers[PredictionTier.STANDARD],
            basic_tier_predictions=tiers[PredictionTier.BASIC],
            partial_predictions=sum(
                bool(item.prediction and item.prediction.warnings)
                for item in job.results
                if item.status == BatchResultStatus.SUCCESS
            ),
            unavailable_fixtures=sum(
                item.status == BatchResultStatus.UNAVAILABLE for item in job.results
            ),
            failed_fixtures=sum(item.status == BatchResultStatus.FAILED for item in job.results),
            cached_predictions=sum(item.cached for item in job.results),
            newly_generated_predictions=sum(
                item.status == BatchResultStatus.SUCCESS and not item.cached for item in job.results
            ),
            competition_coverage=dict(competitions),
            provider_coverage=dict(providers),
            data_freshness=max(timestamps) if timestamps else None,
            processing_seconds=job.processing_seconds,
        )
