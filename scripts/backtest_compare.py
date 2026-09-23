"""Head-to-head backtest on real StatsBomb 2015/16 seasons.

Protocol (no peeking):
  * weekly walk-forward refits, training only on matches before each week
  * hyperparameters (xG weight, shrinkage) tuned on the Premier League ONLY
  * La Liga, Serie A and Ligue 1 are untouched out-of-sample tests
"""

from __future__ import annotations

import itertools
import json
import sys
import warnings
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from soccer_engine.evaluation import outcome, walk_forward
from soccer_engine.models.dixon_coles import DixonColes, MatchResult

warnings.filterwarnings("ignore")
LEAGUES = {"Premier League": "England", "La Liga": "Spain", "Serie A": "Italy", "Ligue 1": "France"}


def load(summary_path: str, match_dir: str) -> dict[str, list[MatchResult]]:
    comp = {}
    for cid, name in [(2, "Premier League"), (11, "La Liga"), (12, "Serie A"), (7, "Ligue 1")]:
        for m in json.loads(Path(f"{match_dir}/matches_{cid}_27.json").read_text()):
            comp[m["match_id"]] = name
    out: dict[str, list[MatchResult]] = {k: [] for k in LEAGUES}
    for line in Path(summary_path).read_text().splitlines():
        s = json.loads(line)
        out[comp[s["match_id"]]].append(
            MatchResult(
                date.fromisoformat(s["date"]), s["home"], s["away"],
                s["home_goals"], s["away_goals"],
                home_xg=s["xg"]["home"] + s["pen_xg"]["home"],
                away_xg=s["xg"]["away"] + s["pen_xg"]["away"],
            )
        )
    return out


def freq_baseline(train, cutoff):
    c = Counter(outcome(m) for m in train)
    p = tuple(c[i] / len(train) for i in range(3))
    return lambda m: p


def penaltyblog_dc(train, cutoff):
    import penaltyblog as pb

    w = pb.models.dixon_coles_weights([m.date for m in train], 0.0019)
    mod = pb.models.DixonColesGoalModel(
        [m.home_goals for m in train], [m.away_goals for m in train],
        [m.home for m in train], [m.away for m in train], w,
    )
    mod.fit()
    return lambda m: tuple(mod.predict(m.home, m.away).home_draw_away)


def ours(xg_weight: float, l2: float):
    def fit(train, cutoff):
        mod = DixonColes(xg_weight=xg_weight, l2=l2).fit(train, cutoff)

        def pred(m):
            p = mod.predict(m.home, m.away)["probabilities"]
            return p["home"], p["draw"], p["away"]

        return pred

    return fit


def main() -> None:
    data = load(sys.argv[1], sys.argv[2])
    results: dict = {"tuning": [], "leagues": {}}

    # 1) tune on Premier League only
    grid = list(itertools.product([0.0, 0.25, 0.5, 0.75, 1.0], [0.1, 0.5, 1.0, 2.0]))
    best = None
    for w, l2 in grid:
        r = walk_forward(data["Premier League"], ours(w, l2)).row()
        results["tuning"].append({"xg_weight": w, "l2": l2, **r})
        if best is None or r["rps"] < best[2]["rps"]:
            best = (w, l2, r)
    assert best is not None
    bw, bl2, _ = best
    print(f"tuned on Premier League -> xg_weight={bw}, l2={bl2}")
    goals_l2 = min((t for t in results["tuning"] if t["xg_weight"] == 0.0), key=lambda t: t["rps"])["l2"]

    # 2) evaluate every model on every league
    models = {
        "Baseline (league H/D/A rates)": freq_baseline,
        "penaltyblog Dixon-Coles (goals)": penaltyblog_dc,
        f"Ours: goals only (l2={goals_l2})": ours(0.0, goals_l2),
        f"Ours: xG-blend (w={bw}, l2={bl2})": ours(bw, bl2),
    }
    for league, ms in data.items():
        results["leagues"][league] = {}
        for name, fit in models.items():
            rep = walk_forward(ms, fit)
            results["leagues"][league][name] = {**rep.row(), "calibration": rep.calibration}
    results["best"] = {"xg_weight": bw, "l2": bl2}

    print(f"\n{'League':16}{'Model':42}{'n':>5}{'Acc':>7}{'RPS':>8}{'LogLoss':>9}{'ECE':>7}")
    for league, rows in results["leagues"].items():
        tag = " (tuning)" if league == "Premier League" else " (out-of-sample)"
        for name, r in rows.items():
            print(f"{league[:16]:16}{name[:42]:42}{r['n']:5}{r['accuracy']:7.3f}{r['rps']:8.4f}"
                  f"{r['log_loss']:9.4f}{r['ece']:7.3f}")
        print(f"{'':16}{tag}")
    oos = [lg for lg in LEAGUES if lg != "Premier League"]
    print("\nOut-of-sample average (La Liga, Serie A, Ligue 1):")
    for name in models:
        rr = [results["leagues"][lg][name] for lg in oos]
        n = sum(r["n"] for r in rr)
        print(f"  {name:42} acc={sum(r['accuracy']*r['n'] for r in rr)/n:.3f} "
              f"rps={sum(r['rps']*r['n'] for r in rr)/n:.4f} "
              f"logloss={sum(r['log_loss']*r['n'] for r in rr)/n:.4f}")
    Path(sys.argv[3]).write_text(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
