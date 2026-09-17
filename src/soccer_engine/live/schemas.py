"""Validated contracts for live feeds and replay output."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from soccer_engine.schemas import OutcomeProbabilities, PlayerScorerProbability


class FeedMode(StrEnum):
    LIVE = "live"
    DELAYED = "delayed"
    REPLAY = "replay"
    UNAVAILABLE = "unavailable"


class LiveEventType(StrEnum):
    GOAL = "goal"
    DISALLOWED_GOAL = "disallowed_goal"
    SHOT = "shot"
    SHOT_ON_TARGET = "shot_on_target"
    CORNER = "corner"
    FOUL = "foul"
    YELLOW_CARD = "yellow_card"
    RED_CARD = "red_card"
    PENALTY = "penalty"
    SUBSTITUTION = "substitution"
    INJURY = "injury"
    VAR = "var"
    SAVE = "save"
    DANGEROUS_ATTACK = "dangerous_attack"
    POSSESSION = "possession"
    CORRECTION = "correction"


class LiveEvent(BaseModel):
    fixture_id: str
    event_id: str | None = None
    provider: str
    provider_timestamp: datetime
    minute: int = Field(ge=0, le=130)
    stoppage_time: int = Field(default=0, ge=0, le=30)
    event_type: LiveEventType
    team_id: str | None = None
    team_name: str | None = None
    player_id: str | None = None
    player_name: str | None = None
    xg: float | None = Field(default=None, ge=0, le=1)
    value: float | None = None
    parser_confidence: float = Field(default=1.0, ge=0, le=1)
    original_text: str | None = None
    correction_for_event_id: str | None = None
    overturned: bool = False


class CommentaryInput(BaseModel):
    fixture_id: str
    provider: str
    provider_timestamp: datetime
    text: str
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str


class LiveMatchRegistration(BaseModel):
    fixture_id: str
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str
    feed_provider: str
    feed_mode: FeedMode
    feed_timestamp: datetime
    confirmed_lineups: bool = False


class TeamLiveStats(BaseModel):
    shots: int = 0
    shots_on_target: int = 0
    supplied_xg: float = 0
    dangerous_attacks: int = 0
    corners: int = 0
    possession: float | None = None
    fouls: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    penalties: int = 0
    substitutions: int = 0
    injuries: int = 0
    saves: int = 0


class LiveMatchState(BaseModel):
    fixture_id: str
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str
    minute: int = 0
    stoppage_time: int = 0
    home_score: int = 0
    away_score: int = 0
    home_stats: TeamLiveStats = Field(default_factory=TeamLiveStats)
    away_stats: TeamLiveStats = Field(default_factory=TeamLiveStats)
    events: list[LiveEvent] = Field(default_factory=list)
    feed_provider: str
    feed_mode: FeedMode
    feed_timestamp: datetime
    estimated_latency_seconds: float = Field(ge=0)
    confirmed_lineups: bool = False
    last_meaningful_attack_minute: int | None = None
    warnings: list[str] = Field(default_factory=list)


class LivePrediction(BaseModel):
    fixture_id: str
    status: FeedMode
    minute: int
    home_score: int
    away_score: int
    outcome: OutcomeProbabilities
    expected_final_home_goals: float = Field(ge=0)
    expected_final_away_goals: float = Field(ge=0)
    live_home_xg: float = Field(ge=0)
    live_away_xg: float = Field(ge=0)
    expected_home_margin: float
    next_home_goal_probability: float = Field(ge=0, le=1)
    next_away_goal_probability: float = Field(ge=0, le=1)
    no_additional_goals_probability: float = Field(ge=0, le=1)
    goal_within_5_minutes: float = Field(ge=0, le=1)
    goal_within_10_minutes: float = Field(ge=0, le=1)
    goal_within_15_minutes: float = Field(ge=0, le=1)
    home_pressure: float = Field(ge=0, le=1)
    away_pressure: float = Field(ge=0, le=1)
    match_pace: float = Field(ge=0)
    player_scoring_probabilities: list[PlayerScorerProbability] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    reliability: str
    model_version: str
    feed_provider: str
    feed_timestamp: datetime
    estimated_latency_seconds: float = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def next_goal_mass_is_valid(self) -> "LivePrediction":
        total = (
            self.next_home_goal_probability
            + self.next_away_goal_probability
            + self.no_additional_goals_probability
        )
        if abs(total - 1) > 1e-6:
            raise ValueError("next-goal probabilities must sum to one")
        return self


class ReplayRequest(BaseModel):
    interval_minutes: int = Field(default=5, ge=1, le=45)
    accelerated: bool = True


class ReplaySnapshot(BaseModel):
    minute: int
    event_id: str | None = None
    prediction: LivePrediction


class ReplayResult(BaseModel):
    match_id: str
    status: FeedMode = FeedMode.REPLAY
    snapshots: list[ReplaySnapshot]
    revealed_events: int
    source: str
