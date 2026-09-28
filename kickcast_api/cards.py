"""Per-competition CardModel cache, same pattern as kickcast_api.predictions. Only
domestic leagues have card data (football-data.co.uk) - "international" has none, so
get_card_model returns None there and callers show "not available" rather than guessing.

Hyperparameters (xi=0.002, l2=15.0) are the ones validated in
reports/backtest_cards.json: tuned walk-forward on 2014-15->2020-21, beats a league
home/away-average baseline out-of-sample on 2021-22->2025-26 for yellow cards (both MAE
and Poisson NLL) and on red-card MAE; red-card Poisson NLL is a near-wash against
baseline (reds are rare enough that team-specific signal barely beats the league
average) - reported honestly in MORNING_REPORT.md rather than oversold.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from kickcast_engine.models.cards import CardModel, CardObservation

from . import artifacts, settings
from .model_cache import cache_key, data_version
from .models import Match, MatchStats

CARD_HYPERPARAMS = {"xi": 0.002, "l2": 15.0}

_cache: dict[tuple[str, str, str], tuple[str, CardModel]] = {}


def _observations(session: Session, league_code: str) -> list[CardObservation]:
    rows = (
        session.query(Match, MatchStats)
        .join(MatchStats, MatchStats.match_id == Match.id)
        .filter(
            Match.league_code == league_code, Match.status == "finished",
            MatchStats.home_yellow.is_not(None), MatchStats.away_yellow.is_not(None),
        )
        .all()
    )
    out = []
    for m, s in rows:
        out.append(CardObservation(m.date, m.home_team_id, True, int(s.home_yellow), int(s.home_red or 0)))
        out.append(CardObservation(m.date, m.away_team_id, False, int(s.away_yellow), int(s.away_red or 0)))
    return out


def get_card_model(session: Session, league_code: str) -> CardModel | None:
    if league_code == "international":  # no card data source for international matches yet
        return None
    version = data_version(session)
    key = cache_key(session, "cards", league_code)
    cached = _cache.get(key)
    if settings.precomputed_only():
        if cached is not None:
            return cached[1]
        bundle = artifacts.load_model("cards", league_code)
        if bundle is None:
            return None
        _cache[key] = (version, bundle["model"])
        return bundle["model"]
    if cached is not None and cached[0] == version:
        return cached[1]
    return fit_card_model(session, league_code)


def fit_card_model(session: Session, league_code: str, persist: bool = False) -> CardModel | None:
    version = data_version(session)
    key = cache_key(session, "cards", league_code)
    obs = _observations(session, league_code)
    if len(obs) < 20:
        return None
    as_of = max(o.date for o in obs) + timedelta(days=1)
    model = CardModel(xi=CARD_HYPERPARAMS["xi"], l2=CARD_HYPERPARAMS["l2"]).fit(obs, as_of)
    _cache[key] = (version, model)
    if persist:
        artifacts.save_model("cards", league_code, {"model": model})
    return model
