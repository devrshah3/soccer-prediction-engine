"""Live-state probability updates, strictly separate from pre-match model fitting."""

import math

import numpy as np

from soccer_engine.live.schemas import FeedMode, LiveMatchState, LivePrediction
from soccer_engine.schemas import FixturePrediction, OutcomeProbabilities, PlayerScorerProbability


def _poisson(rate: float, value: int) -> float:
    return math.exp(-rate) * rate**value / math.factorial(value)


def _pressure(state: LiveMatchState, team_id: str) -> float:
    recent = [
        event
        for event in state.events
        if not event.overturned
        and event.team_id == team_id
        and event.minute >= max(0, state.minute - 10)
    ]
    weights = {
        "goal": 1.0,
        "shot_on_target": 0.7,
        "shot": 0.35,
        "dangerous_attack": 0.2,
        "corner": 0.15,
        "penalty": 0.8,
    }
    return float(np.clip(sum(weights.get(event.event_type, 0.0) for event in recent) / 3, 0, 1))


def predict_live(state: LiveMatchState, prematch: FixturePrediction) -> LivePrediction:
    """Update a pre-match forecast from only the currently revealed normalized state."""

    elapsed = min(float(state.minute + state.stoppage_time), 95.0)
    remaining_fraction = max(0.0, (95.0 - elapsed) / 95.0)
    observed_shots = state.home_stats.shots + state.away_stats.shots
    expected_shots_so_far = max(1.0, 22.0 * elapsed / 95.0)
    pace = float(np.clip(observed_shots / expected_shots_so_far, 0.6, 1.6))
    home_pressure = _pressure(state, state.home_team_id)
    away_pressure = _pressure(state, state.away_team_id)
    home_card_factor = 0.72**state.home_stats.red_cards * 1.18**state.away_stats.red_cards
    away_card_factor = 0.72**state.away_stats.red_cards * 1.18**state.home_stats.red_cards
    home_remaining = (
        prematch.expected_home_goals
        * remaining_fraction
        * pace
        * home_card_factor
        * (0.9 + 0.2 * home_pressure)
    )
    away_remaining = (
        prematch.expected_away_goals
        * remaining_fraction
        * pace
        * away_card_factor
        * (0.9 + 0.2 * away_pressure)
    )
    outcome = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for home_goals in range(8):
        for away_goals in range(8):
            probability = _poisson(home_remaining, home_goals) * _poisson(
                away_remaining, away_goals
            )
            final_home = state.home_score + home_goals
            final_away = state.away_score + away_goals
            key = (
                "home" if final_home > final_away else "away" if final_home < final_away else "draw"
            )
            outcome[key] += probability
    total_outcome = sum(outcome.values())
    outcome = {key: value / total_outcome for key, value in outcome.items()}
    total_remaining = home_remaining + away_remaining
    no_more = math.exp(-total_remaining)
    any_more = 1 - no_more
    home_next = any_more * home_remaining / total_remaining if total_remaining else 0.0
    away_next = any_more * away_remaining / total_remaining if total_remaining else 0.0
    per_minute = total_remaining / max(95.0 - elapsed, 1.0)
    event_count = len([event for event in state.events if not event.overturned])
    confidence = float(np.clip(0.45 + min(event_count, 20) / 50, 0, 0.85))
    if state.feed_mode == FeedMode.DELAYED:
        confidence *= 0.7
    warnings = list(state.warnings)
    if not state.confirmed_lineups:
        warnings.append(
            "Confirmed lineups are unavailable; live player probabilities are withheld."
        )
    warnings.append("Live probabilities are uncertain analytics, not guaranteed betting advice.")
    player_probabilities = []
    if state.confirmed_lineups and prematch.likely_goalscorers:
        intensities = [
            item.expected_goals * remaining_fraction for item in prematch.likely_goalscorers
        ]
        total_intensity = sum(intensities)
        probability_any = 1 - math.exp(-total_intensity)
        for item, intensity in zip(prematch.likely_goalscorers, intensities, strict=True):
            player_probabilities.append(
                PlayerScorerProbability(
                    **item.model_dump(
                        exclude={
                            "expected_goals",
                            "scoring_probability",
                            "first_scorer_probability",
                        }
                    ),
                    expected_goals=intensity,
                    scoring_probability=1 - math.exp(-intensity),
                    first_scorer_probability=(
                        intensity / total_intensity * probability_any if total_intensity else 0
                    ),
                )
            )
    return LivePrediction(
        fixture_id=state.fixture_id,
        status=state.feed_mode,
        minute=state.minute,
        home_score=state.home_score,
        away_score=state.away_score,
        outcome=OutcomeProbabilities(
            home_win=outcome["home"], draw=outcome["draw"], away_win=outcome["away"]
        ),
        expected_final_home_goals=state.home_score + home_remaining,
        expected_final_away_goals=state.away_score + away_remaining,
        live_home_xg=state.home_stats.supplied_xg,
        live_away_xg=state.away_stats.supplied_xg,
        expected_home_margin=(state.home_score + home_remaining)
        - (state.away_score + away_remaining),
        next_home_goal_probability=home_next,
        next_away_goal_probability=away_next,
        no_additional_goals_probability=no_more,
        goal_within_5_minutes=1 - math.exp(-per_minute * min(5, 95 - elapsed)),
        goal_within_10_minutes=1 - math.exp(-per_minute * min(10, 95 - elapsed)),
        goal_within_15_minutes=1 - math.exp(-per_minute * min(15, 95 - elapsed)),
        home_pressure=home_pressure,
        away_pressure=away_pressure,
        match_pace=pace,
        player_scoring_probabilities=player_probabilities,
        confidence=confidence,
        reliability="high" if confidence >= 0.75 else "medium" if confidence >= 0.55 else "low",
        model_version=f"{prematch.model_version}+live-0.3.5",
        feed_provider=state.feed_provider,
        feed_timestamp=state.feed_timestamp,
        estimated_latency_seconds=state.estimated_latency_seconds,
        warnings=sorted(set(warnings)),
    )
