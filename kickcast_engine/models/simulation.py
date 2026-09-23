"""Monte Carlo season simulation: given a fitted DixonColes model, a league's current
standings state, and its remaining fixtures, simulate the rest of the season N times
and report title / top-N / relegation probabilities.

Each simulated match's scoreline is sampled directly from the model's own
score_matrix() (the same Poisson-with-Dixon-Coles-correction distribution used for
match predictions), not just its 3-way W/D/L probabilities - so simulated final
goal difference (used for tie-breaks) reflects the model's actual goal expectations,
not an arbitrary tie-break assumption.

Ranking is fully vectorized (no per-simulation Python loop): pts/gd/gf are packed into
one sortable integer per (simulation, team) and ranked with a single np.argsort per
simulation batch.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dixon_coles import DixonColes


@dataclass(frozen=True)
class StandingsState:
    points: int
    goals_for: int
    goals_against: int


def simulate_season(
    model: DixonColes,
    standings_state: dict[str, StandingsState],
    remaining_fixtures: list[tuple[str, str]],
    n_sims: int = 20000,
    seed: int | None = None,
) -> dict[str, dict]:
    rng = np.random.default_rng(seed)
    teams = list(standings_state.keys())
    idx = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)

    pts = np.tile(np.array([standings_state[t].points for t in teams], dtype=np.int64), (n_sims, 1))
    gf = np.tile(np.array([standings_state[t].goals_for for t in teams], dtype=np.int64), (n_sims, 1))
    ga = np.tile(np.array([standings_state[t].goals_against for t in teams], dtype=np.int64), (n_sims, 1))

    g = model.max_goals + 1
    for home, away in remaining_fixtures:
        if home not in idx or away not in idx:
            continue  # fixture involves a team not in this table (shouldn't happen; skip defensively)
        lam, mu = model.expected_goals(home, away)
        mat = model.score_matrix(lam, mu)
        flat = mat.reshape(-1)
        flat = flat / flat.sum()
        draws = rng.choice(g * g, size=n_sims, p=flat)
        hg, ag = draws // g, draws % g
        hi, ai = idx[home], idx[away]
        gf[:, hi] += hg
        ga[:, hi] += ag
        gf[:, ai] += ag
        ga[:, ai] += hg
        pts[:, hi] += np.where(hg > ag, 3, np.where(hg == ag, 1, 0))
        pts[:, ai] += np.where(ag > hg, 3, np.where(hg == ag, 1, 0))

    gd = gf - ga
    # composite sortable key: bigger = better placed. Safe range for football (points < 1e4,
    # |gd| < 1e4, gf < 1e4): no realistic season can overflow or collide these bands.
    composite = pts.astype(np.int64) * 10**8 + (gd + 10**4).astype(np.int64) * 10**4 + gf.astype(np.int64)
    order = np.argsort(-composite, axis=1)  # order[:, 0] = index of the 1st-place team, per sim
    positions = np.empty_like(order)
    rows = np.arange(n_sims)[:, None]
    positions[rows, order] = np.arange(1, n_teams + 1)[None, :]

    out = {}
    for t in teams:
        p = positions[:, idx[t]]
        out[t] = {
            "title_pct": float(np.mean(p == 1)),
            "top4_pct": float(np.mean(p <= 4)),
            "relegation_pct": float(np.mean(p > n_teams - relegation_slots(n_teams))),
            "expected_position": round(float(np.mean(p)), 2),
            "expected_points": round(float(np.mean(pts[:, idx[t]])), 1),
        }
    return out


def relegation_slots(n_teams: int) -> int:
    """3 direct-relegation slots in a 20-team league, 2 in an 18-team one - a documented
    simplification: doesn't distinguish a direct slot from a playoff slot (e.g.
    Bundesliga's 16th-place playoff), just "bottom N"."""
    return 3 if n_teams >= 19 else 2
