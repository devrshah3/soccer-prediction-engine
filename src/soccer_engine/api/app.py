"""Versioned FastAPI intelligence layer."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
from fastapi import APIRouter, FastAPI, HTTPException, Query

from soccer_engine.api.models import (
    BatchPredictionRequest,
    CatalogResponse,
    FixtureSummary,
    HealthResponse,
    StatusResponse,
)
from soccer_engine.config import coverage_report
from soccer_engine.schemas import FixturePrediction
from soccer_engine.services import SoccerService

VERSION = "0.3.0"
app = FastAPI(
    title="Global Soccer Prediction Engine",
    version=VERSION,
    description="Calibrated pre-match analytics for education—not betting advice.",
)
router = APIRouter(prefix="/api/v1")


def _service() -> SoccerService:
    return SoccerService()


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return cast(
        list[dict[str, Any]], json.loads(frame.to_json(orient="records", date_format="iso"))
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="soccer-engine", version=VERSION)


@router.get("/competitions", response_model=CatalogResponse)
def competitions() -> dict[str, Any]:
    return coverage_report()


@router.get("/seasons", response_model=StatusResponse)
def seasons(competition: str | None = None) -> StatusResponse:
    entries = coverage_report()["rows"]
    if competition:
        entries = [row for row in entries if row["key"] == competition]
    values = sorted({str(row["season"]) for row in entries if row["season"]})
    return StatusResponse(status="available" if values else "unavailable", data={"seasons": values})


@router.get("/fixtures", response_model=list[FixtureSummary])
def fixtures(
    date: str | None = None,
    competition: str | None = None,
    timezone: str = Query(default="UTC"),
) -> list[dict[str, Any]]:
    try:
        frame = _service().fixtures(target_date=date, competition=competition, timezone=timezone)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if "ingested_at" not in frame:
        frame["ingested_at"] = None
    columns = [
        "match_id",
        "competition_name",
        "kickoff",
        "home_team_name",
        "away_team_name",
        "status",
        "provider",
        "ingested_at",
    ]
    return _records(frame[columns].rename(columns={"ingested_at": "freshness"}))


def _prediction(fixture_id: str) -> FixturePrediction:
    try:
        return _service().predict(fixture_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="fixture not found") from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/predictions/{fixture_id}", response_model=FixturePrediction)
def prediction(fixture_id: str) -> FixturePrediction:
    return _prediction(fixture_id)


@router.post("/predictions/batch", response_model=list[FixturePrediction])
def batch_predictions(request: BatchPredictionRequest) -> list[FixturePrediction]:
    return [_prediction(fixture_id) for fixture_id in request.fixture_ids]


@router.get("/teams/{team_id}/form", response_model=StatusResponse)
def team_form(team_id: str, limit: int = Query(default=10, ge=1, le=50)) -> StatusResponse:
    frame = _service().team_form(team_id, limit)
    return StatusResponse(status="available" if len(frame) else "unavailable", data=_records(frame))


@router.get("/players/{player_id}/form", response_model=StatusResponse)
def player_form(player_id: str, limit: int = Query(default=10, ge=1, le=50)) -> StatusResponse:
    frame = _service().player_form(player_id, limit)
    return StatusResponse(status="available" if len(frame) else "unavailable", data=_records(frame))


def _prediction_component(fixture_id: str, component: str) -> StatusResponse:
    value = _prediction(fixture_id)
    items = getattr(value, component)
    rows = [item.model_dump(mode="json") for item in items]
    return StatusResponse(status="available" if rows else "partial", data=rows)


@router.get("/predictions/{fixture_id}/lineups", response_model=StatusResponse)
def lineups(fixture_id: str) -> StatusResponse:
    return _prediction_component(fixture_id, "expected_lineups")


@router.get("/predictions/{fixture_id}/goalscorers", response_model=StatusResponse)
def goalscorers(fixture_id: str) -> StatusResponse:
    return _prediction_component(fixture_id, "likely_goalscorers")


@router.get("/predictions/{fixture_id}/first-goalscorers", response_model=StatusResponse)
def first_goalscorers(fixture_id: str) -> StatusResponse:
    response = _prediction_component(fixture_id, "likely_goalscorers")
    assert isinstance(response.data, list)
    response.data.sort(key=lambda row: row["first_scorer_probability"], reverse=True)
    return response


@router.get("/predictions/{fixture_id}/goal-timing", response_model=StatusResponse)
def goal_timing(fixture_id: str) -> StatusResponse:
    return _prediction_component(fixture_id, "goal_intervals")


@router.get("/data/freshness", response_model=StatusResponse)
def freshness() -> StatusResponse:
    try:
        matches = _service().matches()
        timestamps = pd.to_datetime(matches["ingested_at"], utc=True, errors="coerce")
        latest = timestamps.max()
        value = latest.isoformat() if pd.notna(latest) else None
        return StatusResponse(
            status="available", data={"latest_ingestion": value, "rows": len(matches)}
        )
    except FileNotFoundError:
        return StatusResponse(status="unavailable", data={"latest_ingestion": None, "rows": 0})


@router.get("/providers", response_model=StatusResponse)
def providers() -> StatusResponse:
    key = bool(os.getenv("FOOTBALL_DATA_ORG_API_KEY"))
    values: list[dict[str, Any]] = [
        {"provider": "statsbomb_open_data", "status": "available", "credential_required": False},
        {"provider": "football_data_uk", "status": "adapter-ready", "credential_required": False},
        {
            "provider": "football_data_org",
            "status": "available" if key else "credential-required",
            "credential_required": True,
        },
        {"provider": "api_football", "status": "adapter-ready", "credential_required": True},
        {"provider": "sportmonks", "status": "adapter-ready", "credential_required": True},
        {"provider": "openligadb", "status": "adapter-ready", "credential_required": False},
    ]
    return StatusResponse(status="partial", data=values)


def _json_report(path: Path) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(path.read_text())
    return value


@router.get("/models", response_model=StatusResponse)
def models() -> StatusResponse:
    path = Path("reports/evaluation.json")
    return StatusResponse(
        status="available" if path.exists() else "unavailable",
        data=_json_report(path) if path.exists() else {"version": VERSION},
    )


@router.get("/evaluation", response_model=StatusResponse)
def evaluation() -> StatusResponse:
    path = Path("reports/global_evaluation.json")
    if not path.exists():
        path = Path("reports/evaluation.json")
    return StatusResponse(
        status="available" if path.exists() else "unavailable",
        data=_json_report(path) if path.exists() else {},
    )


@router.get("/data-quality", response_model=StatusResponse)
def data_quality() -> StatusResponse:
    report = coverage_report()
    return StatusResponse(
        status="partial",
        data={
            "registered_competitions": report["registered_competitions"],
            "observed_matches": report["observed_statsbomb_matches"],
            "checked_at": datetime.now(UTC).isoformat(),
        },
        warnings=["Coverage is provider- and season-specific; adapter-ready is not ingested data."],
    )


app.include_router(router)
app.add_api_route("/health", health, response_model=HealthResponse)
app.add_api_route("/fixtures", fixtures, response_model=list[FixtureSummary])
app.add_api_route("/predictions/{fixture_id}", prediction, response_model=FixturePrediction)
