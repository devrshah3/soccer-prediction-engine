"""Validated batch job contracts."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from soccer_engine.schemas import FixturePrediction


class PredictionTier(StrEnum):
    FULL = "full"
    STANDARD = "standard"
    BASIC = "basic"
    UNAVAILABLE = "unavailable"


class BatchResultStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class BatchJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"


class BatchJobRequest(BaseModel):
    date: str
    competition: str | None = None
    timezone: str = "UTC"
    workers: int = Field(default=4, ge=1, le=32)
    allow_historical_replay: bool = False
    force: bool = False


class BatchFixtureResult(BaseModel):
    fixture_id: str
    competition: str
    kickoff: datetime
    provider: str
    fixture_status: str
    status: BatchResultStatus
    tier: PredictionTier
    confidence: float = Field(ge=0, le=1)
    cached: bool = False
    cache_key: str
    model_version: str
    data_timestamp: datetime
    provider_attribution: str
    prediction: FixturePrediction | None = None
    reason: str | None = None
    processing_seconds: float = Field(default=0, ge=0)


class BatchJob(BaseModel):
    job_id: str
    request: BatchJobRequest
    status: BatchJobStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processing_seconds: float = Field(default=0, ge=0)
    discovered_fixtures: int = 0
    results: list[BatchFixtureResult] = Field(default_factory=list)


class DailySummary(BaseModel):
    date: str
    job_id: str | None = None
    status: str
    total_discovered_fixtures: int
    full_tier_predictions: int
    standard_tier_predictions: int
    basic_tier_predictions: int
    partial_predictions: int
    unavailable_fixtures: int
    failed_fixtures: int
    cached_predictions: int
    newly_generated_predictions: int
    competition_coverage: dict[str, int]
    provider_coverage: dict[str, int]
    data_freshness: datetime | None
    processing_seconds: float
