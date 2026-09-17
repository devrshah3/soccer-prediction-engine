"""StatsBomb Open Data adapter with caching and conservative network behavior."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from soccer_engine.ingestion.base import DataProvider
from soccer_engine.schemas import MatchRecord, MatchStatus


class StatsBombOpenDataProvider(DataProvider):
    """Read public research data published in StatsBomb's open-data repository.

    Usage requires StatsBomb attribution when derived analysis is published.
    This adapter does not scrape statsbomb.com or bypass access controls.
    """

    name = "statsbomb_open_data"
    base_url = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

    def __init__(self, cache_dir: Path = Path("data/raw/statsbomb"), timeout: float = 30.0):
        self.cache_dir = cache_dir
        self.timeout = timeout
        self._last_request = 0.0

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def _download(self, url: str) -> bytes:
        elapsed = time.monotonic() - self._last_request
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "soccer-engine/0.1 research"})
            response.raise_for_status()
        self._last_request = time.monotonic()
        return response.content

    def fetch_raw_matches(self, competition_id: str, season_id: str) -> list[dict[str, Any]]:
        """Return cached raw match JSON, downloading once when absent."""

        target = self.cache_dir / "matches" / competition_id / f"{season_id}.json"
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            url = f"{self.base_url}/matches/{competition_id}/{season_id}.json"
            target.write_bytes(self._download(url))
        value: list[dict[str, Any]] = json.loads(target.read_text())
        return value

    def fetch_matches(self, competition_id: str, season_id: str) -> list[MatchRecord]:
        """Fetch and normalize a StatsBomb match index."""

        source_url = f"{self.base_url}/matches/{competition_id}/{season_id}.json"
        return [
            self._normalize(row, source_url)
            for row in self.fetch_raw_matches(competition_id, season_id)
        ]

    def _normalize(self, row: dict[str, Any], source_url: str) -> MatchRecord:
        kickoff = datetime.fromisoformat(f"{row['match_date']}T{row.get('kick_off') or '00:00:00'}")
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=UTC)
        stage = row.get("competition_stage", {}).get("name")
        stadium = row.get("stadium") or {}
        referee = row.get("referee") or {}
        return MatchRecord(
            match_id=f"statsbomb:{row['match_id']}",
            provider=self.name,
            provider_match_id=str(row["match_id"]),
            competition_id=f"statsbomb:{row['competition']['competition_id']}",
            competition_name=row["competition"]["competition_name"],
            season=str(row["season"]["season_name"]),
            kickoff=kickoff,
            home_team_id=f"statsbomb:{row['home_team']['home_team_id']}",
            home_team_name=row["home_team"]["home_team_name"],
            away_team_id=f"statsbomb:{row['away_team']['away_team_id']}",
            away_team_name=row["away_team"]["away_team_name"],
            status=MatchStatus.FINISHED,
            home_score=row.get("home_score"),
            away_score=row.get("away_score"),
            neutral_venue=bool(row.get("neutral", False)),
            stage=stage,
            venue=stadium.get("name"),
            referee=referee.get("name"),
            source_url=source_url,
        )
