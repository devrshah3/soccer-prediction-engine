from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from kickcast_engine.models.dixon_coles import DixonColes, MatchResult
from kickcast_engine.models.simulation import StandingsState, relegation_slots, simulate_season


def fitted_model(n_teams: int = 8) -> DixonColes:
    rng = np.random.default_rng(0)
    teams = [f"T{i}" for i in range(n_teams)]
    strength = dict(zip(teams, np.linspace(-0.3, 0.3, n_teams)))
    out, d = [], date(2024, 8, 1)
    for _ in range(20):
        order = rng.permutation(teams)
        for h, a in zip(order[::2], order[1::2]):
            lam = np.exp(0.2 + strength[h] - strength[a] * 0.5)
            mu = np.exp(strength[a] - strength[h] * 0.5)
            out.append(MatchResult(d, h, a, int(rng.poisson(lam)), int(rng.poisson(mu))))
        d += timedelta(days=7)
    return DixonColes().fit(out, d + timedelta(days=1))


def test_no_remaining_fixtures_locks_in_current_order():
    model = fitted_model()
    state = {
        "T0": StandingsState(points=90, goals_for=80, goals_against=10),
        "T1": StandingsState(points=10, goals_for=10, goals_against=80),
    }
    result = simulate_season(model, state, [], n_sims=500, seed=1)
    assert result["T0"]["title_pct"] == 1.0
    assert result["T1"]["title_pct"] == 0.0
    assert result["T0"]["expected_position"] == 1.0
    assert result["T1"]["expected_position"] == 2.0


def test_probabilities_sum_correctly_across_teams():
    model = fitted_model(n_teams=8)
    teams = [f"T{i}" for i in range(8)]
    state = {t: StandingsState(points=10, goals_for=10, goals_against=10) for t in teams}
    remaining = [(teams[i], teams[(i + 1) % 8]) for i in range(8)] * 3
    result = simulate_season(model, state, remaining, n_sims=4000, seed=2)
    assert abs(sum(r["title_pct"] for r in result.values()) - 1.0) < 1e-6
    assert abs(sum(r["top4_pct"] for r in result.values()) - 4.0) < 1e-6
    assert abs(sum(r["relegation_pct"] for r in result.values()) - relegation_slots(8)) < 1e-6


def test_stronger_team_has_higher_title_chance_with_fixtures_remaining():
    model = fitted_model()
    teams = [f"T{i}" for i in range(8)]
    state = {t: StandingsState(points=0, goals_for=0, goals_against=0) for t in teams}
    remaining = [(teams[i], teams[(i + 3) % 8]) for i in range(8)] * 4
    result = simulate_season(model, state, remaining, n_sims=4000, seed=3)
    # T7 has the highest fitted attack strength (see fitted_model's linspace), T0 the lowest
    assert result["T7"]["title_pct"] > result["T0"]["title_pct"]
    assert result["T7"]["expected_points"] > result["T0"]["expected_points"]


def test_relegation_slots_by_league_size():
    assert relegation_slots(20) == 3
    assert relegation_slots(18) == 2
