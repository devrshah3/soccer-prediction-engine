"""HTTP API for model metadata, fixtures, and predictions."""

from functools import lru_cache
from pathlib import Path
from typing import cast

import pandas as pd
from fastapi import FastAPI, HTTPException

from soccer_engine.features.team import build_match_features
from soccer_engine.inference.predictor import predict_fixture
from soccer_engine.schemas import FixturePrediction
from soccer_engine.storage import LocalStore
from soccer_engine.training import ModelBundle

app = FastAPI(
    title="Global Soccer Prediction Engine",
    version="0.1.0",
    description=(
        "Calibrated pre-match probabilities for analytics and education—not betting advice."
    ),
)


@lru_cache(maxsize=1)
def _bundle() -> ModelBundle:
    try:
        return ModelBundle.load(Path("models/champion.joblib"))
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503, detail="model unavailable; run soccer-engine train"
        ) from error


def _matches() -> pd.DataFrame:
    try:
        return LocalStore().read_frame("matches")
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503, detail="match data unavailable; run ingestion"
        ) from error


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "soccer-engine", "version": "0.1.0"}


@app.get("/fixtures")
def fixtures() -> list[dict[str, object]]:
    frame = _matches()
    scheduled = frame[frame["status"] == "scheduled"].sort_values("kickoff")
    columns = ["match_id", "competition_name", "kickoff", "home_team_name", "away_team_name"]
    return cast(list[dict[str, object]], scheduled[columns].to_dict(orient="records"))


@app.get("/predictions/{fixture_id}", response_model=FixturePrediction)
def prediction(fixture_id: str) -> FixturePrediction:
    matches = _matches()
    selected = matches[matches["match_id"] == fixture_id]
    if selected.empty:
        raise HTTPException(status_code=404, detail="fixture not found")
    features = build_match_features(matches)
    feature = features[features["match_id"] == fixture_id]
    return predict_fixture(selected.iloc[0], feature, _bundle())
