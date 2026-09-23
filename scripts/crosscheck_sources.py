"""Cross-check openfootball vs football-data.co.uk scores on matches both sources cover.

Joins on (canonical home id, canonical away id, date +/- 1 day) and compares full-time
scores. Reports how many matches were compared and how many disagreed -- disagreements are
printed, not hidden.

Usage: python scripts/crosscheck_sources.py [data/openfootball_raw] [data/footballdata_uk] [out.json]
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kickcast_engine.data.footballdata_uk import FD_TO_KC
from kickcast_engine.data.footballdata_uk import load_all_seasons as load_fd
from kickcast_engine.data.openfootball import load_all_seasons as load_of
from kickcast_engine.data.team_aliases import canonical

OF_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/openfootball_raw")
FD_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/footballdata_uk")
OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("reports/crosscheck_sources.json")


def main() -> None:
    report: dict[str, dict] = {}
    total_compared = total_disagree = 0
    all_disagreements = []

    for fd_code, kc_code in FD_TO_KC.items():
        of_rows = [r for r in load_of(OF_DIR, kc_code) if r["status"] == "finished"]
        fd_rows = [r for r in load_fd(FD_DIR, fd_code) if r["status"] == "finished"]

        # index fd matches by team pair -> list of (date, hg, ag)
        fd_by_pair: dict[tuple[str, str], list[tuple[date, int, int]]] = {}
        for r in fd_rows:
            key = (r["home"], r["away"])
            fd_by_pair.setdefault(key, []).append(
                (date.fromisoformat(r["date"]), r["home_goals"], r["away_goals"])
            )

        compared = disagree = 0
        disagreements = []
        for r in of_rows:
            key = (canonical(r["home"]), canonical(r["away"]))
            candidates = fd_by_pair.get(key)
            if not candidates:
                continue
            of_d = date.fromisoformat(r["date"])
            match = next((c for c in candidates if abs((c[0] - of_d).days) <= 1), None)
            if match is None:
                continue
            compared += 1
            fd_d, fd_hg, fd_ag = match
            if (r["home_goals"], r["away_goals"]) != (fd_hg, fd_ag):
                disagree += 1
                disagreements.append(
                    {
                        "league": kc_code, "home": r["home"], "away": r["away"],
                        "openfootball_date": r["date"], "footballdata_date": fd_d.isoformat(),
                        "openfootball_score": [r["home_goals"], r["away_goals"]],
                        "footballdata_score": [fd_hg, fd_ag],
                    }
                )

        report[kc_code] = {"compared": compared, "disagreements": disagree}
        total_compared += compared
        total_disagree += disagree
        all_disagreements += disagreements
        print(f"{kc_code:6} compared={compared:5} disagreements={disagree}")

    print(f"\nTOTAL compared={total_compared} disagreements={total_disagree}")
    for d in all_disagreements:
        print(" ", d)

    OUT.write_text(
        json.dumps(
            {"by_league": report, "total_compared": total_compared,
             "total_disagreements": total_disagree, "disagreements": all_disagreements},
            indent=1,
        )
    )
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
