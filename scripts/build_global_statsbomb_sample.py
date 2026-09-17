"""Build a compact match-level sample from every StatsBomb Open Data catalog entry."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from soccer_engine.ingestion import StatsBombOpenDataProvider

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE = Path("data/raw/statsbomb")
OUTPUT = Path("src/soccer_engine/sample_data/statsbomb_global_matches.json")
REPORT = Path("src/soccer_engine/sample_data/statsbomb_catalog.json")


async def fetch_bytes(client: httpx.AsyncClient, semaphore: asyncio.Semaphore, url: str) -> bytes:
    async with semaphore:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True
        ):
            with attempt:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
    raise RuntimeError(f"unreachable download state for {url}")


async def cache_pair(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    competition_id: str,
    season_id: str,
) -> tuple[str, str | None]:
    target = CACHE / "matches" / competition_id / f"{season_id}.json"
    if target.exists():
        return "skipped_cached", None
    try:
        content = await fetch_bytes(
            client, semaphore, f"{BASE_URL}/matches/{competition_id}/{season_id}.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return "successful", None
    except Exception as error:  # noqa: BLE001 - catalog records recoverable per-pair failures
        return "failed", str(error)


async def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "soccer-engine/0.3 Virginia-Tech-portfolio-research"}
    semaphore = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers=headers) as client:
        catalog_path = CACHE / "competitions.json"
        if catalog_path.exists():
            catalog_bytes = catalog_path.read_bytes()
        else:
            catalog_bytes = await fetch_bytes(client, semaphore, f"{BASE_URL}/competitions.json")
            catalog_path.write_bytes(catalog_bytes)
        catalog: list[dict[str, Any]] = json.loads(catalog_bytes)
        statuses = await asyncio.gather(
            *(
                cache_pair(
                    client,
                    semaphore,
                    str(entry["competition_id"]),
                    str(entry["season_id"]),
                )
                for entry in catalog
            )
        )

    provider = StatsBombOpenDataProvider(CACHE)
    all_matches: dict[str, dict[str, Any]] = {}
    entries = []
    for entry, (status, error) in zip(catalog, statuses, strict=True):
        count = 0
        if status != "failed":
            try:
                matches = provider.fetch_matches(
                    str(entry["competition_id"]), str(entry["season_id"])
                )
                count = len(matches)
                for match in matches:
                    all_matches[match.match_id] = match.model_dump(mode="json")
            except Exception as normalization_error:  # noqa: BLE001
                status, error = "incompatible", str(normalization_error)
        entries.append(
            {
                "competition_id": entry["competition_id"],
                "season_id": entry["season_id"],
                "country": entry["country_name"],
                "competition": entry["competition_name"],
                "season": entry["season_name"],
                "gender": entry["competition_gender"],
                "international": entry["competition_international"],
                "status": status,
                "matches": count,
                "error": error,
            }
        )
    matches = sorted(all_matches.values(), key=lambda row: (row["kickoff"], row["match_id"]))
    payload = {
        "metadata": {
            "provider": "StatsBomb Open Data",
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "https://github.com/statsbomb/open-data",
            "competition_seasons": len(entries),
            "unique_matches": len(matches),
        },
        "matches": matches,
    }
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(
            {"generated_at": payload["metadata"]["generated_at"], "entries": entries}, indent=2
        )
    )
    summary: dict[str, int] = {}
    for entry in entries:
        summary[entry["status"]] = summary.get(entry["status"], 0) + 1
    print(f"Catalog entries: {len(entries)}; unique matches: {len(matches)}; statuses: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
