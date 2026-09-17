"""Stable domain and API schemas."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELED = "canceled"


class MatchOutcome(StrEnum):
    HOME = "home"
    DRAW = "draw"
    AWAY = "away"


class MatchRecord(BaseModel):
    """Provider-neutral match or fixture record."""

    model_config = ConfigDict(extra="forbid")

    match_id: str
    provider: str
    provider_match_id: str
    competition_id: str
    competition_name: str
    season: str
    kickoff: datetime
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str
    status: MatchStatus
    home_score: int | None = Field(default=None, ge=0)
    away_score: int | None = Field(default=None, ge=0)
    home_score_ht: int | None = Field(default=None, ge=0)
    away_score_ht: int | None = Field(default=None, ge=0)
    neutral_venue: bool = False
    stage: str | None = None
    venue: str | None = None
    referee: str | None = None
    attendance: int | None = Field(default=None, ge=0)
    went_to_extra_time: bool = False
    went_to_penalties: bool = False
    home_penalties: int | None = Field(default=None, ge=0)
    away_penalties: int | None = Field(default=None, ge=0)
    source_url: str
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_scores(self) -> "MatchRecord":
        if self.status == MatchStatus.FINISHED and (
            self.home_score is None or self.away_score is None
        ):
            raise ValueError("finished matches require regulation/extra-time scores")
        if self.home_team_id == self.away_team_id:
            raise ValueError("home and away teams must differ")
        return self

    @property
    def regulation_outcome(self) -> MatchOutcome | None:
        """Return score outcome without converting shootouts into match wins."""

        if self.home_score is None or self.away_score is None:
            return None
        if self.home_score > self.away_score:
            return MatchOutcome.HOME
        if self.home_score < self.away_score:
            return MatchOutcome.AWAY
        return MatchOutcome.DRAW


class ScorelineProbability(BaseModel):
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    probability: float = Field(ge=0, le=1)


class OutcomeProbabilities(BaseModel):
    home_win: float = Field(ge=0, le=1)
    draw: float = Field(ge=0, le=1)
    away_win: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def probabilities_sum_to_one(self) -> "OutcomeProbabilities":
        if abs(self.home_win + self.draw + self.away_win - 1.0) > 1e-6:
            raise ValueError("outcome probabilities must sum to one")
        return self


class PlayerMatchRecord(BaseModel):
    """Normalized player participation and attacking output for one match."""

    model_config = ConfigDict(extra="forbid")

    match_id: str
    kickoff: datetime
    provider: str
    provider_player_id: str
    player_id: str
    player_name: str
    team_id: str
    team_name: str
    position: str | None = None
    in_squad: bool = True
    started: bool = False
    minutes: float = Field(default=0, ge=0, le=130)
    goals: int = Field(default=0, ge=0)
    non_penalty_goals: int = Field(default=0, ge=0)
    assists: int = Field(default=0, ge=0)
    expected_goals: float = Field(default=0, ge=0)
    shots: int = Field(default=0, ge=0)
    shots_on_target: int = Field(default=0, ge=0)
    penalties_taken: int = Field(default=0, ge=0)
    penalties_scored: int = Field(default=0, ge=0)
    first_goal: bool = False
    source_url: str


class GoalEventRecord(BaseModel):
    """Minimal goal-event record used for cutoff-safe timing distributions."""

    match_id: str
    kickoff: datetime
    team_id: str
    player_id: str | None = None
    minute: int = Field(ge=0, le=130)
    interval: str
    own_goal: bool = False
    penalty: bool = False
    source_url: str


class PlayerScorerProbability(BaseModel):
    """Uncertain player scorer forecast reconciled to team expected goals."""

    player_id: str
    player_name: str
    team_id: str
    team_name: str
    position: str | None = None
    starting_probability: float = Field(ge=0, le=1)
    expected_minutes: float = Field(ge=0, le=130)
    expected_goals: float = Field(ge=0)
    scoring_probability: float = Field(ge=0, le=1)
    first_scorer_probability: float = Field(ge=0, le=1)
    reliability: str


class ExpectedLineupPlayer(BaseModel):
    """Player participation estimate based only on earlier team sheets."""

    player_id: str
    player_name: str
    team_id: str
    team_name: str
    position: str | None = None
    starting_probability: float = Field(ge=0, le=1)
    expected_minutes: float = Field(ge=0, le=130)
    reliability: str


class GoalIntervalProbability(BaseModel):
    """Probability of at least one goal within a broad match interval."""

    interval: str
    home_goal_probability: float = Field(ge=0, le=1)
    away_goal_probability: float = Field(ge=0, le=1)
    any_goal_probability: float = Field(ge=0, le=1)


class FixturePrediction(BaseModel):
    """Versioned public prediction contract."""

    schema_version: str = "2.0"
    fixture_id: str
    competition: str
    kickoff: datetime
    home_team: str
    away_team: str
    outcome: OutcomeProbabilities
    expected_home_goals: float = Field(ge=0)
    expected_away_goals: float = Field(ge=0)
    expected_home_margin: float
    likely_scorelines: list[ScorelineProbability]
    over_1_5: float = Field(ge=0, le=1)
    over_2_5: float = Field(ge=0, le=1)
    over_3_5: float = Field(ge=0, le=1)
    both_teams_to_score: float = Field(ge=0, le=1)
    home_clean_sheet: float = Field(ge=0, le=1)
    away_clean_sheet: float = Field(ge=0, le=1)
    expected_lineups: list[ExpectedLineupPlayer] = Field(default_factory=list)
    likely_goalscorers: list[PlayerScorerProbability] = Field(default_factory=list)
    goal_intervals: list[GoalIntervalProbability] = Field(default_factory=list)
    important_factors: list[str]
    data_freshness: datetime
    model_version: str
    reliability: str
    warnings: list[str] = Field(default_factory=list)
