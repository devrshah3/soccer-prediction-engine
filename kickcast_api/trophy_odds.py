"""Monte Carlo trophy odds (title / top 4 / relegation) for a domestic league season,
cached per (db, league, season) the same way predictions/cards are - refit only when
scripts/ingest.py bumps meta.data_version, not on every request (20,000 simulated
scorelines per remaining fixture is not free).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from kickcast_engine.models.simulation import StandingsState, simulate_season

from . import artifacts, settings
from .model_cache import cache_key, data_version
from .models import Match
from .predictions import get_model
from .serialize import latest_season, standings

N_SIMS = 20000

_cache: dict[tuple[str, str, str], tuple[str, dict]] = {}


def get_trophy_odds(session: Session, league_code: str, season: str | None = None) -> dict | None:
    if season is None:
        season = latest_season(session, league_code)
    if season is None:
        return None
    if settings.precomputed_only():
        return artifacts.get_payload(session, payload_key(league_code, season))  # never simulate per request

    version = data_version(session)
    key = cache_key(session, f"trophy:{season}", league_code)
    cached = _cache.get(key)
    if cached is not None and cached[0] == version:
        return cached[1]
    out = compute_trophy_odds(session, league_code, season)
    if out is not None:
        _cache[key] = (version, out)
    return out


def payload_key(league_code: str, season: str) -> str:
    return f"trophy:{league_code}:{season}"


def compute_trophy_odds(session: Session, league_code: str, season: str) -> dict | None:
    """The Monte Carlo itself (20,000 simulations per remaining fixture): development computes it
    lazily; production only ever runs it from the build step / nightly job."""
    model = get_model(session, league_code)
    if model is None:
        return None

    table = standings(session, league_code, season)
    if not table:
        return None
    state = {row["team_id"]: StandingsState(row["pts"], row["gf"], row["ga"]) for row in table}
    names = {row["team_id"]: row["team_name"] for row in table}
    remaining = [
        (m.home_team_id, m.away_team_id)
        for m in session.query(Match).filter(
            Match.league_code == league_code, Match.season == season, Match.status == "scheduled"
        )
    ]

    result = simulate_season(model, state, remaining, n_sims=N_SIMS, seed=42)
    teams = [{"team_id": t, "team_name": names.get(t, t), **r} for t, r in result.items()]
    teams.sort(key=lambda r: r["expected_position"])
    out = {
        "league_code": league_code, "season": season, "n_sims": N_SIMS,
        "remaining_fixtures": len(remaining), "model_as_of": model.as_of.isoformat() if model.as_of else None,
        "teams": teams,
    }
    return out
