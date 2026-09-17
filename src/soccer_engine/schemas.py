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


class FixturePrediction(BaseModel):
    """Versioned public prediction contract."""

    schema_version: str = "1.0"
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
    important_factors: list[str]
    data_freshness: datetime
    model_version: str
    reliability: str
    warnings: list[str] = Field(default_factory=list)
