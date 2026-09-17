"""Cutoff-safe broad goal-interval intensity model."""

import math
from datetime import datetime

import numpy as np
import pandas as pd

from soccer_engine.normalization.players import GOAL_INTERVALS
from soccer_engine.schemas import GoalIntervalProbability


def predict_goal_intervals(
    goal_events: pd.DataFrame,
    fixture_kickoff: datetime | pd.Timestamp,
    expected_home_goals: float,
    expected_away_goals: float,
    smoothing: float = 2.0,
) -> tuple[list[GoalIntervalProbability], str]:
    """Estimate interval intensities from goals known strictly before kickoff."""

    cutoff = pd.Timestamp(fixture_kickoff)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    if goal_events.empty:
        counts = np.zeros(len(GOAL_INTERVALS), dtype=float)
        observations = 0
    else:
        history = goal_events.copy()
        history["kickoff"] = pd.to_datetime(history["kickoff"], utc=True)
        history = history[history["kickoff"] < cutoff]
        counts = np.array(
            [(history["interval"] == interval).sum() for interval in GOAL_INTERVALS], dtype=float
        )
        observations = len(history)
    shares = (counts + smoothing) / (counts.sum() + smoothing * len(GOAL_INTERVALS))
    predictions = []
    for interval, share in zip(GOAL_INTERVALS, shares, strict=True):
        home_intensity = expected_home_goals * float(share)
        away_intensity = expected_away_goals * float(share)
        predictions.append(
            GoalIntervalProbability(
                interval=interval,
                home_goal_probability=1 - math.exp(-home_intensity),
                away_goal_probability=1 - math.exp(-away_intensity),
                any_goal_probability=1 - math.exp(-(home_intensity + away_intensity)),
            )
        )
    reliability = "high" if observations >= 150 else "medium" if observations >= 50 else "low"
    return predictions, reliability
