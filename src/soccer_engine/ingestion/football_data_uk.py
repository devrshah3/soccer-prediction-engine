"""Adapter for user-downloaded football-data.co.uk historical CSV files."""

from datetime import UTC
from pathlib import Path
from typing import Any, cast

import pandas as pd

from soccer_engine.ingestion.base import DataProvider, ProviderUnavailableError
from soccer_engine.schemas import MatchRecord, MatchStatus


class FootballDataUKProvider(DataProvider):
    """Normalize legally obtained CSVs without scraping or redistributing them.

    Users must review football-data.co.uk's current terms before downloading. The adapter only reads
    a local file supplied by the user and preserves its path as provenance.
    """

    name = "football_data_uk"
    attribution_url = "https://www.football-data.co.uk/data.php"

    def __init__(self, source_dir: Path = Path("data/raw/football_data_uk")) -> None:
        self.source_dir = source_dir

    def fetch_matches(self, competition_id: str, season_id: str) -> list[MatchRecord]:
        path = self.source_dir / season_id / f"{competition_id}.csv"
        if not path.exists():
            raise ProviderUnavailableError(
                f"local source missing: {path}; download only after reviewing provider terms"
            )
        frame = pd.read_csv(path)
        rows = cast(list[dict[str, Any]], frame.to_dict("records"))
        return [self._normalize(row, competition_id, season_id, path) for row in rows]

    def _normalize(
        self, row: dict[str, Any], competition_id: str, season_id: str, path: Path
    ) -> MatchRecord:
        kickoff = pd.to_datetime(
            f"{row['Date']} {row.get('Time', '00:00')}", dayfirst=True, utc=True
        ).to_pydatetime()
        stable = (
            f"{competition_id}:{season_id}:{kickoff.isoformat()}:"
            f"{row['HomeTeam']}:{row['AwayTeam']}"
        )
        finished = pd.notna(row.get("FTHG")) and pd.notna(row.get("FTAG"))
        return MatchRecord(
            match_id=f"football_data_uk:{stable}",
            provider=self.name,
            provider_match_id=stable,
            competition_id=f"football_data_uk:{competition_id}",
            competition_name=str(row.get("Div", competition_id)),
            season=season_id,
            kickoff=kickoff.astimezone(UTC),
            home_team_id=f"football_data_uk:{row['HomeTeam']}",
            home_team_name=str(row["HomeTeam"]),
            away_team_id=f"football_data_uk:{row['AwayTeam']}",
            away_team_name=str(row["AwayTeam"]),
            status=MatchStatus.FINISHED if finished else MatchStatus.SCHEDULED,
            home_score=int(row["FTHG"]) if finished else None,
            away_score=int(row["FTAG"]) if finished else None,
            home_score_ht=int(row["HTHG"]) if pd.notna(row.get("HTHG")) else None,
            away_score_ht=int(row["HTAG"]) if pd.notna(row.get("HTAG")) else None,
            referee=str(row["Referee"]) if pd.notna(row.get("Referee")) else None,
            source_url=str(path),
        )
