"""Multi-season backtest: does more warm-start history help, especially early-season?

Protocol (no peeking):
  * xi/l2 tuned via walk-forward ONLY on 2014-08-01 to 2021-08-01 (pooled across the 5 big
    leagues, weighted by match count), using the full-history training arm (what would ship).
  * Reported numbers are ONLY from the held-out 2021-08-01 to 2026-07-01 window.
  * "Full history" = football-data.co.uk (2005-06 onward, free, no xG) fills each league's
    seasons before openfootball's own coverage starts (which varies by league -- confirmed
    from the files on disk: en.1/de.1 from 2010-11, es.1 from 2012-13, it.1 from 2013-14,
    fr.1 from 2014-15); openfootball is preferred wherever both sources cover a match, since
    that's what the live site ingests (see scripts/crosscheck_sources.py for how well the two
    sources agree where they overlap: 23,562 matches compared, 2 disagreements).
  * "1-season warm start" = at each cutoff, train ONLY on matches since Aug 1 of the season in
    progress (falls back to a frequency baseline when that's under 10 matches -- DixonColes
    needs >=10 to fit -- which is exactly the early-season cold-start problem this test is
    checking whether more history fixes).
  * Early-season subset = matchday 1-6 (parsed from openfootball's own "Matchday N" round
    field), reported separately from the full held-out set.
  * Extra arm: bookmaker closing odds (football-data.co.uk, margin/overround removed), only
    over the subset of held-out matches where a closing line actually exists.
"""

from __future__ import annotations

import itertools
import json
import re
import sys
import warnings
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kickcast_engine.data.footballdata_uk import (
    FD_TO_KC,
    margin_removed_probs,
)
from kickcast_engine.data.footballdata_uk import (
    load_all_seasons as load_fd,
)
from kickcast_engine.data.openfootball import LEAGUES
from kickcast_engine.data.openfootball import load_all_seasons as load_of
from kickcast_engine.data.team_aliases import canonical
from kickcast_engine.evaluation import Report, outcome, rps, score, walk_forward_window
from kickcast_engine.models.dixon_coles import DixonColes, MatchResult

warnings.filterwarnings("ignore")

OF_DIR = Path("data/openfootball_raw")
FD_DIR = Path("data/footballdata_uk")
KC_TO_FD = {v: k for k, v in FD_TO_KC.items()}
TUNE = (date(2014, 8, 1), date(2021, 8, 1))
TEST = (date(2021, 8, 1), date(2026, 7, 1))
BOOTSTRAP_B = 10000


def season_start(d: date) -> date:
    return date(d.year, 8, 1) if d.month >= 8 else date(d.year - 1, 8, 1)


def matchday_num(round_str: str | None) -> int | None:
    if not round_str:
        return None
    m = re.search(r"\d+", round_str)
    return int(m.group()) if m else None


class LeagueData:
    def __init__(self, kc_code: str):
        self.kc_code = kc_code
        fd_code = KC_TO_FD[kc_code]
        of_rows = [r for r in load_of(OF_DIR, kc_code) if r["status"] == "finished"]
        fd_rows = [r for r in load_fd(FD_DIR, fd_code) if r["status"] == "finished"]
        self.of_start_date = min(date.fromisoformat(r["date"]) for r in of_rows)
        self.of_start_season = min(r["season"] for r in of_rows)

        merged = []
        for r in fd_rows:
            d = date.fromisoformat(r["date"])
            if d < self.of_start_date:
                merged.append(MatchResult(d, r["home"], r["away"], r["home_goals"], r["away_goals"]))
        for r in of_rows:
            merged.append(
                MatchResult(
                    date.fromisoformat(r["date"]), canonical(r["home"]), canonical(r["away"]),
                    r["home_goals"], r["away_goals"],
                )
            )
        merged.sort(key=lambda m: m.date)
        self.matches = merged
        self.n_pre_openfootball = sum(1 for m in merged if m.date < self.of_start_date)

        self.matchday = {
            (date.fromisoformat(r["date"]), canonical(r["home"]), canonical(r["away"])): matchday_num(r.get("round"))
            for r in of_rows
        }

        odds_by_pair: dict[tuple[str, str], list[tuple[date, dict]]] = {}
        for r in fd_rows:
            if r.get("closing_odds"):
                odds_by_pair.setdefault((r["home"], r["away"]), []).append(
                    (date.fromisoformat(r["date"]), r["closing_odds"])
                )
        self.odds_by_pair = odds_by_pair

    def is_early_season(self, m: MatchResult) -> bool:
        md = self.matchday.get((m.date, m.home, m.away))
        return md is not None and md <= 6

    def closing_probs(self, m: MatchResult) -> tuple[float, float, float] | None:
        for d, o in self.odds_by_pair.get((m.home, m.away), []):
            if abs((d - m.date).days) <= 1:
                return margin_removed_probs(o["home"], o["draw"], o["away"])
        return None


