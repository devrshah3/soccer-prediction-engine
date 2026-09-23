from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from kickcast_engine.models.cards import CardModel, CardObservation, LeakageError


def synthetic(n: int = 200, seed: int = 0) -> list[CardObservation]:
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(8)]
    disciplined = {t: r for t, r in zip(teams, np.linspace(1.0, 3.5, 8))}  # true home yellow rate
    out, d = [], date(2020, 8, 1)
    for _ in range(n):
        team = rng.choice(teams)
        is_home = bool(rng.integers(0, 2))
        rate = disciplined[team] * (1.0 if is_home else 1.1)
        yellow = int(rng.poisson(rate))
        red = int(rng.poisson(0.08))
        out.append(CardObservation(d, team, is_home, yellow, red))
        d += timedelta(days=1)
    return out


def test_fit_predict_shapes():
    obs = synthetic()
    m = CardModel().fit(obs, obs[-1].date + timedelta(days=1))
    p = m.predict("T0", True)
    assert p["expected_yellow"] > 0
    assert p["expected_red"] >= 0
    assert p["evidence"] in ("A", "B", "C")


def test_leakage_guard():
    obs = synthetic()
    with pytest.raises(LeakageError):
        CardModel().fit(obs, obs[-1].date)


def test_unseen_team_falls_back_to_league_average():
    obs = synthetic()
    m = CardModel().fit(obs, obs[-1].date + timedelta(days=1))
    p = m.predict("Unseen FC", True)
    assert p["evidence"] == "C"
    assert abs(p["expected_yellow"] - m.league_home_yellow) < 1e-3  # predict() rounds to 3dp


def test_model_recovers_relative_discipline_ranking():
    # T0 has the lowest true home-yellow rate (1.0), T7 the highest (3.5) - the fitted
    # model should preserve that ordering after shrinkage, given enough observations.
    obs = synthetic(n=800)
    m = CardModel(l2=1.0).fit(obs, obs[-1].date + timedelta(days=1))
    assert m.predict("T0", True)["expected_yellow"] < m.predict("T7", True)["expected_yellow"]


def test_shrinkage_pulls_thin_data_toward_league_mean():
    obs = synthetic(n=800)
    # a team with only one observation should sit closer to the league mean than one
    # with many observations, for the same underlying rate difference
    thin = [obs[0]] + [o for o in obs if o.team != obs[0].team]
    m_thin = CardModel(l2=6.0).fit(thin, max(o.date for o in thin) + timedelta(days=1))
    m_full = CardModel(l2=6.0).fit(obs, obs[-1].date + timedelta(days=1))
    team = thin[0].team
    d_thin = abs(m_thin.predict(team, True)["expected_yellow"] - m_thin.league_home_yellow)
    d_full = abs(m_full.predict(team, True)["expected_yellow"] - m_full.league_home_yellow)
    assert d_thin <= d_full
