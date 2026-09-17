"""Configuration-driven global competition registry and observed coverage."""

import json
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class CoverageStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    ADAPTER_READY = "adapter-ready"
    CREDENTIAL_REQUIRED = "credential-required"
    UNAVAILABLE = "unavailable"


class CompetitionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    name: str
    region: str
    country: str
    kind: str
    status: CoverageStatus
    providers: dict[str, str | None] = Field(default_factory=dict)

    @property
    def international(self) -> bool:
        return self.kind.startswith("international")


class CompetitionRegistry:
    """Read competition capabilities without embedding league rules in model code."""

    def __init__(self, path: Path = Path("configs/competitions.yaml")) -> None:
        payload = yaml.safe_load(path.read_text())
        self.competitions = [
            CompetitionConfig.model_validate(row) for row in payload["competitions"]
        ]

    def find(self, key: str) -> CompetitionConfig:
        try:
            return next(item for item in self.competitions if item.key == key)
        except StopIteration as error:
            raise KeyError(f"unknown competition: {key}") from error

    def as_dicts(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.competitions]


def statsbomb_catalog(
    path: Path = Path("src/soccer_engine/sample_data/statsbomb_catalog.json"),
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value: list[dict[str, Any]] = json.loads(path.read_text()).get("entries", [])
    return value


def coverage_report(
    registry: CompetitionRegistry | None = None,
    catalog_path: Path = Path("src/soccer_engine/sample_data/statsbomb_catalog.json"),
) -> dict[str, Any]:
    """Combine configured capability with exact locally observed open-data counts."""

    registry = registry or CompetitionRegistry()
    entries = statsbomb_catalog(catalog_path)
    rows: list[dict[str, Any]] = []
    matched_pairs: set[tuple[str, str]] = set()
    for competition in registry.competitions:
        matching = [
            row for row in entries if row["competition"].lower() == competition.name.lower()
        ]
        if matching:
            for row in matching:
                matched_pairs.add((str(row["competition"]), str(row["season"])))
                rows.append(
                    {
                        **competition.model_dump(mode="json"),
                        "provider": "statsbomb_open_data",
                        "season": str(row["season"]),
                        "match_level": True,
                        "event_level": True,
                        "player_level": True,
                        "upcoming_fixtures": False,
                        "records": int(row["matches"]),
                        "credential_required": False,
                        "freshness": row.get("status", "unknown"),
                        "limitations": (
                            "Historical open-data subset; not complete worldwide coverage."
                        ),
                    }
                )
        else:
            live = "football_data_org" in competition.providers
            rows.append(
                {
                    **competition.model_dump(mode="json"),
                    "provider": next(iter(competition.providers), None),
                    "season": None,
                    "match_level": competition.status != CoverageStatus.UNAVAILABLE,
                    "event_level": False,
                    "player_level": False,
                    "upcoming_fixtures": live,
                    "records": 0,
                    "credential_required": live,
                    "freshness": "not-ingested",
                    "limitations": "Adapter capability only; no local records prove coverage.",
                }
            )
    for row in entries:
        pair = (str(row["competition"]), str(row["season"]))
        if pair in matched_pairs:
            continue
        rows.append(
            {
                "key": f"statsbomb_{row['competition_id']}",
                "name": row["competition"],
                "region": row["country"],
                "country": row["country"],
                "kind": "international" if row["international"] else "club",
                "status": "partial",
                "providers": {"statsbomb_open_data": str(row["competition_id"])},
                "provider": "statsbomb_open_data",
                "season": str(row["season"]),
                "match_level": True,
                "event_level": True,
                "player_level": True,
                "upcoming_fixtures": False,
                "records": int(row["matches"]),
                "credential_required": False,
                "freshness": row.get("status", "unknown"),
                "limitations": "Observed open-data catalog entry outside priority registry.",
            }
        )
    counts = Counter(row["status"] for row in rows)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "registered_competitions": len(registry.competitions),
        "observed_statsbomb_pairs": len(entries),
        "observed_statsbomb_matches": sum(int(row["matches"]) for row in entries),
        "status_counts": dict(counts),
        "rows": rows,
    }
