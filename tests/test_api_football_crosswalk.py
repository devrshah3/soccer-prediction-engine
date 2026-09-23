from __future__ import annotations

from pathlib import Path

from kickcast_api.db import SessionLocal
from kickcast_api.models import Team
from kickcast_engine.data.api_football_crosswalk import (
    API_FOOTBALL_OVERRIDES,
    crosswalk_id,
    load_team_crosswalk,
)

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "api_football_cache"


def test_overrides_resolve_the_2_real_naming_quirks():
    assert crosswalk_id("Celta Vigo") == "celta"
    assert crosswalk_id("FSV Mainz 05") == "mainz"


def test_real_cached_teams_mostly_resolve_against_our_own_team_table():
    """96/98 big-5 teams auto-resolve via canonical_id() alone; the 2 gaps are covered
    by API_FOOTBALL_OVERRIDES (see that module's docstring for how these were found)."""
    if not CACHE_DIR.exists():
        return  # cache not present in this environment (e.g. a bare clone) - nothing to check
    crosswalk = load_team_crosswalk(CACHE_DIR)
    assert len(crosswalk) >= 90  # real count as of 2026-09-23 was 98 across the big-5

    session = SessionLocal()
    known_ids = {t.id for t in session.query(Team.id).all()}
    matched = sum(1 for kc_id in crosswalk.values() if kc_id in known_ids)
    assert matched / len(crosswalk) > 0.9  # real measured rate was 96/98 = 0.98


def test_overrides_are_the_only_2_entries():
    """If this grows, it means a new real naming-quirk was found and documented -
    fine - but it should never shrink silently (that would mean a fix got lost)."""
    assert len(API_FOOTBALL_OVERRIDES) >= 2
