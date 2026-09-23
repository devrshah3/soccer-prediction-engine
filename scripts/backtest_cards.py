"""Walk-forward backtest for the card-rate model (step 3).

Same discipline as scripts/backtest_openfootball.py: tune xi/l2 only on 2014-15 to
2020-21 (pooled across the 5 leagues), report only on held-out 2021-22 to 2025-26.
Baseline is the league's home/away card average with no team-specific information
(computed from training data only, same leakage guard). Metrics: MAE (goals... cards,
easier to interpret than log-loss for a count) and Poisson negative log-likelihood
(lower = better, same convention as RPS/log-loss elsewhere in this repo).

Requires data/kickcast.db to already be populated (python scripts/ingest.py).
"""

from __future__ import annotations

import itertools
import json
import sys
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kickcast_api.db import SessionLocal
from kickcast_api.models import Match, MatchStats
from kickcast_engine.models.cards import CardModel, CardObservation

warnings.filterwarnings("ignore")
TUNE = (date(2014, 8, 1), date(2021, 6, 1))
TEST = (date(2021, 8, 1), date(2026, 6, 1))
LEAGUES = ["en.1", "es.1", "it.1", "de.1", "fr.1"]


def load_observations(league_code: str) -> list[CardObservation]:
    session = SessionLocal()
    try:
        rows = (
            session.query(Match, MatchStats)
            .join(MatchStats, MatchStats.match_id == Match.id)
            .filter(Match.league_code == league_code, Match.status == "finished", MatchStats.home_yellow.is_not(None))
            .all()
        )
        out = []
        for m, s in rows:
            if s.home_yellow is None or s.away_yellow is None:
                continue
            out.append(CardObservation(m.date, m.home_team_id, True, int(s.home_yellow), int(s.home_red or 0)))
            out.append(CardObservation(m.date, m.away_team_id, False, int(s.away_yellow), int(s.away_red or 0)))
        return out
    finally:
        session.close()


@dataclass
class Report:
    n: int
    mae_yellow: float
    mae_red: float
    poisson_nll_yellow: float
    poisson_nll_red: float

    def row(self) -> dict:
        return {
            "n": self.n, "mae_yellow": round(self.mae_yellow, 4), "mae_red": round(self.mae_red, 4),
            "poisson_nll_yellow": round(self.poisson_nll_yellow, 4), "poisson_nll_red": round(self.poisson_nll_red, 4),
        }


def poisson_nll(actual: np.ndarray, predicted: np.ndarray) -> float:
    lam = np.clip(predicted, 1e-6, None)
    from scipy.special import gammaln

    return float(np.mean(lam - actual * np.log(lam) + gammaln(actual + 1)))


def baseline_predict(train: list[CardObservation], team: str, is_home: bool) -> tuple[float, float]:
    rows = [o for o in train if o.is_home == is_home]
    if not rows:
        return 0.0, 0.0
    return float(np.mean([o.yellow for o in rows])), float(np.mean([o.red for o in rows]))


def walk_forward_cards(
    obs: list[CardObservation], start: date, end: date, predict_fn, block_days: int = 14
) -> Report:
    obs = sorted(obs, key=lambda o: o.date)
    blocks: dict[int, list[CardObservation]] = {}
    for o in obs:
        if start <= o.date < end:
            blocks.setdefault((o.date - start).days // block_days, []).append(o)
    py, pr, ay, ar = [], [], [], []
    for k in sorted(blocks):
        block = blocks[k]
        cutoff = min(o.date for o in block)
        train = [o for o in obs if o.date < cutoff]
        if len(train) < 20:
            continue
        pred = predict_fn(train, cutoff)
        for o in block:
            ey, er = pred(o.team, o.is_home)
            py.append(ey)
            pr.append(er)
            ay.append(o.yellow)
            ar.append(o.red)
    ay_arr, ar_arr, py_arr, pr_arr = map(np.array, (ay, ar, py, pr))
    return Report(
        n=len(ay),
        mae_yellow=float(np.mean(np.abs(py_arr - ay_arr))),
        mae_red=float(np.mean(np.abs(pr_arr - ar_arr))),
        poisson_nll_yellow=poisson_nll(ay_arr, py_arr),
        poisson_nll_red=poisson_nll(ar_arr, pr_arr),
    )


def ours(xi: float, l2: float):
    def fit(train: list[CardObservation], cutoff: date):
        mod = CardModel(xi=xi, l2=l2).fit(train, cutoff)

        def pred(team: str, is_home: bool) -> tuple[float, float]:
            p = mod.predict(team, is_home)
            return p["expected_yellow"], p["expected_red"]

        return pred

    return fit


def baseline(train: list[CardObservation], cutoff: date):
    return lambda team, is_home: baseline_predict(train, team, is_home)


def main() -> None:
    all_obs = {lg: load_observations(lg) for lg in LEAGUES}
    total_n = sum(len(v) for v in all_obs.values())
    print(f"loaded {total_n} team-match card observations across {len(LEAGUES)} leagues")

    grid = list(itertools.product([0.0005, 0.001, 0.002, 0.004], [2.0, 6.0, 15.0]))
    tuning = []
    for xi, l2 in grid:
        reps = [walk_forward_cards(all_obs[lg], *TUNE, ours(xi, l2)) for lg in LEAGUES]
        n = sum(r.n for r in reps)
        pooled_nll = sum(r.poisson_nll_yellow * r.n for r in reps) / n
        tuning.append({"xi": xi, "l2": l2, "n": n, "pooled_poisson_nll_yellow": round(pooled_nll, 4)})
    best = min(tuning, key=lambda t: t["pooled_poisson_nll_yellow"])
    print(f"tuned on 2014-15..2020-21 (pooled) -> xi={best['xi']}, l2={best['l2']}")

    out: dict = {"tuning": tuning, "best": {"xi": best["xi"], "l2": best["l2"]}, "test": {}}
    print(f"\n{'League':10}{'Model':12}{'n':>7}{'MAE_Y':>9}{'MAE_R':>9}{'NLL_Y':>9}{'NLL_R':>9}")
    pooled = {"baseline": [], "ours": []}
    for lg in LEAGUES:
        out["test"][lg] = {}
        for name, fit in [("baseline", baseline), ("ours", ours(best["xi"], best["l2"]))]:
            rep = walk_forward_cards(all_obs[lg], *TEST, fit)
            out["test"][lg][name] = rep.row()
            pooled[name].append(rep)
            r = rep.row()
            print(f"{lg:10}{name:12}{r['n']:7}{r['mae_yellow']:9.3f}{r['mae_red']:9.4f}{r['poisson_nll_yellow']:9.4f}{r['poisson_nll_red']:9.4f}")
    print("\nPooled held-out (2021-22..2025-26):")
    out["pooled_test"] = {}
    for name, reps in pooled.items():
        n = sum(r.n for r in reps)
        mae_y = sum(r.mae_yellow * r.n for r in reps) / n
        mae_r = sum(r.mae_red * r.n for r in reps) / n
        nll_y = sum(r.poisson_nll_yellow * r.n for r in reps) / n
        nll_r = sum(r.poisson_nll_red * r.n for r in reps) / n
        out["pooled_test"][name] = {
            "n": n, "mae_yellow": round(mae_y, 4), "mae_red": round(mae_r, 4),
            "poisson_nll_yellow": round(nll_y, 4), "poisson_nll_red": round(nll_r, 4),
        }
        print(f"  {name:10} n={n} MAE_yellow={mae_y:.3f} MAE_red={mae_r:.4f} NLL_yellow={nll_y:.4f} NLL_red={nll_r:.4f}")

    Path("reports/backtest_cards.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
