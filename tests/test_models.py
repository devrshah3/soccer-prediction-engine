from datetime import date, timedelta

import numpy as np
import pytest

from kickcast_engine.evaluation import rps, walk_forward
from kickcast_engine.models.dixon_coles import DixonColes, LeakageError, MatchResult


def synthetic(n_rounds: int = 12, seed: int = 0) -> list[MatchResult]:
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(8)]
    strength = {t: s for t, s in zip(teams, np.linspace(-0.4, 0.4, 8))}
    out, d = [], date(2020, 8, 1)
    for r in range(n_rounds):
        order = rng.permutation(teams)
        for h, a in zip(order[::2], order[1::2]):
            lam = np.exp(0.25 + strength[h] - strength[a] * 0.5)
            mu = np.exp(strength[a] - strength[h] * 0.5)
            out.append(MatchResult(d, h, a, int(rng.poisson(lam)), int(rng.poisson(mu)),
                                   home_xg=float(lam), away_xg=float(mu)))
        d += timedelta(days=7)
    return out


def test_probabilities_are_valid():
    ms = synthetic()
    m = DixonColes().fit(ms, ms[-1].date + timedelta(days=1))
    p = m.predict("T7", "T0")
    probs = p["probabilities"]
    assert abs(sum(probs.values()) - 1) < 1e-9
    assert all(0 < v < 1 for v in probs.values())
    assert probs["home"] > probs["away"]  # strongest team at home vs weakest
    assert p["evidence"] == "A"


def test_leakage_guard():
    ms = synthetic()
    with pytest.raises(LeakageError):
        DixonColes().fit(ms, ms[-1].date)  # cutoff equal to a training date


def test_unseen_team_is_flagged():
    ms = synthetic()
    p = DixonColes().fit(ms, ms[-1].date + timedelta(days=1)).predict("T1", "Newcomers FC")
    assert p["evidence"] == "C"


def test_neutral_venue_removes_home_edge():
    ms = synthetic()
    m = DixonColes().fit(ms, ms[-1].date + timedelta(days=1))
    assert m.expected_goals("T3", "T4", neutral=True)[0] < m.expected_goals("T3", "T4")[0]


def test_xg_blend_fits():
    ms = synthetic()
    p = DixonColes(xg_weight=0.75, l2=2.0).fit(ms, ms[-1].date + timedelta(days=1)).predict("T5", "T2")
    assert abs(sum(p["probabilities"].values()) - 1) < 1e-9


def test_rps_known_values():
    assert rps([1, 0, 0], 0) == 0
    assert rps([0, 0, 1], 0) == 1
    assert abs(rps([1 / 3] * 3, 1) - 1 / 9) < 1e-12


def test_walk_forward_never_trains_on_future():
    ms = synthetic()
    seen = []

    def fit(train, cutoff):
        assert max(m.date for m in train) < cutoff
        seen.append(cutoff)
        return lambda m: (0.45, 0.27, 0.28)

    rep = walk_forward(ms, fit, warmup=20)
    assert rep.n == len(ms) - 20 and len(seen) > 5


def test_standings_matches_manual_table():
    from kickcast_engine.data.openfootball import standings

    rows = [
        {"season": "24-25", "status": "finished", "home": "A", "away": "B", "home_goals": 2, "away_goals": 1},
        {"season": "24-25", "status": "finished", "home": "B", "away": "A", "home_goals": 0, "away_goals": 0},
        {"season": "24-25", "status": "finished", "home": "A", "away": "C", "home_goals": 1, "away_goals": 1},
        {"season": "24-25", "status": "scheduled", "home": "B", "away": "C", "home_goals": None, "away_goals": None},
    ]
    tbl = {t["team"]: t for t in standings(rows, "24-25")}
    assert tbl["A"]["played"] == 3 and tbl["A"]["pts"] == 5  # W(home) + D(away) + D(home)
    assert tbl["B"]["played"] == 2 and tbl["B"]["pts"] == 1  # L(away) + D(home)
    assert tbl["C"]["played"] == 1 and tbl["C"]["pts"] == 1
    assert all(r["status"] != "scheduled" or r["home_goals"] is None for r in rows)  # unplayed excluded


def test_openfootball_no_future_leakage_in_training_set():
    from datetime import date

    from kickcast_engine.data.openfootball import to_training_matches

    rows = [
        {"date": "2026-09-20", "home": "A", "away": "B", "home_goals": 2, "away_goals": 0, "status": "finished"},
        {"date": "2026-10-10", "home": "A", "away": "C", "home_goals": None, "away_goals": None, "status": "scheduled"},
    ]
    ms = to_training_matches(rows)
    assert len(ms) == 1 and ms[0].date == date(2026, 9, 20)
