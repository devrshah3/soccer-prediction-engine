"""International results (martj42/international_results, CC0) -> MatchResult rows.

Includes goalscorers.csv (scorer, minute, penalty, own goal) for the assistant.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from ..models.dixon_coles import MatchResult

SOURCE = "martj42/international_results"
# UEFA/common name -> name used in the dataset
ALIASES = {"Czechia": "Czech Republic", "Türkiye": "Turkey", "Turkiye": "Turkey"}


def canonical(name: str) -> str:
    return ALIASES.get(name, name)


def load_results(path: Path, since: date, friendly_weight: float = 0.5) -> list[MatchResult]:
    out = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            d = date.fromisoformat(r["date"])
            if d < since or r["home_score"] in ("", "NA"):
                continue
            out.append(
                MatchResult(
                    date=d,
                    home=r["home_team"],
                    away=r["away_team"],
                    home_goals=int(r["home_score"]),
                    away_goals=int(r["away_score"]),
                    neutral=r["neutral"].upper() == "TRUE",
                    weight=friendly_weight if r["tournament"] == "Friendly" else 1.0,
                )
            )
    out.sort(key=lambda m: m.date)
    return out


def tournaments(path: Path) -> dict[tuple[str, str, str], str]:
    with open(path, newline="") as fh:
        return {(r["date"], r["home_team"], r["away_team"]): r["tournament"] for r in csv.DictReader(fh)}
