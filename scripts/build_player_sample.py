"""Build the compact attributed Phase 2 sample from StatsBomb Open Data."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from soccer_engine.ingestion import StatsBombOpenDataProvider
from soccer_engine.normalization.players import normalize_statsbomb_players

OUTPUT = Path("src/soccer_engine/sample_data/wsl_2023_24_players.json")
BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


async def fetch_json(client: httpx.AsyncClient, semaphore: asyncio.Semaphore, url: str) -> Any:
    """Fetch one public JSON asset with bounded concurrency and retries."""

    async with semaphore:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True
        ):
            with attempt:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
    raise RuntimeError(f"unreachable download state for {url}")


async def process_match(
    client: httpx.AsyncClient, semaphore: asyncio.Semaphore, match: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    provider_id = str(match.provider_match_id)
    events_url = f"{BASE_URL}/events/{provider_id}.json"
    lineups_url = f"{BASE_URL}/lineups/{provider_id}.json"
    events, lineups = await asyncio.gather(
        fetch_json(client, semaphore, events_url),
        fetch_json(client, semaphore, lineups_url),
    )
    players, goals = normalize_statsbomb_players(
        match_id=match.match_id,
        kickoff=match.kickoff,
        lineups=lineups,
        events=events,
        source_url=events_url,
    )
    return (
        [record.model_dump(mode="json") for record in players],
        [record.model_dump(mode="json") for record in goals],
    )


async def main() -> None:
    provider = StatsBombOpenDataProvider()
    matches = provider.fetch_matches("37", "281")
    semaphore = asyncio.Semaphore(8)
    headers = {"User-Agent": "soccer-engine/0.2 Virginia-Tech-portfolio-research"}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers=headers) as client:
        results = await asyncio.gather(
            *(process_match(client, semaphore, match) for match in matches)
        )
    player_matches = [row for players, _ in results for row in players]
    goal_events = [row for _, goals in results for row in goals]
    payload = {
        "metadata": {
            "provider": "StatsBomb Open Data",
            "competition": "FA Women's Super League",
            "season": "2023/2024",
            "matches": len(matches),
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "https://github.com/statsbomb/open-data",
            "terms": "Attribution required for published analysis; upstream agreement controls.",
        },
        "player_matches": player_matches,
        "goal_events": goal_events,
    }
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"Wrote {len(player_matches)} player-match rows and {len(goal_events)} goals to {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
