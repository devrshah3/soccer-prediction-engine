"""International backtest: tune on Sep 2024-Aug 2025, test on Sep 2025-Aug 2026 (incl. World Cup 2026)."""

from __future__ import annotations

import itertools
import json
import sys
import warnings
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from soccer_engine.data.international import load_results, tournaments
from soccer_engine.evaluation import outcome, walk_forward_window
from soccer_engine.models.dixon_coles import DixonColes

warnings.filterwarnings("ignore")
RESULTS = Path(sys.argv[1])
TOURN = tournaments(RESULTS)
TUNE = (date(2024, 9, 1), date(2025, 9, 1))
TEST = (date(2025, 9, 1), date(2026, 9, 1))


def tourn(m):
    return TOURN.get((m.date.isoformat(), m.home, m.away), "")


def competitive(m):
    return tourn(m) != "Friendly"


def ours(fw, xi, l2):
    def fit(train, cutoff):
        rows = [m if m.weight == 1.0 or fw == 0.5 else type(m)(**{**m.__dict__, "weight": fw}) for m in train]
        mod = DixonColes(xi=xi, l2=l2).fit(rows, cutoff)

        def pred(m):
            p = mod.predict(m.home, m.away, neutral=m.neutral)["probabilities"]
            return p["home"], p["draw"], p["away"]

        return pred

    return fit


def baseline(train, cutoff):
    c = Counter(outcome(m) for m in train[-3000:])
    p = tuple(c[i] / sum(c.values()) for i in range(3))
    return lambda m: p


def penaltyblog_dc(train, cutoff):
    import penaltyblog as pb

    tr = train
    w = pb.models.dixon_coles_weights([m.date for m in tr], 0.0005)
    mod = pb.models.DixonColesGoalModel(
        [m.home_goals for m in tr], [m.away_goals for m in tr], [m.home for m in tr], [m.away for m in tr], w
    )
    mod.fit()
    fallback = baseline(train, cutoff)

    def pred(m):
        try:
            return tuple(mod.predict(m.home, m.away).home_draw_away)
        except ValueError:
            return fallback(m)

    return pred


def main():
    ms = load_results(RESULTS, date(2016, 1, 1), friendly_weight=0.5)
    grid = list(itertools.product([1.0, 0.5, 0.25], [0.00025, 0.0005, 0.001], [0.1, 0.25, 0.5, 2.0]))
    tune = []
    for fw, xi, l2 in grid:
        r = walk_forward_window(ms, ours(fw, xi, l2), *TUNE, block_days=14, include=competitive).row()
        tune.append({"friendly_weight": fw, "xi": xi, "l2": l2, **r})
    best = min(tune, key=lambda r: r["rps"])
    print("tuned on 2024-25 competitive matches ->", {k: best[k] for k in ("friendly_weight", "xi", "l2")})

    models = {
        "Baseline (H/D/A rates)": baseline,
        "penaltyblog Dixon-Coles": penaltyblog_dc,
        "Ours (tuned)": ours(best["friendly_weight"], best["xi"], best["l2"]),
    }
    out = {"tuning": tune, "best": best, "test": {}}
    subsets = {
        "All competitive (2025-26)": competitive,
        "World Cup 2026": lambda m: tourn(m) == "FIFA World Cup",
        "UEFA qualifiers/NL (2025-26)": lambda m: "UEFA" in tourn(m) or (
            "qualification" in tourn(m) and m.home in EUROPE and m.away in EUROPE),
    }
    print(f"\n{'Test set':30}{'Model':28}{'n':>6}{'Acc':>7}{'RPS':>8}{'LogLoss':>9}{'ECE':>7}")
    for sname, inc in subsets.items():
        out["test"][sname] = {}
        for name, fit in models.items():
            rep = walk_forward_window(ms, fit, *TEST, block_days=7, include=inc)
            out["test"][sname][name] = {**rep.row(), "calibration": rep.calibration}
            r = rep.row()
            print(f"{sname:30}{name:28}{r['n']:6}{r['accuracy']:7.3f}{r['rps']:8.4f}{r['log_loss']:9.4f}{r['ece']:7.3f}")
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str))


EUROPE = set(json.loads(Path(__file__).resolve().parents[1].joinpath("data/uefa_teams.json").read_text()))

if __name__ == "__main__":
    main()