def baseline(train: list[MatchResult], cutoff) -> object:
    if len(train) < 10:
        return lambda m: (0.44, 0.27, 0.29)  # generic big-5-league prior, no data to condition on
    c = Counter(outcome(m) for m in train[-2000:])
    total = sum(c.values())
    p = tuple(c[i] / total for i in range(3))
    return lambda m: p


def penaltyblog_dc(xi: float):
    def fit(train, cutoff):
        import penaltyblog as pb

        if len(train) < 10:
            return baseline(train, cutoff)
        w = pb.models.dixon_coles_weights([m.date for m in train], xi)
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

    return fit


def ours_full_history(xi: float, l2: float):
    def fit(train, cutoff):
        if len(train) < 10:
            return baseline(train, cutoff)
        mod = DixonColes(xi=xi, l2=l2).fit(train, cutoff)

        def pred(m):
            p = mod.predict(m.home, m.away)["probabilities"]
            return p["home"], p["draw"], p["away"]

        return pred

    return fit


def ours_1season(xi: float, l2: float):
    def fit(train, cutoff):
        s0 = season_start(cutoff)
        season_train = [m for m in train if m.date >= s0]
        if len(season_train) < 10:
            return baseline(train, cutoff)
        mod = DixonColes(xi=xi, l2=l2).fit(season_train, cutoff)

        def pred(m):
            p = mod.predict(m.home, m.away)["probabilities"]
            return p["home"], p["draw"], p["away"]

        return pred

    return fit


def tune(leagues: dict[str, LeagueData]) -> dict:
    grid = list(itertools.product([0.0008, 0.0015, 0.0022], [0.5, 1.0, 2.0, 4.0]))
    rows = []
    for xi, l2 in grid:
        total_n, total_rps_weighted = 0, 0.0
        for ld in leagues.values():
            rep = walk_forward_window(ld.matches, ours_full_history(xi, l2), *TUNE, block_days=14)
            total_n += rep.n
            total_rps_weighted += rep.rps * rep.n
        pooled_rps = total_rps_weighted / total_n
        rows.append({"xi": xi, "l2": l2, "n": total_n, "rps": round(pooled_rps, 5)})
        print(f"  tune xi={xi:<8} l2={l2:<5} n={total_n:6} pooled_rps={pooled_rps:.5f}")
    best = min(rows, key=lambda r: r["rps"])
    return {"grid": rows, "best": best}


def paired_bootstrap(rps_ours: dict[tuple, float], rps_other: dict[tuple, float], seed: int = 0) -> dict:
    keys = sorted(set(rps_ours) & set(rps_other))
    diffs = np.array([rps_other[k] - rps_ours[k] for k in keys])  # positive = ours better
    rng = np.random.default_rng(seed)
    n = len(diffs)
    idx = rng.integers(0, n, size=(BOOTSTRAP_B, n))
    boot_means = diffs[idx].mean(axis=1)
    lo, hi = np.percentile(boot_means, [2.5, 97.5])
    return {"n": n, "mean_rps_improvement": float(diffs.mean()), "ci_low": float(lo), "ci_high": float(hi)}


