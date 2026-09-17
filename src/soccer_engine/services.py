"""Application services shared by CLI, FastAPI, and Streamlit."""

from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from soccer_engine.features.team import build_match_features
from soccer_engine.inference.predictor import predict_fixture
from soccer_engine.schemas import FixturePrediction
from soccer_engine.storage import LocalStore
from soccer_engine.training import ModelBundle


class SoccerService:
    """Single orchestration layer so interfaces do not reimplement model logic."""

    def __init__(
        self,
        store: LocalStore | None = None,
        model_path: Path = Path("models/champion.joblib"),
    ) -> None:
        self.store = store or LocalStore()
        self.model_path = model_path

    def matches(self) -> pd.DataFrame:
        return self.store.read_frame("matches")

    def optional_table(self, name: str) -> pd.DataFrame:
        try:
            return self.store.read_frame(name)
        except FileNotFoundError:
            return pd.DataFrame()

    def fixtures(
        self,
        *,
        target_date: str | None = None,
        competition: str | None = None,
        timezone: str = "UTC",
    ) -> pd.DataFrame:
        frame = self.matches().copy()
        try:
            zone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown timezone: {timezone}") from error
        kickoff = pd.to_datetime(frame["kickoff"], utc=True)
        active = frame["status"].isin(["scheduled", "postponed"])
        frame = frame[active].copy()
        local_kickoff = kickoff[active].dt.tz_convert(zone)
        if target_date:
            frame = frame[local_kickoff.dt.date == pd.Timestamp(target_date).date()]
        if competition:
            frame = frame[frame["competition_name"].str.casefold() == competition.casefold()]
        frame["kickoff"] = pd.to_datetime(frame["kickoff"], utc=True).dt.tz_convert(zone)
        return frame.sort_values("kickoff")

    def predict(self, fixture_id: str) -> FixturePrediction:
        matches = self.matches()
        selected = matches[matches["match_id"] == fixture_id]
        if selected.empty:
            raise KeyError(fixture_id)
        features = build_match_features(matches)
        feature = features[features["match_id"] == fixture_id]
        bundle = ModelBundle.load(self.model_path)
        return predict_fixture(
            selected.iloc[0],
            feature,
            bundle,
            player_matches=self.optional_table("player_match_stats"),
            goal_events=self.optional_table("goal_events"),
        )

    def team_form(self, team_id: str, limit: int = 10) -> pd.DataFrame:
        matches = self.matches()
        mask = (matches["home_team_id"] == team_id) | (matches["away_team_id"] == team_id)
        return matches[mask].sort_values("kickoff", ascending=False).head(limit)

    def player_form(self, player_id: str, limit: int = 10) -> pd.DataFrame:
        players = self.optional_table("player_match_stats")
        if players.empty:
            return players
        return (
            players[players["player_id"] == player_id]
            .sort_values("kickoff", ascending=False)
            .head(limit)
        )
