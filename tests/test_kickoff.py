from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from kickcast_engine.data.kickoff import LEAGUE_TIMEZONES, to_utc_hhmm

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_arsenal_coventry_2026_08_21_matches_real_openfootball_data():
    """The exact case specified: Arsenal vs Coventry City, 2026-08-21, 20:00 local in
    London (BST/UTC+1 in August) must convert to 19:00 UTC. Read the real fixture from
    disk rather than hardcoding it, so this test breaks honestly if the source data
    (or the fixture's kickoff time) ever changes."""
    data = json.loads((REPO_ROOT / "data" / "openfootball_raw" / "2026-27" / "en.1.json").read_text())
    fixture = next(
        m for m in data["matches"]
        if m["date"] == "2026-08-21" and m["team1"] == "Arsenal FC" and m["team2"] == "Coventry City FC"
    )
    assert fixture["time"] == "20:00"  # sanity check on the real source data itself
    assert to_utc_hhmm(date(2026, 8, 21), fixture["time"], LEAGUE_TIMEZONES["en.1"]) == "19:00"


def test_winter_kickoff_is_gmt_not_bst():
    """London in January is GMT (UTC+0), not BST - a fixed +1 offset would be wrong."""
    assert to_utc_hhmm(date(2027, 1, 15), "15:00", "Europe/London") == "15:00"


def test_handles_hh_mm_ss_input():
    assert to_utc_hhmm(date(2026, 8, 21), "20:00:00", "Europe/London") == "19:00"


def test_madrid_is_one_hour_ahead_of_london_in_summer():
    # Spain observes CEST (UTC+2) while UK observes BST (UTC+1) in August.
    assert to_utc_hhmm(date(2026, 8, 21), "21:00", "Europe/Madrid") == "19:00"


def test_all_five_domestic_leagues_and_international_have_timezones_configured():
    for code in ("en.1", "es.1", "it.1", "de.1", "fr.1", "international"):
        assert code in LEAGUE_TIMEZONES
