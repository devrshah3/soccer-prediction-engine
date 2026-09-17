"""Shared test fixtures."""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest


@pytest.fixture
def small_matches() -> pd.DataFrame:
    """Synthetic unit-test schedule; never used as training or claimed source data."""

    start = datetime(2024, 1, 1, 15, tzinfo=UTC)
    rows = []
    teams = [("a", "Alpha"), ("b", "Bravo"), ("c", "Charlie"), ("d", "Delta")]
    for index in range(40):
        home_id, home_name = teams[index % 4]
        away_id, away_name = teams[(index + 1 + index // 4) % 4]
        if home_id == away_id:
            away_id, away_name = teams[(index + 2) % 4]
        rows.append(
            {
                "match_id": f"test:{index}",
                "provider": "test",
                "provider_match_id": str(index),
                "competition_id": "test:league",
                "competition_name": "Test League",
                "season": "2024",
                "kickoff": start + timedelta(days=index * 3),
                "home_team_id": home_id,
                "home_team_name": home_name,
                "away_team_id": away_id,
                "away_team_name": away_name,
                "status": "finished",
                "home_score": index % 4,
                "away_score": (index * 2 + 1) % 3,
                "neutral_venue": False,
                "source_url": "test-only",
            }
        )
    return pd.DataFrame(rows)
