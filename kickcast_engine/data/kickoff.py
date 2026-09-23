"""Convert each league's LOCALLY-STORED kickoff time to UTC, DST-aware.

openfootball's `time` field is the match's LOCAL wall-clock kickoff time in that
league's own country, not UTC - confirmed real: Arsenal vs Coventry City, 2026-08-21,
is stored as "20:00" (data/openfootball_raw/2026-27/en.1.json), and 20:00 in London in
August is British Summer Time (UTC+1), i.e. 19:00 UTC - see
tests/test_kickoff.py::test_arsenal_coventry_2026_08_21_matches_real_openfootball_data.
data/nations_league_2026_27_md1_4.json's `kickoff_cet` field says directly that it's
CET/CEST (Europe/Paris observes the same CET/CEST rules).

Both scripts/ingest.py's domestic and international ingestion call `to_utc_hhmm` before
writing Match.kickoff, so the stored value is always UTC. The DB's `date` column keeps
the competition's own nominal match date (the date a fixture is grouped under, e.g. for
standings/round purposes) even in the rare case a very-late local kickoff's UTC instant
would fall on the next calendar day - only the time-of-day is converted, not the date.
This is deliberate (competitions themselves define "the date of the match" by local
kickoff, not by UTC), and worth knowing if a UTC-midnight-crossing fixture ever looks
odd: the kickoff time is still correct UTC, just paired with the local match date.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")

LEAGUE_TIMEZONES: dict[str, str] = {
    "en.1": "Europe/London",
    "es.1": "Europe/Madrid",
    "it.1": "Europe/Rome",
    "de.1": "Europe/Berlin",
    "fr.1": "Europe/Paris",
    "international": "Europe/Paris",  # Nations League's kickoff_cet - see module docstring
}


def to_utc_hhmm(local_date: date, local_time: str, tz_name: str) -> str:
    """"20:00" (or "20:00:00") local wall-clock time on `local_date` in the zone named by
    `tz_name` -> "HH:MM" in UTC, DST-aware (uses the real offset in effect on that exact
    date, not a fixed UTC+N)."""
    parts = local_time.split(":")
    hh, mm = int(parts[0]), int(parts[1])
    local_dt = datetime(local_date.year, local_date.month, local_date.day, hh, mm, tzinfo=ZoneInfo(tz_name))
    utc_dt = local_dt.astimezone(UTC)
    return f"{utc_dt.hour:02d}:{utc_dt.minute:02d}"
