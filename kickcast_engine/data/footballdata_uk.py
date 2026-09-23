"""football-data.co.uk loader (free, no key; see scripts/fetch_footballdata_uk.py for the
download step and the licensing note there -- no formal terms-of-use text was found on the
site restricting research/personal use, so we cache once locally and credit the source).

Column layout has changed over the years, so every column's presence is detected per file
rather than assumed. Confirmed from data/footballdata_uk/manifest.json + the actual CSVs
(big-5 leagues, 2005-06 to 2026-27):
  - Match stats (shots/fouls/corners) and cards (HY/AY/HR/AR): present every season for
    en.1/es.1/it.1/de.1; for fr.1, shots/fouls/corners are missing in 2005-06 and 2006-07
    (cards ARE present from 2005-06 onward everywhere).
  - Closing odds: no true closing-line columns before 2012-13 (only a single pre-match
    snapshot, e.g. B365H/D/A). From 2012-13, Pinnacle closing (PSCH/PSCD/PSCA) is present.
    From 2019-20, a fuller closing set including the multi-book average (AvgCH/AvgCD/AvgCA)
    is present. `closing_odds()` prefers AvgC*, then PSC*, else reports unavailable.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from ..models.dixon_coles import MatchResult
from .team_aliases import canonical

SOURCE = "football-data.co.uk"

# football-data.co.uk league code -> kickcast league code (matches kickcast_engine.data.openfootball.LEAGUES)
FD_TO_KC = {"E0": "en.1", "SP1": "es.1", "I1": "it.1", "D1": "de.1", "F1": "fr.1"}

STAT_COLUMNS = {
    "HS": "home_shots", "AS": "away_shots",
    "HST": "home_shots_on_target", "AST": "away_shots_on_target",
    "HF": "home_fouls", "AF": "away_fouls",
    "HC": "home_corners", "AC": "away_corners",
}
CARD_COLUMNS = {"HY": "home_yellow", "AY": "away_yellow", "HR": "home_red", "AR": "away_red"}
# preference order: (home_col, draw_col, away_col, label)
CLOSING_ODDS_SETS = [
    ("AvgCH", "AvgCD", "AvgCA", "market_average_closing"),
    ("PSCH", "PSCD", "PSCA", "pinnacle_closing"),
]


def _parse_date(s: str) -> date:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()  # noqa: DTZ007 - calendar match date, no tz involved
        except ValueError:
            continue
    raise ValueError(f"unrecognised date format: {s!r}")


def _float(row: dict, col: str) -> float | None:
    v = row.get(col)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def margin_removed_probs(odds_h: float, odds_d: float, odds_a: float) -> tuple[float, float, float]:
    """Convert decimal odds to probabilities with the bookmaker overround/margin removed."""
    inv = (1 / odds_h, 1 / odds_d, 1 / odds_a)
    total = sum(inv)
    return (inv[0] / total, inv[1] / total, inv[2] / total)


def detect_columns(header: Sequence[str]) -> dict:
    has_stats = all(c in header for c in STAT_COLUMNS)
    has_cards = all(c in header for c in CARD_COLUMNS)
    odds_source = None
    for h, d, a, label in CLOSING_ODDS_SETS:
        if h in header and d in header and a in header:
            odds_source = label
            break
    return {"has_stats": has_stats, "has_cards": has_cards, "closing_odds_source": odds_source}


def load_season(repo_dir: Path, fd_code: str, season: str) -> list[dict]:
    """Raw rows for one league-season, e.g. fd_code='E0', season='2005-06'."""
    f = repo_dir / season / f"{fd_code}.csv"
    if not f.exists():
        return []
    with open(f, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        cols = detect_columns(header)
        out = []
        for r in reader:
            if not r.get("HomeTeam") or not r.get("Date"):
                continue
            hg, ag = r.get("FTHG"), r.get("FTAG")
            row = {
                "source": SOURCE,
                "kickcast_league": FD_TO_KC[fd_code],
                "fd_code": fd_code,
                "season": season,
                "date": _parse_date(r["Date"]).isoformat(),
                "home": canonical(r["HomeTeam"]),
                "away": canonical(r["AwayTeam"]),
                "home_raw": r["HomeTeam"],
                "away_raw": r["AwayTeam"],
                "home_goals": int(hg) if hg not in (None, "") else None,
                "away_goals": int(ag) if ag not in (None, "") else None,
                "status": "finished" if hg not in (None, "") and ag not in (None, "") else "scheduled",
            }
            if cols["has_stats"]:
                for src, dst in STAT_COLUMNS.items():
                    row[dst] = _float(r, src)
            if cols["has_cards"]:
                for src, dst in CARD_COLUMNS.items():
                    row[dst] = _float(r, src)
            if cols["closing_odds_source"]:
                h, d, a, label = next(
                    s for s in CLOSING_ODDS_SETS if s[3] == cols["closing_odds_source"]
                )
                oh, od, oa = _float(r, h), _float(r, d), _float(r, a)
                if oh and od and oa:
                    row["closing_odds"] = {"home": oh, "draw": od, "away": oa, "source": label}
            out.append(row)
    out.sort(key=lambda r: str(r["date"]))
    return out


def load_all_seasons(repo_dir: Path, fd_code: str) -> list[dict]:
    rows = []
    for season_dir in sorted(repo_dir.glob("20??-??")):
        rows += load_season(repo_dir, fd_code, season_dir.name)
    return rows


def to_training_matches(rows: list[dict]) -> list[MatchResult]:
    return [
        MatchResult(date.fromisoformat(r["date"]), r["home"], r["away"], r["home_goals"], r["away_goals"])
        for r in rows
        if r["status"] == "finished"
    ]


def column_coverage_report(repo_dir: Path) -> dict:
    """Per league-season: which stat/card/closing-odds columns are actually present."""
    report: dict[str, dict] = {}
    for fd_code in FD_TO_KC:
        report[fd_code] = {}
        for season_dir in sorted(repo_dir.glob("20??-??")):
            f = season_dir / f"{fd_code}.csv"
            if not f.exists():
                continue
            with open(f, newline="", encoding="utf-8-sig") as fh:
                header = next(csv.reader(fh))
            report[fd_code][season_dir.name] = detect_columns(header)
    return report
