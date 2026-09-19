"""Award prediction and evaluation public API."""

from soccer_engine.awards.ranking import AwardEngine
from soccer_engine.awards.registry import AwardRegistry
from soccer_engine.awards.schemas import (
    AwardCoverage,
    AwardPrediction,
    AwardRecomputeRequest,
    MediaObservation,
)
from soccer_engine.awards.video import GoalVideoAnalysisProvider, GoalVideoAnalysisRequest

__all__ = [
    "AwardCoverage",
    "AwardEngine",
    "AwardPrediction",
    "AwardRecomputeRequest",
    "AwardRegistry",
    "GoalVideoAnalysisProvider",
    "GoalVideoAnalysisRequest",
    "MediaObservation",
]
