"""Builds data/statsbomb_replays.json: a small, curated set of real StatsBomb Open Data
matches with a clean event timeline (goals/cards/subs with real minute and player),
for the keyless Historical Replay mode (step 7). Re-run only if you want to add more
matches; the committed JSON is what the API actually serves from.

StatsBomb Open Data is free, static, historical CC0-licensed data (not a live provider),
so caching it once into data/sb/ (gitignored) and then into this small derived JSON
(committed - it's a few KB, not the bulk raw data) doesn't violate the "never call
providers on page load" rule, which is about live/rate-limited feeds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kickcast_engine.data.statsbomb import load_events, load_matches

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "sb"
OUT = Path(__file__).resolve().parents[1] / "data" / "statsbomb_replays.json"

# Premier League 2015/16 (Leicester's title-winning season - the same season already
# validated in HANDOFF.md/reports/backtest_2015_16.json). Pick a handful of real,
# well-known, event-rich matches by date (deterministic, not curated by outcome).
COMPETITION_ID, SEASON_ID = 2, 27
N_MATCHES = 6


def event_type(e: dict) -> str:
    return e.get("type", {}).get("name", "")


def player_name(e: dict) -> str | None:
    p = e.get("player")
    return p.get("name") if p else None


def team_name(e: dict) -> str | None:
    t = e.get("team")
    return t.get("name") if t else None


def minute(e: dict) -> int:
    return int(e.get("minute", 0))


def extract_timeline(events: list[dict]) -> list[dict]:
    timeline = []
    for e in events:
        et = event_type(e)
        if et == "Shot" and e.get("shot", {}).get("outcome", {}).get("name") == "Goal":
            shot = e["shot"]
            timeline.append(
                {
                    "type": "goal", "minute": minute(e), "team": team_name(e), "player": player_name(e),
                    "detail": shot.get("type", {}).get("name"),
                }
            )
        elif et == "Own Goal Against":
            timeline.append({"type": "own_goal", "minute": minute(e), "team": team_name(e), "player": player_name(e)})
        elif et == "Bad Behaviour" and e.get("bad_behaviour", {}).get("card", {}).get("name") in ("Yellow Card", "Red Card", "Second Yellow"):
            timeline.append(
                {
                    "type": "card", "minute": minute(e), "team": team_name(e), "player": player_name(e),
                    "card": e["bad_behaviour"]["card"]["name"],
                }
            )
        elif et == "Substitution":
            sub = e.get("substitution", {})
            timeline.append(
                {
                    "type": "substitution", "minute": minute(e), "team": team_name(e),
                    "player_off": player_name(e), "player_on": sub.get("replacement", {}).get("name"),
                }
            )
    timeline.sort(key=lambda x: x["minute"])
    return timeline


def main() -> None:
    matches = load_matches(COMPETITION_ID, SEASON_ID, CACHE_DIR)
    chosen = matches[:N_MATCHES]
    out = []
    for m in chosen:
        events = load_events(m["source_id"], CACHE_DIR)
        timeline = extract_timeline(events)
        out.append(
            {
                "id": m["source_id"], "source": "statsbomb_open_data",
                "competition": m["competition"], "season": m["season"], "date": m["date"].isoformat(),
                "home": m["home"], "away": m["away"], "home_goals": m["home_goals"], "away_goals": m["away_goals"],
                "timeline": timeline,
            }
        )
        print(f"{m['date']} {m['home']} {m['home_goals']}-{m['away_goals']} {m['away']}: {len(timeline)} events")
    OUT.write_text(json.dumps({"source": "StatsBomb Open Data (CC0, historical only)", "matches": out}, indent=1))
    print(f"\nwrote {len(out)} matches to {OUT}")


if __name__ == "__main__":
    main()
