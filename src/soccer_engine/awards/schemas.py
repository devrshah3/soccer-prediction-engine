"""Validated contracts for cutoff-safe award intelligence."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class AwardCategory(StrEnum):
    NARRATIVE = "narrative"
    SCORING = "scoring"
    TOURNAMENT_BEST_PLAYER = "tournament_best_player"
    GOAL = "goal"


class AwardCoverage(StrEnum):
    FULL = "full"
    STATISTICAL_ONLY = "statistical_only"
    MEDIA_ONLY = "media_only"
    METADATA_ONLY = "metadata_only"
    PARTIAL = "partial"
    CREDENTIAL_REQUIRED = "credential_required"
    UNAVAILABLE = "unavailable"


class SourceMetadata(BaseModel):
    source: str
    source_url: str | None = None
    publication_date: datetime
    retrieval_date: datetime
    availability_cutoff: datetime
    usage_notes: str | None = None


class AwardEdition(BaseModel):
    edition: str
    eligibility_start: datetime
    eligibility_end: datetime
    nomination_date: datetime | None = None
    voting_cutoff: datetime | None = None
    ceremony_date: datetime | None = None
    rules: str
    tie_break: str


class AwardDefinition(BaseModel):
    id: str
    official_name: str
    organization: str
    category: AwardCategory
    methodology: str
    coverage: AwardCoverage
    providers: list[str]
    required_data: list[str]
    optional_data: list[str]
    editions: list[AwardEdition] = Field(default_factory=list)


class AwardRule(BaseModel):
    award_id: str
    edition: str
    eligibility_start: datetime
    eligibility_end: datetime
    eligibility_rules: str
    voting_methodology: str
    tie_breaking_rules: str
    source: SourceMetadata


class AwardCandidate(BaseModel):
    award_id: str
    edition: str
    candidate_id: str
    candidate_name: str
    team_name: str | None = None
    position: str | None = None
    official_nominee: bool = False
    candidate_pool_complete: bool = False
    availability_cutoff: datetime
    source: SourceMetadata


class OfficialNominee(BaseModel):
    award_id: str
    edition: str
    candidate_id: str
    candidate_name: str
    nomination_date: datetime
    source: SourceMetadata


class OfficialVoteTotal(BaseModel):
    award_id: str
    edition: str
    candidate_id: str
    vote_total: float = Field(ge=0)
    rank: int | None = Field(default=None, ge=1)
    source: SourceMetadata


class PlayerPeriodStatistics(BaseModel):
    player_id: str
    player_name: str
    period_start: datetime
    period_end: datetime
    competition_scope: str
    context: str
    minutes: float = Field(ge=0)
    starts: int = Field(ge=0)
    goals: int = Field(ge=0)
    non_penalty_goals: int = Field(ge=0)
    assists: int = Field(ge=0)
    expected_goals: float | None = Field(default=None, ge=0)
    expected_assists: float | None = Field(default=None, ge=0)
    shots: int | None = Field(default=None, ge=0)
    shots_on_target: int | None = Field(default=None, ge=0)
    availability_cutoff: datetime
    source: SourceMetadata


class TeamAchievement(BaseModel):
    team_id: str
    competition: str
    season: str
    achievement: str
    achieved_at: datetime
    weight: float = Field(ge=0, le=1)
    availability_cutoff: datetime
    source: SourceMetadata


class PlayerAchievement(BaseModel):
    player_id: str
    achievement: str
    achieved_at: datetime
    weight: float = Field(ge=0, le=1)
    availability_cutoff: datetime
    source: SourceMetadata


class MediaObservation(BaseModel):
    observation_id: str
    award_id: str
    edition: str
    publication: str
    author: str | None = None
    article_date: datetime
    url: str
    candidate_id: str
    candidate_name: str
    extracted_rank: int | None = Field(default=None, ge=1)
    sentiment_score: float | None = Field(default=None, ge=-1, le=1)
    confidence: float = Field(default=1, ge=0, le=1)
    reliability_weight: float = Field(default=1, ge=0, le=1)
    retrieval_method: str = "manual"
    source_terms: str | None = None
    retrieved_at: datetime
    availability_cutoff: datetime


class OfficialAwardResult(BaseModel):
    award_id: str
    edition: str
    candidate_id: str
    candidate_name: str
    rank: int = Field(ge=1)
    vote_total: float | None = Field(default=None, ge=0)
    source: SourceMetadata


class GoalNomination(BaseModel):
    nomination_id: str
    award_id: str
    edition: str
    player_id: str
    player_name: str
    match_id: str | None = None
    competition: str
    goal_date: datetime
    minute: int | None = Field(default=None, ge=0, le=130)
    distance_meters: float | None = Field(default=None, ge=0)
    technique_tags: list[str] = Field(default_factory=list)
    defenders_beaten: int | None = Field(default=None, ge=0)
    match_importance: float | None = Field(default=None, ge=0, le=1)
    official_vote_share: float | None = Field(default=None, ge=0, le=1)
    source: SourceMetadata


class AwardCandidatePrediction(BaseModel):
    rank: int = Field(ge=1)
    candidate_id: str
    candidate_name: str
    team_name: str | None = None
    position: str | None = None
    winner_probability: float = Field(ge=0, le=1)
    top_three_probability: float = Field(ge=0, le=1)
    top_five_probability: float = Field(ge=0, le=1)
    statistical_score: float = Field(ge=0, le=1)
    team_achievement_score: float = Field(ge=0, le=1)
    international_score: float = Field(ge=0, le=1)
    media_score: float | None = Field(default=None, ge=0, le=1)
    combined_score: float = Field(ge=0, le=1)
    current_goals: int | None = Field(default=None, ge=0)
    expected_additional_goals: float | None = Field(default=None, ge=0)
    projected_final_goals: float | None = Field(default=None, ge=0)
    expected_remaining_minutes: float | None = Field(default=None, ge=0)
    shared_award_probability: float | None = Field(default=None, ge=0, le=1)
    data_completeness: float = Field(ge=0, le=1)
    confidence: str
    supporting_factors: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class AwardPrediction(BaseModel):
    schema_version: str = "1.0"
    award_id: str
    award_name: str
    edition: str | None = None
    category: AwardCategory
    status: AwardCoverage
    as_of: datetime
    model_version: str
    data_version: str
    candidates: list[AwardCandidatePrediction] = Field(default_factory=list)
    source_attribution: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime

    @model_validator(mode="after")
    def winner_mass_is_valid(self) -> "AwardPrediction":
        if self.candidates:
            total = sum(item.winner_probability for item in self.candidates)
            if abs(total - 1) > 1e-6:
                raise ValueError("winner probabilities must sum to one across candidates")
        return self


class AwardPredictionSnapshot(BaseModel):
    snapshot_id: str
    as_of: datetime
    prediction: AwardPrediction
    model_version: str
    data_version: str
    source_coverage: list[str]
    missing_data_warnings: list[str]
    created_at: datetime


class AwardEvaluation(BaseModel):
    award_id: str
    editions: int
    date_range: list[str]
    snapshots: int
    top_one_accuracy: float | None = None
    top_three_hit_rate: float | None = None
    top_five_hit_rate: float | None = None
    mean_reciprocal_rank: float | None = None
    ndcg: float | None = None
    spearman: float | None = None
    kendall: float | None = None
    log_loss: float | None = None
    multiclass_brier: float | None = None
    calibration_error: float | None = None
    baselines: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AwardRecomputeRequest(BaseModel):
    award_id: str
    as_of: datetime
    edition: str | None = None
    simulations: int = Field(default=5000, ge=100, le=100000)
    seed: int = 42
