from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from soccer_engine.features.team import build_match_features
from soccer_engine.live.engine import LiveEngine
from soccer_engine.live.parser import CommentaryParser
from soccer_engine.live.predictor import predict_live
from soccer_engine.live.replay import StatsBombReplay
from soccer_engine.live.schemas import (
    CommentaryInput,
    FeedMode,
    LiveEvent,
    LiveEventType,
    LiveMatchRegistration,
)
from soccer_engine.live.state import LiveStateStore
from soccer_engine.models.goals import PoissonGoalModel
from soccer_engine.models.outcome import OutcomeModel
from soccer_engine.services import SoccerService
from soccer_engine.storage import LocalStore
from soccer_engine.training import ModelBundle


def _comment(text: str) -> CommentaryInput:
    return CommentaryInput(
        fixture_id="test:live",
        provider="mock",
        provider_timestamp=datetime.now(UTC),
        text=text,
        home_team_id="a",
        home_team_name="Alpha",
        away_team_id="b",
        away_team_name="Bravo",
    )


def test_commentary_parser_handles_negation_and_disallowed_goals() -> None:
    parser = CommentaryParser()
    assert parser.parse(_comment("23' No penalty for Alpha after review")) is None
    disallowed = parser.parse(_comment("45+2' Goal disallowed for Alpha after VAR review"))
    assert disallowed is not None
    assert disallowed.event_type == LiveEventType.DISALLOWED_GOAL
    assert disallowed.minute == 45
    assert disallowed.stoppage_time == 2
    assert parser.parse(_comment("30' Alpha might create a chance")) is None


def test_live_state_is_idempotent_out_of_order_and_correctable(tmp_path: Path) -> None:
    store = LiveStateStore(tmp_path)
    registration = LiveMatchRegistration(
        fixture_id="test:live",
        home_team_id="a",
        home_team_name="Alpha",
        away_team_id="b",
        away_team_name="Bravo",
        feed_provider="mock",
        feed_mode=FeedMode.REPLAY,
        feed_timestamp=datetime.now(UTC),
    )
    store.register(registration)
    later = LiveEvent(
        fixture_id="test:live",
        event_id="goal-1",
        provider="mock",
        provider_timestamp=datetime.now(UTC),
        minute=50,
        event_type=LiveEventType.GOAL,
        team_id="a",
    )
    state, accepted = store.ingest(later)
    assert accepted and state.home_score == 1
    _, accepted = store.ingest(later)
    assert not accepted
    earlier = later.model_copy(
        update={"event_id": "shot-1", "minute": 10, "event_type": LiveEventType.SHOT}
    )
    state, _ = store.ingest(earlier)
    assert [event.minute for event in state.events] == [10, 50]
    correction = later.model_copy(
        update={
            "event_id": "var-1",
            "minute": 52,
            "event_type": LiveEventType.DISALLOWED_GOAL,
            "correction_for_event_id": "goal-1",
        }
    )
    state, _ = store.ingest(correction)
    assert state.home_score == 0
    assert next(event for event in state.events if event.event_id == "goal-1").overturned


def _live_service(tmp_path: Path, small_matches: pd.DataFrame) -> tuple[SoccerService, str]:
    normalized = small_matches.copy()
    normalized["home_team_id"] = "statsbomb:" + normalized["home_team_id"].astype(str)
    normalized["away_team_id"] = "statsbomb:" + normalized["away_team_id"].astype(str)
    store = LocalStore(tmp_path / "data")
    store.write_frame("matches", normalized)
    model = tmp_path / "models" / "champion.joblib"
    features = build_match_features(normalized).dropna(subset=["outcome"])
    bundle = ModelBundle(
        outcome_model=OutcomeModel(kind="logistic").fit(features),
        goal_model=PoissonGoalModel().fit(features),
        trained_at=datetime.now(UTC),
        training_cutoff=pd.Timestamp(features["kickoff"].max()).to_pydatetime(),
        data_source="synthetic unit test",
    )
    bundle.save(model)
    match_id = str(normalized.iloc[-1]["match_id"])
    return SoccerService(store, model), match_id


