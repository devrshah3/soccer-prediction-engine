from datetime import UTC, datetime

import pytest

from soccer_engine.normalization import deduplicate_matches, records_to_frame
from soccer_engine.schemas import MatchRecord, MatchStatus


def record(status: MatchStatus = MatchStatus.FINISHED) -> MatchRecord:
    return MatchRecord(
        match_id="test:1",
        provider="test",
        provider_match_id="1",
        competition_id="test:league",
        competition_name="League",
        season="2024",
        kickoff=datetime(2024, 1, 1, tzinfo=UTC),
        home_team_id="a",
        home_team_name="A",
        away_team_id="b",
        away_team_name="B",
        status=status,
        home_score=1 if status == MatchStatus.FINISHED else None,
        away_score=0 if status == MatchStatus.FINISHED else None,
        source_url="test-only",
    )


def test_exact_duplicate_matches_are_removed() -> None:
    item = record()
    assert deduplicate_matches([item, item]) == [item]


def test_conflicting_duplicates_are_rejected() -> None:
    first = record()
    second = first.model_copy(update={"home_score": 2})
    with pytest.raises(ValueError, match="conflicting"):
        deduplicate_matches([first, second])


def test_postponed_and_canceled_are_excluded_from_finished_view() -> None:
    records = [record(), record(MatchStatus.POSTPONED), record(MatchStatus.CANCELED)]
    # IDs deliberately differ only for the test view; they are not passed through deduplication.
    records[1] = records[1].model_copy(update={"match_id": "test:2", "provider_match_id": "2"})
    records[2] = records[2].model_copy(update={"match_id": "test:3", "provider_match_id": "3"})
    frame = records_to_frame(records, finished_only=True)
    assert frame["status"].tolist() == ["finished"]
