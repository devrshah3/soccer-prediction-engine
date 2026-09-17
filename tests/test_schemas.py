from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from soccer_engine.schemas import MatchOutcome, MatchRecord, MatchStatus, OutcomeProbabilities


def test_probabilities_must_sum_to_one() -> None:
    valid = OutcomeProbabilities(home_win=0.4, draw=0.3, away_win=0.3)
    assert valid.home_win + valid.draw + valid.away_win == pytest.approx(1)
    with pytest.raises(ValidationError):
        OutcomeProbabilities(home_win=0.6, draw=0.3, away_win=0.3)


def test_penalty_shootout_does_not_change_regulation_outcome() -> None:
    match = MatchRecord(
        match_id="x",
        provider="test",
        provider_match_id="x",
        competition_id="cup",
        competition_name="Cup",
        season="2024",
        kickoff=datetime(2024, 1, 1, tzinfo=UTC),
        home_team_id="a",
        home_team_name="A",
        away_team_id="b",
        away_team_name="B",
        status=MatchStatus.FINISHED,
        home_score=1,
        away_score=1,
        went_to_penalties=True,
        home_penalties=5,
        away_penalties=4,
        source_url="test-only",
    )
    assert match.regulation_outcome == MatchOutcome.DRAW
