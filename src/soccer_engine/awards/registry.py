"""Configuration-driven, edition-aware award registry."""

from datetime import datetime
from pathlib import Path

import yaml

from soccer_engine.awards.schemas import AwardDefinition, AwardEdition


class AwardRegistry:
    def __init__(self, path: Path = Path("configs/awards.yaml")) -> None:
        if not path.exists():
            packaged = Path(__file__).parents[1] / "config" / "awards.yaml"
            path = packaged
        if not path.exists():
            raise FileNotFoundError(f"award registry not found: {path}")
        payload = yaml.safe_load(path.read_text())
        self.schema_version = str(payload["schema_version"])
        self.awards = {
            item.id: item
            for item in (AwardDefinition.model_validate(row) for row in payload["awards"])
        }

    def get(self, award_id: str) -> AwardDefinition:
        try:
            return self.awards[award_id]
        except KeyError as error:
            raise KeyError(f"unsupported award: {award_id}") from error

    def edition(self, award_id: str, edition: str | None, as_of: datetime) -> AwardEdition | None:
        award = self.get(award_id)
        if edition:
            return next((item for item in award.editions if item.edition == edition), None)
        eligible = [
            item
            for item in award.editions
            if item.eligibility_start <= as_of <= item.eligibility_end
        ]
        return eligible[-1] if eligible else None

    def coverage(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "awards": len(self.awards),
            "editions": sum(len(item.editions) for item in self.awards.values()),
            "rows": [item.model_dump(mode="json") for item in self.awards.values()],
        }
