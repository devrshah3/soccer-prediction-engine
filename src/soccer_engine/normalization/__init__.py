"""Normalization services."""

from soccer_engine.normalization.matches import deduplicate_matches, records_to_frame
from soccer_engine.normalization.players import (
    GOAL_INTERVALS,
    goal_interval,
    normalize_statsbomb_players,
)

__all__ = [
    "GOAL_INTERVALS",
    "deduplicate_matches",
    "goal_interval",
    "normalize_statsbomb_players",
    "records_to_frame",
]