def test_live_prediction_probability_contract(tmp_path: Path, small_matches: pd.DataFrame) -> None:
    service, match_id = _live_service(tmp_path, small_matches)
    engine = LiveEngine(service, tmp_path / "live")
    fixture = small_matches.iloc[-1]
    state = engine.register_fixture(
        match_id,
        provider="mock replay",
        mode=FeedMode.REPLAY,
        feed_timestamp=pd.Timestamp(fixture["kickoff"]).to_pydatetime(),
    )
    prediction = predict_live(state, engine.prematch(match_id))
    assert (
        abs(prediction.outcome.home_win + prediction.outcome.draw + prediction.outcome.away_win - 1)
        < 1e-6
    )
    assert (
        abs(
            prediction.next_home_goal_probability
            + prediction.next_away_goal_probability
            + prediction.no_additional_goals_probability
            - 1
        )
        < 1e-6
    )
    assert prediction.goal_within_5_minutes <= prediction.goal_within_10_minutes
    assert prediction.goal_within_10_minutes <= prediction.goal_within_15_minutes


class FakeStatsBombProvider:
    def __init__(self, root: Path, home_id: str, away_id: str) -> None:
        self.cache_dir = root
        self.home_id = home_id.removeprefix("statsbomb:")
        self.away_id = away_id.removeprefix("statsbomb:")

    def fetch_events(self, provider_match_id: str):
        del provider_match_id
        return [
            {
                "id": "first",
                "type": {"name": "Shot"},
                "minute": 10,
                "timestamp": "00:10:00.000",
                "team": {"id": self.home_id, "name": "Home"},
                "player": {"id": "p1", "name": "One"},
                "shot": {"outcome": {"name": "Goal"}, "statsbomb_xg": 0.2},
            },
            {
                "id": "future",
                "type": {"name": "Shot"},
                "minute": 80,
                "timestamp": "01:20:00.000",
                "team": {"id": self.away_id, "name": "Away"},
                "player": {"id": "p2", "name": "Two"},
                "shot": {"outcome": {"name": "Goal"}, "statsbomb_xg": 0.3},
            },
        ]


def test_replay_never_reveals_future_goal_early(
    tmp_path: Path, small_matches: pd.DataFrame
) -> None:
    service, match_id = _live_service(tmp_path, small_matches)
    engine = LiveEngine(service, tmp_path / "live")
    fixture = service.matches().set_index("match_id").loc[match_id]
    provider = FakeStatsBombProvider(
        tmp_path / "raw", str(fixture["home_team_id"]), str(fixture["away_team_id"])
    )
    replay = StatsBombReplay(engine, provider=provider, output_dir=tmp_path / "replays")  # type: ignore[arg-type]
    result = replay.run(match_id, interval_minutes=5)
    assert len(result.snapshots) == 2
    assert result.snapshots[0].prediction.home_score == 1
    assert result.snapshots[0].prediction.away_score == 0
    assert result.snapshots[1].prediction.away_score == 1


def test_statsbomb_own_goal_is_credited_to_opponent(
    tmp_path: Path, small_matches: pd.DataFrame
) -> None:
    service, match_id = _live_service(tmp_path, small_matches)
    engine = LiveEngine(service, tmp_path / "live")
    fixture = service.matches().set_index("match_id").loc[match_id]
    replay = StatsBombReplay(engine, output_dir=tmp_path / "replays")
    home_id = str(fixture["home_team_id"])
    away_id = str(fixture["away_team_id"])
    event = replay._normalize_event(
        match_id,
        {
            "id": "own-goal",
            "type": {"name": "Own Goal Against"},
            "minute": 25,
            "timestamp": "00:25:00.000",
            "team": {"id": home_id.removeprefix("statsbomb:"), "name": "Home"},
        },
        pd.Timestamp(fixture["kickoff"]).to_pydatetime(),
        home_id,
        away_id,
    )
    assert event is not None
    assert event.team_id == away_id
