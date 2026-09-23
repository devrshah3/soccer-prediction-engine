"""Stream StatsBomb event files and keep only a compact per-match summary.

Output (JSON lines): team xG (open play vs penalty), shots, goal timeline,
red cards, corners and whether each corner's possession produced a goal.
Raw event files are deleted after extraction to save disk.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data/events"


def summarize(match: dict, events: list[dict]) -> dict:
    home = match["home_team"]["home_team_name"]
    away = match["away_team"]["away_team_name"]
    side = {home: "home", away: "away"}
    other = {"home": "away", "away": "home"}
    s: dict = {
        "match_id": match["match_id"],
        "date": match["match_date"],
        "home": home,
        "away": away,
        "home_goals": match["home_score"],
        "away_goals": match["away_score"],
        "xg": {"home": 0.0, "away": 0.0},
        "pen_xg": {"home": 0.0, "away": 0.0},
        "shots": {"home": 0, "away": 0},
        "goals": [],
        "reds": [],
        "corners": [],
    }
    corner_poss: dict[int, dict] = {}
    for e in events:
        t = e["type"]["name"]
        team = e.get("team", {}).get("name")
        sd = side.get(team)
        if sd is None:
            continue
        minute, period = e["minute"], e["period"]
        if period > 4:  # ignore penalty shootouts
            continue
        if t == "Shot":
            shot = e["shot"]
            xg = float(shot.get("statsbomb_xg") or 0.0)
            if shot.get("type", {}).get("name") == "Penalty":
                s["pen_xg"][sd] += xg
            else:
                s["xg"][sd] += xg
            s["shots"][sd] += 1
            if shot["outcome"]["name"] == "Goal":
                s["goals"].append(
                    {
                        "side": sd,
                        "minute": minute,
                        "period": period,
                        "player": e.get("player", {}).get("name"),
                        "player_id": e.get("player", {}).get("id"),
                        "penalty": shot.get("type", {}).get("name") == "Penalty",
                        "body_part": shot.get("body_part", {}).get("name"),
                        "play_pattern": e.get("play_pattern", {}).get("name"),
                        "own_goal": False,
                    }
                )
                if e["possession"] in corner_poss:
                    corner_poss[e["possession"]]["goal"] = True
                    corner_poss[e["possession"]]["scorer"] = e.get("player", {}).get("name")
        elif t == "Own Goal For":
            s["goals"].append(
                {"side": sd, "minute": minute, "period": period, "player": None,
                 "player_id": None, "penalty": False, "body_part": None,
                 "play_pattern": e.get("play_pattern", {}).get("name"), "own_goal": True}
            )
        elif t == "Pass" and e["pass"].get("type", {}).get("name") == "Corner":
            c = {"side": sd, "minute": minute, "period": period, "goal": False, "scorer": None}
            s["corners"].append(c)
            corner_poss[e["possession"]] = c
        else:
            card = None
            if t == "Foul Committed":
                card = e.get("foul_committed", {}).get("card", {}).get("name")
            elif t == "Bad Behaviour":
                card = e.get("bad_behaviour", {}).get("card", {}).get("name")
            if card in ("Red Card", "Second Yellow"):
                s["reds"].append({"side": sd, "minute": minute, "period": period})
    # sanity: goal timeline must match the official score
    hg = sum(1 for g in s["goals"] if g["side"] == "home")
    ag = sum(1 for g in s["goals"] if g["side"] == "away")
    s["timeline_matches_score"] = (hg, ag) == (s["home_goals"], s["away_goals"])
    _ = other
    return s


def fetch_and_summarize(match: dict) -> dict | None:
    for attempt in range(3):
        try:
            r = requests.get(f"{BASE}/{match['match_id']}.json", timeout=60)
            r.raise_for_status()
            return summarize(match, r.json())
        except Exception as exc:  # noqa: BLE001 - retry then report
            if attempt == 2:
                print(f"failed {match['match_id']}: {exc}", file=sys.stderr)
    return None


def main(match_files: list[str], out_path: str, workers: int = 16) -> None:
    out = Path(out_path)
    done = set()
    if out.exists():
        done = {json.loads(line)["match_id"] for line in out.read_text().splitlines()}
    matches = []
    for f in match_files:
        matches += [m for m in json.loads(Path(f).read_text()) if m["match_id"] not in done]
    print(f"{len(done)} cached, {len(matches)} to fetch", flush=True)
    with out.open("a") as fh, ThreadPoolExecutor(workers) as pool:
        for i, s in enumerate(pool.map(fetch_and_summarize, matches), 1):
            if s:
                fh.write(json.dumps(s) + "\n")
            if i % 200 == 0:
                print(f"{i}/{len(matches)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[2:], sys.argv[1])
