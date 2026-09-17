"""Shared orchestration for normalized live events and commentary."""

from datetime import UTC, datetime
from pathlib import Path

from soccer_engine.live.parser import CommentaryParser
from soccer_engine.live.predictor import predict_live
from soccer_engine.live.schemas import (
    CommentaryInput,
    FeedMode,
    LiveEvent,
    LiveMatchRegistration,
    LiveMatchState,
    LivePrediction,
)
from soccer_engine.live.state import LiveStateStore
from soccer_engine.schemas import FixturePrediction
from soccer_engine.services import SoccerService


class LiveEngine:
    """Keep pre-match inference and mutable live state separated behind one service boundary."""

    def __init__(
        self,
        service: SoccerService | None = None,
        root: Path = Path("data/predictions/live"),
    ) -> None:
        self.service = service or SoccerService()
        self.store = LiveStateStore(root)
        self.parser = CommentaryParser()
        self.prematch_dir = root / "prematch"
        self.prematch_dir.mkdir(parents=True, exist_ok=True)

    def register_fixture(
        self,
        fixture_id: str,
        *,
        provider: str,
        mode: FeedMode,
        feed_timestamp: datetime | None = None,
        confirmed_lineups: bool = False,
    ) -> LiveMatchState:
        matches = self.service.matches()
        selected = matches[matches["match_id"] == fixture_id]
        if selected.empty:
            raise KeyError(fixture_id)
        fixture = selected.iloc[0]
        registration = LiveMatchRegistration(
            fixture_id=fixture_id,
            home_team_id=str(fixture["home_team_id"]),
            home_team_name=str(fixture["home_team_name"]),
            away_team_id=str(fixture["away_team_id"]),
            away_team_name=str(fixture["away_team_name"]),
            feed_provider=provider,
            feed_mode=mode,
            feed_timestamp=feed_timestamp or datetime.now(UTC),
            confirmed_lineups=confirmed_lineups,
        )
        state = self.store.register(registration)
        path = self._prematch_path(fixture_id)
        if not path.exists():
            prediction = self.service.predict(fixture_id)
            path.write_text(prediction.model_dump_json(indent=2))
        return state

    def _prematch_path(self, fixture_id: str) -> Path:
        import hashlib

        return self.prematch_dir / f"{hashlib.sha256(fixture_id.encode()).hexdigest()}.json"

    def prematch(self, fixture_id: str) -> FixturePrediction:
        path = self._prematch_path(fixture_id)
        if not path.exists():
            raise KeyError(fixture_id)
        return FixturePrediction.model_validate_json(path.read_text())

    def ingest_event(self, event: LiveEvent) -> tuple[LiveMatchState, bool, LivePrediction]:
        state, created = self.store.ingest(event)
        return state, created, predict_live(state, self.prematch(event.fixture_id))

    def ingest_commentary(
        self, commentary: CommentaryInput
    ) -> tuple[LiveMatchState, LiveEvent | None, bool, LivePrediction]:
        event = self.parser.parse(commentary)
        if event is None:
            state = self.store.get(commentary.fixture_id)
            return state, None, False, predict_live(state, self.prematch(commentary.fixture_id))
        state, created, prediction = self.ingest_event(event)
        return state, event, created, prediction

    def state(self, fixture_id: str) -> LiveMatchState:
        return self.store.get(fixture_id)

    def prediction(self, fixture_id: str) -> LivePrediction:
        state = self.state(fixture_id)
        return predict_live(state, self.prematch(fixture_id))

    def timeline(self, fixture_id: str) -> list[LiveEvent]:
        return self.state(fixture_id).events

    def matches(self) -> list[LiveMatchState]:
        return self.store.list_matches()