def rps_by_key(rep: Report) -> dict[tuple, float]:
    return {(p["match"].date, p["match"].home, p["match"].away): rps(p["p"], p["o"]) for p in rep.predictions}


def run_bookmaker_arm(leagues: dict[str, LeagueData]) -> tuple[Report, Report]:
    """Returns (full-set report, early-season-subset report) using only matches with odds."""
    preds_all, preds_early = [], []
    for ld in leagues.values():
        for m in ld.matches:
            if not (TEST[0] <= m.date < TEST[1]):
                continue
            probs = ld.closing_probs(m)
            if probs is None:
                continue
            p = np.array(probs)
            entry = {"match": m, "p": p, "o": outcome(m), "cutoff": m.date}
            preds_all.append(entry)
            if ld.is_early_season(m):
                preds_early.append(entry)
    return score(preds_all), score(preds_early)


def main() -> None:
    print("Loading + merging per-league history (football-data.co.uk fills pre-openfootball seasons)...")
    leagues = {kc: LeagueData(kc) for kc in LEAGUES}
    for kc, ld in leagues.items():
        print(f"  {kc:6} total={len(ld.matches):5} pre-openfootball(fd-only)={ld.n_pre_openfootball:5} "
              f"openfootball-from={ld.of_start_season}")

    print("\nTuning xi/l2 on 2014-08-01..2021-08-01 (pooled across leagues, full-history arm)...")
    tuning = tune(leagues)
    xi, l2 = tuning["best"]["xi"], tuning["best"]["l2"]
    print(f"-> best xi={xi} l2={l2} (pooled tuning RPS={tuning['best']['rps']})")

    models = {
        "Baseline (H/D/A rates)": baseline,
        "penaltyblog Dixon-Coles": penaltyblog_dc(xi),
        "Ours: 1-season warm start": ours_1season(xi, l2),
        "Ours: full-history warm start": ours_full_history(xi, l2),
    }

    results: dict = {"tuning": tuning, "xi": xi, "l2": l2, "per_league": {}, "pooled": {}, "bootstrap": {}}

    print(f"\n{'League':8}{'Model':32}{'n':>6}{'Acc':>7}{'RPS':>8}{'LogLoss':>9}{'ECE':>7}   (held-out 2021-22..2025-26)")
    all_reports: dict[str, dict[str, Report]] = {}
    all_early: dict[str, dict[str, Report]] = {}
    for kc, ld in leagues.items():
        results["per_league"][kc] = {"full": {}, "early_season": {}}
        all_reports[kc], all_early[kc] = {}, {}
        for name, fit in models.items():
            rep_full = walk_forward_window(ld.matches, fit, *TEST, block_days=7)
            rep_early = walk_forward_window(ld.matches, fit, *TEST, block_days=7, include=ld.is_early_season)
            all_reports[kc][name] = rep_full
            all_early[kc][name] = rep_early
            results["per_league"][kc]["full"][name] = rep_full.row()
            results["per_league"][kc]["early_season"][name] = rep_early.row()
            r = rep_full.row()
            print(f"{kc:8}{name:32}{r['n']:6}{r['accuracy']:7.3f}{r['rps']:8.4f}{r['log_loss']:9.4f}{r['ece']:7.3f}")

    # bookmaker odds arm (only matches with closing lines)
    bk_full, bk_early = run_bookmaker_arm(leagues)
    results["bookmaker_closing_odds"] = {"full": bk_full.row(), "early_season": bk_early.row()}
    print(f"{'ALL':8}{'Bookmaker closing odds (mkt avg/Pinnacle)':32}"
          f"{bk_full.n:6}{bk_full.accuracy:7.3f}{bk_full.rps:8.4f}{bk_full.log_loss:9.4f}{bk_full.ece:7.3f}")

    # pooled (weighted by n) across leagues, full set and early-season subset
    print("\n=== Pooled across all 5 leagues (held-out 2021-22..2025-26) ===")
    print(f"{'Subset':14}{'Model':32}{'n':>6}{'Acc':>7}{'RPS':>8}{'LogLoss':>9}")
    for subset_name, reports_by_league in [("Full set", all_reports), ("Early season (MD1-6)", all_early)]:
        results["pooled"][subset_name] = {}
        for name in models:
            rr = [reports_by_league[kc][name] for kc in leagues]
            n = sum(r.n for r in rr)
            acc = sum(r.accuracy * r.n for r in rr) / n
            rp = sum(r.rps * r.n for r in rr) / n
            ll = sum(r.log_loss * r.n for r in rr) / n
            results["pooled"][subset_name][name] = {"n": n, "accuracy": round(acc, 4), "rps": round(rp, 4), "log_loss": round(ll, 4)}
            print(f"{subset_name:14}{name:32}{n:6}{acc:7.3f}{rp:8.4f}{ll:9.4f}")
    results["pooled"]["Full set"]["Bookmaker closing odds"] = bk_full.row()
    results["pooled"]["Early season (MD1-6)"]["Bookmaker closing odds"] = bk_early.row()
    print(f"{'Full set':14}{'Bookmaker closing odds':32}{bk_full.n:6}{bk_full.accuracy:7.3f}{bk_full.rps:8.4f}{bk_full.log_loss:9.4f}")
    print(f"{'Early season':14}{'Bookmaker closing odds':32}{bk_early.n:6}{bk_early.accuracy:7.3f}{bk_early.rps:8.4f}{bk_early.log_loss:9.4f}")

    # paired bootstrap: ours full-history vs each other model, pooled across leagues, full set + early season
    print("\n=== Paired bootstrap 95% CI: ours (full-history) RPS improvement vs each model ===")
    ours_key = "Ours: full-history warm start"
    for subset_name, reports_by_league in [("Full set", all_reports), ("Early season (MD1-6)", all_early)]:
        results["bootstrap"][subset_name] = {}
        ours_rps_all = {}
        for kc in leagues:
            ours_rps_all.update(rps_by_key(reports_by_league[kc][ours_key]))
        for name in models:
            if name == ours_key:
                continue
            other_rps_all = {}
            for kc in leagues:
                other_rps_all.update(rps_by_key(reports_by_league[kc][name]))
            ci = paired_bootstrap(ours_rps_all, other_rps_all)
            results["bootstrap"][subset_name][name] = ci
            print(f"  [{subset_name}] vs {name:32} n={ci['n']:5} "
                  f"improvement={ci['mean_rps_improvement']:+.4f}  95% CI=[{ci['ci_low']:+.4f}, {ci['ci_high']:+.4f}]")

    # bookmaker vs ours, odds-available subset only
    for subset_name, bk_report, reports_by_league in [
        ("Full set", bk_full, all_reports), ("Early season (MD1-6)", bk_early, all_early),
    ]:
        bk_rps = {(p["match"].date, p["match"].home, p["match"].away): rps(p["p"], p["o"]) for p in bk_report.predictions}
        ours_rps_all = {}
        for kc in leagues:
            ours_rps_all.update(rps_by_key(reports_by_league[kc][ours_key]))
        ci = paired_bootstrap(ours_rps_all, bk_rps)
        results["bootstrap"][subset_name]["Bookmaker closing odds"] = ci
        print(f"  [{subset_name}] vs {'Bookmaker closing odds':32} n={ci['n']:5} "
              f"improvement={ci['mean_rps_improvement']:+.4f}  95% CI=[{ci['ci_low']:+.4f}, {ci['ci_high']:+.4f}]")

    out_path = Path("reports/backtest_openfootball.json")
    out_path.write_text(json.dumps(results, indent=1, default=str))
    print(f"\n-> {out_path}")


if __name__ == "__main__":
    main()
