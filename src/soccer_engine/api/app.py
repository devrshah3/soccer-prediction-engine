"""Versioned FastAPI intelligence layer."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast

import pandas as pd
from fastapi import APIRouter, FastAPI, HTTPException, Query

from soccer_engine.api.models import (
    BatchPredictionRequest,
    CatalogResponse,
    FixtureSummary,
    HealthResponse,
    LiveIngestResponse,
    StatusResponse,
)
from soccer_engine.awards import (
    AwardEngine,
    AwardPrediction,
    AwardRecomputeRequest,
    MediaObservation,
)
from soccer_engine.awards.schemas import AwardDefinition
from soccer_engine.batch import BatchEngine, BatchJob, BatchJobRequest, DailySummary
from soccer_engine.config import coverage_report
from soccer_engine.live import LiveEngine, StatsBombReplay
from soccer_engine.live.schemas import (
    CommentaryInput,
    FeedMode,
    LiveEvent,
    LiveMatchState,
    LivePrediction,
    ReplayRequest,
    ReplayResult,
)
from soccer_engine.schemas import FixturePrediction
from soccer_engine.services import SoccerService

VERSION = "0.4.0"
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


@router.post("/predictions/batch", response_model=list[FixturePrediction] | BatchJob)
def batch_predictions(request: BatchPredictionRequest) -> list[FixturePrediction] | BatchJob:
    if request.fixture_ids:
        return [_prediction(fixture_id) for fixture_id in request.fixture_ids]
    if not request.date:
        raise HTTPException(status_code=422, detail="provide fixture_ids or a date")
    try:
        return BatchEngine().run(
            BatchJobRequest(
                date=request.date,
                competition=request.competition,
                timezone=request.timezone,
                workers=request.workers,
                allow_historical_replay=request.allow_historical_replay,
                force=request.force,
            )
        )
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/predictions/batch/{job_id}", response_model=BatchJob)
def batch_status(job_id: str) -> BatchJob:
    try:
        return BatchEngine().get_job(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="batch job not found") from error


@router.get("/predictions/daily/{date}", response_model=BatchJob)
def daily_predictions(date: str) -> BatchJob:
    job = BatchEngine().find_daily_job(date)
    if job is None:
        raise HTTPException(status_code=404, detail="no batch job found for date")
    return job


@router.get("/predictions/daily/{date}/summary", response_model=DailySummary)
def daily_summary(date: str) -> DailySummary:
    engine = BatchEngine()
    job = engine.find_daily_job(date)
    if job is None:
        raise HTTPException(status_code=404, detail="no batch job found for date")
    return engine.summary(job)


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


def _award_engine() -> AwardEngine:
    return AwardEngine()


@router.get("/awards", response_model=StatusResponse)
def awards() -> StatusResponse:
    report = _award_engine().list_awards()
    return StatusResponse(status="partial", data=report)


@router.get("/awards/{award_id}", response_model=AwardDefinition)
def award_definition(award_id: str) -> AwardDefinition:
    try:
        return _award_engine().registry.get(award_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/awards/{award_id}/editions", response_model=StatusResponse)
def award_editions(award_id: str) -> StatusResponse:
    award = award_definition(award_id)
    values = [item.model_dump(mode="json") for item in award.editions]
    return StatusResponse(status="available" if values else "partial", data=values)


def _award_prediction(
    award_id: str, as_of: datetime, edition: str | None = None
) -> AwardPrediction:
    try:
        return _award_engine().rank(award_id, as_of, edition=edition)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/awards/{award_id}/candidates", response_model=StatusResponse)
def award_candidates(
    award_id: str,
    as_of: Annotated[datetime | None, Query()] = None,
    edition: str | None = None,
) -> StatusResponse:
    prediction_value = _award_prediction(award_id, as_of or datetime.now(UTC), edition)
    return StatusResponse(
        status=prediction_value.status,
        data=[item.model_dump(mode="json") for item in prediction_value.candidates],
        warnings=prediction_value.warnings,
    )


@router.get("/awards/{award_id}/rankings", response_model=AwardPrediction)
def award_rankings(
    award_id: str,
    as_of: Annotated[datetime | None, Query()] = None,
    edition: str | None = None,
) -> AwardPrediction:
    return _award_prediction(award_id, as_of or datetime.now(UTC), edition)


@router.get("/awards/{award_id}/predictions", response_model=AwardPrediction)
def award_predictions(
    award_id: str,
    as_of: Annotated[datetime | None, Query()] = None,
    edition: str | None = None,
) -> AwardPrediction:
    return _award_prediction(award_id, as_of or datetime.now(UTC), edition)


@router.get("/awards/{award_id}/leaderboard", response_model=AwardPrediction)
def award_leaderboard(
    award_id: str,
    as_of: Annotated[datetime | None, Query()] = None,
    edition: str | None = None,
) -> AwardPrediction:
    return _award_prediction(award_id, as_of or datetime.now(UTC), edition)


@router.get("/awards/{award_id}/history", response_model=StatusResponse)
def award_history(award_id: str) -> StatusResponse:
    try:
        values = _award_engine().history(award_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return StatusResponse(status="available" if values else "unavailable", data=values)


@router.get("/awards/{award_id}/evaluation", response_model=StatusResponse)
def award_evaluation(award_id: str) -> StatusResponse:
    path = Path("reports/award_evaluation.json")
    if not path.exists():
        return StatusResponse(status="unavailable", data={})
    report = _json_report(path)
    if report.get("award_id") != award_id:
        return StatusResponse(status="unavailable", data={})
    return StatusResponse(status="partial", data=report, warnings=report.get("warnings", []))


@router.post("/awards/{award_id}/media-observations", response_model=StatusResponse)
def add_award_media(award_id: str, observations: list[MediaObservation]) -> StatusResponse:
    if any(item.award_id != award_id for item in observations):
        raise HTTPException(status_code=422, detail="award_id does not match route")
    count = _award_engine().add_media_observations(observations)
    return StatusResponse(status="available", data={"imported": count})


@router.post("/awards/recompute", response_model=AwardPrediction)
def recompute_award(request: AwardRecomputeRequest) -> AwardPrediction:
    try:
        return _award_engine().rank(
            request.award_id,
            request.as_of,
            edition=request.edition,
            simulations=request.simulations,
            seed=request.seed,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def _live_engine() -> LiveEngine:
    return LiveEngine()


@router.post("/live/events", response_model=LiveIngestResponse)
def live_event(event: LiveEvent) -> LiveIngestResponse:
    engine = _live_engine()
    try:
        engine.state(event.fixture_id)
    except KeyError:
        try:
            engine.register_fixture(
                event.fixture_id,
                provider=event.provider,
                mode=FeedMode.LIVE,
                feed_timestamp=event.provider_timestamp,
            )
        except (KeyError, FileNotFoundError) as error:
            raise HTTPException(
                status_code=404, detail="fixture or pre-match model unavailable"
            ) from error
    state, accepted, prediction_value = engine.ingest_event(event)
    return LiveIngestResponse(
        accepted=accepted,
        event=event.model_dump(mode="json"),
        state=state.model_dump(mode="json"),
        prediction=prediction_value.model_dump(mode="json"),
    )


@router.post("/live/commentary", response_model=LiveIngestResponse)
def live_commentary(commentary: CommentaryInput) -> LiveIngestResponse:
    engine = _live_engine()
    try:
        engine.state(commentary.fixture_id)
    except KeyError:
        try:
            engine.register_fixture(
                commentary.fixture_id,
                provider=commentary.provider,
                mode=FeedMode.LIVE,
                feed_timestamp=commentary.provider_timestamp,
            )
        except (KeyError, FileNotFoundError) as error:
            raise HTTPException(
                status_code=404, detail="fixture or pre-match model unavailable"
            ) from error
    state, event, accepted, prediction_value = engine.ingest_commentary(commentary)
    return LiveIngestResponse(
        accepted=accepted,
        event=event.model_dump(mode="json") if event else None,
        state=state.model_dump(mode="json"),
        prediction=prediction_value.model_dump(mode="json"),
    )


@router.get("/live/matches", response_model=list[LiveMatchState])
def live_matches() -> list[LiveMatchState]:
    return _live_engine().matches()


@router.get("/live/matches/{fixture_id}", response_model=LiveMatchState)
def live_match(fixture_id: str) -> LiveMatchState:
    try:
        return _live_engine().state(fixture_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="live match state not found") from error


@router.get("/live/matches/{fixture_id}/prediction", response_model=LivePrediction)
def live_prediction(fixture_id: str) -> LivePrediction:
    try:
        return _live_engine().prediction(fixture_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="live prediction not found") from error


@router.get("/live/matches/{fixture_id}/timeline", response_model=list[LiveEvent])
def live_timeline(fixture_id: str) -> list[LiveEvent]:
    try:
        return _live_engine().timeline(fixture_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="live timeline not found") from error


@router.post("/live/replay/{match_id}", response_model=ReplayResult)
def live_replay(match_id: str, request: ReplayRequest) -> ReplayResult:
    try:
        return StatsBombReplay().run(match_id, request.interval_minutes)
    except (KeyError, FileNotFoundError) as error:
        raise HTTPException(status_code=404, detail=f"replay unavailable: {error}") from error


app.include_router(router)
app.add_api_route("/health", health, response_model=HealthResponse)
app.add_api_route("/fixtures", fixtures, response_model=list[FixtureSummary])
app.add_api_route("/predictions/{fixture_id}", prediction, response_model=FixturePrediction)
