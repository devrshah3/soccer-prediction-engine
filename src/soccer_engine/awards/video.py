"""Extension boundary for a future rights-cleared goal-video analysis provider."""

from typing import Protocol

from pydantic import BaseModel, Field

from soccer_engine.awards.schemas import SourceMetadata


class GoalVideoAnalysisRequest(BaseModel):
    """Reference a legally accessible clip without copying video into this project."""

    nomination_id: str
    licensed_asset_reference: str
    usage_rights_confirmed: bool = False


class GoalVideoFeatures(BaseModel):
    """Auditable observations returned by an external, licensed implementation."""

    nomination_id: str
    technique_tags: list[str] = Field(default_factory=list)
    estimated_distance_meters: float | None = Field(default=None, ge=0)
    defenders_beaten: int | None = Field(default=None, ge=0)
    model_confidence: float = Field(ge=0, le=1)
    model_version: str
    source: SourceMetadata


class GoalVideoAnalysisProvider(Protocol):
    """Contract only; Phase 4 intentionally bundles no video-analysis implementation."""

    def analyze(self, request: GoalVideoAnalysisRequest) -> GoalVideoFeatures:
        """Return source-attributed features for a rights-cleared video asset."""
