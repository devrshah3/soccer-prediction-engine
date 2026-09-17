"""Validated version-one API contracts."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class FixtureSummary(BaseModel):
    match_id: str
    competition_name: str
    kickoff: datetime
    home_team_name: str
    away_team_name: str
    status: str
    provider: str
    freshness: datetime | None = None


class BatchPredictionRequest(BaseModel):
    fixture_ids: list[str] = Field(default_factory=list, max_length=100)
    date: str | None = None
    competition: str | None = None
    timezone: str = "UTC"
    workers: int = Field(default=4, ge=1, le=32)
    allow_historical_replay: bool = False
    force: bool = False


class LiveIngestResponse(BaseModel):
    accepted: bool
    event: dict[str, Any] | None = None
    state: dict[str, Any]
    prediction: dict[str, Any]


class CatalogResponse(BaseModel):
    generated_at: datetime
    registered_competitions: int
    observed_statsbomb_pairs: int
    observed_statsbomb_matches: int
    status_counts: dict[str, int]
    rows: list[dict[str, Any]]


class StatusResponse(BaseModel):
    status: str
    data: dict[str, Any] | list[dict[str, Any]]
    warnings: list[str] = []
