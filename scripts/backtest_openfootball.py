"""Backtest on free openfootball history: does more seasons of warm-start data help,
and does our goals-only model (no xG available here) still beat penaltyblog and baseline
on a full season using a proper season-long warm start?
"""

from __future__ import annotations

import sys
import warnings
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kickcast_engine.data.openfootball import load_all_seasons, to_training_matches
from kickcast_engine.evaluation import outcome, walk_forward_window
from kickcast_engine.models.dixon_coles import DixonColes

warnings.filterwarnings("ignore")
REPO = Path(sys.argv[1])
TEST_SEASON = (date(2025, 8, 1), date(2026, 6, 1))  # last fully-played season


def baseline(train, cutoff):
    c = Counter(outcome(m) for m in train[-1000:])
    p = tuple(c[i] / sum(c.values()) for i in range(3))
    return lambda m: p


def ours(l2):
    def fit(train, cutoff):
        mod = DixonColes(xi=0.0015, l2=l2).fit(train, cutoff)

        def pred(m):
            p = mod.predict(m.home, m.away)["probabilities"]
            return p["home"], p["draw"], p["away"]

        return pred

    return fit


def penaltyblog_dc(train, cutoff):
    import penaltyblog as pb

    w = pb.models.dixon_coles_weights([m.date for m in train], 0.0015)
    mod = pb.models.DixonColesGoalModel(
        [m.home_goals for m in train], [m.away_goals for m in train],
        [m.home for m in train], [m.away for m in train], w,
    )
    mod.fit()
    fb = baseline(train, cutoff)

    def pred(m):
        try:
            return tuple(mod.predict(m.home, m.away).home_draw_away)
        except ValueError:
            return fb(m)

    return pred


def main():
    print(f"{'League':14}{'Warm-start':11}{'Model':28}{'n':>5}{'Acc':>7}{'RPS':>8}{'LogLoss':>9}")
    summary = {}
    for code in ["en.1", "es.1", "it.1", "de.1", "fr.1"]:
        rows = load_all_seasons(REPO, code)
        ms = to_training_matches(rows)
        for warm_label, cutoff_history in [("1 season", 380), ("full history", None)]:
            hist = ms if cutoff_history is None else [m for m in ms if m.date < TEST_SEASON[0]][-cutoff_history:]
            pool = hist + [m for m in ms if TEST_SEASON[0] <= m.date < TEST_SEASON[1]]
            for name, fit in [("Baseline", baseline), ("penaltyblog", penaltyblog_dc), ("Ours (l2=2.0)", ours(2.0))]:
                rep = walk_forward_window(pool, fit, *TEST_SEASON, block_days=7)
                r = rep.row()
                key = (code, name)
                summary.setdefault(key, {})[warm_label] = r
                print(f"{code:14}{warm_label:11}{name:28}{r['n']:5}{r['accuracy']:7.3f}{r['rps']:8.4f}{r['log_loss']:9.4f}")
        print()

    print("\n=== Does full-history warm start beat 1-season warm start? (RPS, lower=better) ===")
    for (code, name), by_warm in summary.items():
        if "1 season" in by_warm and "full history" in by_warm:
            d = by_warm["1 season"]["rps"] - by_warm["full history"]["rps"]
            print(f"{code:8}{name:28} 1-season RPS={by_warm['1 season']['rps']:.4f}  "
                  f"full-history RPS={by_warm['full history']['rps']:.4f}  improvement={d:+.4f}")


if __name__ == "__main__":
    main()
