"""Per-competition Dixon-Coles model cache.

Fitting is fast (well under a second for a big-5 league, per reports/backtest_openfootball.json)
but there is no reason to refit on every request. Each competition's model is cached in memory,
keyed by kickcast_api.models.Meta['data_version'] -- scripts/ingest.py bumps that value, so a
stale cache is detected and refit automatically the next time a prediction is requested, without
polling or a background scheduler.

Hyperparameters are the ones validated in reports/backtest_openfootball.json (domestic, tuned
2014-15->2020-21, held out 2021-22->2025-26) and reports/backtest_international.json
(international, tuned on 2024-25 competitive matches).
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from kickcast_engine.models.dixon_coles import DixonColes, MatchResult

from .model_cache import cache_key, data_version
from .models import Match

DOMESTIC_HYPERPARAMS = {"xi": 0.0022, "l2": 2.0}
INTERNATIONAL_HYPERPARAMS = {"xi": 0.001, "l2": 0.1}
INTERNATIONAL_FRIENDLY_WEIGHT = 0.5

_cache: dict[tuple[str, str, str], tuple[str, DixonColes]] = {}


def _training_matches(session: Session, league_code: str) -> list[MatchResult]:
    q = session.query(Match).filter(
        Match.league_code == league_code, Match.status == "finished",
        Match.home_goals.is_not(None), Match.away_goals.is_not(None),
    )
    rows = q.all()
    out = []
    for m in rows:
        assert m.home_goals is not None and m.away_goals is not None  # guaranteed by the filter above
        weight = 1.0
        if league_code == "international" and (m.round or "") == "Friendly":
            weight = INTERNATIONAL_FRIENDLY_WEIGHT
        out.append(
            MatchResult(
                date=m.date, home=m.home_team_id, away=m.away_team_id,
                home_goals=m.home_goals, away_goals=m.away_goals, neutral=m.neutral, weight=weight,
            )
        )
    return out


def get_model(session: Session, league_code: str) -> DixonColes | None:
    """Returns a fitted, cached DixonColes model for the competition, or None if there
    isn't enough finished-match history yet (DixonColes.fit needs >= 10 matches).

    "CL" (Champions League) is deliberately excluded even once it has >= 10 finished
    matches: fitting Dixon-Coles on CL results alone would mix teams from many different
    domestic leagues with no shared strength scale (a team's CL results say little about
    its true strength without a cross-league rating), and DOMESTIC_HYPERPARAMS were
    tuned/validated on single-league goals, not a cross-league cup - per the project's
    backtesting rule, an unvalidated model must not be presented as a real prediction.
    A real cross-league rating is future work, not something to ship quickly here.
    """
    if league_code == "CL":
        return None
    version = data_version(session)
    key = cache_key(session, "goals", league_code)
    cached = _cache.get(key)
    if cached is not None and cached[0] == version:
        return cached[1]

    matches = _training_matches(session, league_code)
    if len(matches) < 10:
        return None
    as_of = max(m.date for m in matches) + timedelta(days=1)
    params = INTERNATIONAL_HYPERPARAMS if league_code == "international" else DOMESTIC_HYPERPARAMS
    model = DixonColes(xi=params["xi"], l2=params["l2"]).fit(matches, as_of)
    _cache[key] = (version, model)
    return model
