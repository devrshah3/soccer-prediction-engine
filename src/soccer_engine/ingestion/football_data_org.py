"""Optional authenticated football-data.org fixture adapter."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from soccer_engine.ingestion.base import DataProvider
from soccer_engine.schemas import MatchRecord, MatchStatus

STATUS_MAP = {
    "SCHEDULED": MatchStatus.SCHEDULED,
    "TIMED": MatchStatus.SCHEDULED,
    "IN_PLAY": MatchStatus.SCHEDULED,
    "PAUSED": MatchStatus.SCHEDULED,
    "FINISHED": MatchStatus.FINISHED,
    "POSTPONED": MatchStatus.POSTPONED,
    "CANCELLED": MatchStatus.CANCELED,
    "SUSPENDED": MatchStatus.POSTPONED,
}


class FootballDataOrgProvider(DataProvider):
    """Use the documented API with a user-supplied key and local response cache."""

    name = "football_data_org"
    base_url = "https://api.football-data.org/v4"

    def __init__(
        self, cache_dir: Path = Path("data/raw/football_data_org"), api_key: str | None = None
    ):
        self.cache_dir = cache_dir
        self.api_key = api_key or os.getenv("FOOTBALL_DATA_ORG_API_KEY")
        if not self.api_key:
            raise ValueError("FOOTBALL_DATA_ORG_API_KEY is required for live fixture refresh")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=16), reraise=True)
    def _get(self, path: str, parameters: dict[str, str] | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(
                f"{self.base_url}/{path.lstrip('/')}",
                params=parameters,
                headers={"X-Auth-Token": self.api_key or "", "User-Agent": "soccer-engine/0.1"},
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

    def _normalize(self, row: dict[str, Any]) -> MatchRecord:
        score = row.get("score", {})
        full_time = score.get("fullTime") or {}
        half_time = score.get("halfTime") or {}
        competition = row["competition"]
        season = row["season"]
        return MatchRecord(
            match_id=f"football_data_org:{row['id']}",
            provider=self.name,
            provider_match_id=str(row["id"]),
            competition_id=f"football_data_org:{competition['code']}",
            competition_name=competition["name"],
            season=str(season["startDate"][:4]),
            kickoff=datetime.fromisoformat(row["utcDate"].replace("Z", "+00:00")),
            home_team_id=f"football_data_org:{row['homeTeam']['id']}",
            home_team_name=row["homeTeam"]["name"],
            away_team_id=f"football_data_org:{row['awayTeam']['id']}",
            away_team_name=row["awayTeam"]["name"],
            status=STATUS_MAP.get(row["status"], MatchStatus.SCHEDULED),
            home_score=full_time.get("home"),
            away_score=full_time.get("away"),
            home_score_ht=half_time.get("home"),
            away_score_ht=half_time.get("away"),
            stage=row.get("stage"),
            venue=row.get("venue"),
            referee=(row.get("referees") or [{}])[0].get("name"),
            source_url="https://www.football-data.org/",
        )

    def fetch_matches(self, competition_id: str, season_id: str) -> list[MatchRecord]:
        payload = self._get(f"competitions/{competition_id}/matches", {"season": season_id})
        return [self._normalize(row) for row in payload.get("matches", [])]

    def fetch_upcoming_fixtures(self, competition_id: str) -> list[MatchRecord]:
        payload = self._get(f"competitions/{competition_id}/matches", {"status": "SCHEDULED"})
        target = self.cache_dir / f"fixtures_{competition_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2))
        return [self._normalize(row) for row in payload.get("matches", [])]
