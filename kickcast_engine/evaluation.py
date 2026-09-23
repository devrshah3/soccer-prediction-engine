"""Chronological (walk-forward) evaluation.

Matches are grouped into consecutive 7-day blocks. For each block, the model is
refit using ONLY matches dated strictly before the block's first match, then
predicts every match in the block. Nothing from the future can leak in.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from itertools import pairwise

import numpy as np

from .models.dixon_coles import MatchResult

Probs = tuple[float, float, float]  # home, draw, away
Predictor = Callable[[list[MatchResult], MatchResult], Probs]
FitFn = Callable[[list[MatchResult], "object"], Callable[[MatchResult], Probs]]


def outcome(m: MatchResult) -> int:
    if m.home_goals > m.away_goals:
        return 0
    return 1 if m.home_goals == m.away_goals else 2


def rps(p: Sequence[float], o: int) -> float:
    """Ranked probability score for ordered outcomes (home, draw, away). Lower = better."""
    obs = np.zeros(3)
    obs[o] = 1
    cp, co = np.cumsum(p), np.cumsum(obs)
    return float(np.sum((cp[:-1] - co[:-1]) ** 2) / 2)


@dataclass
class Report:
    n: int
    accuracy: float
    rps: float
    log_loss: float
    brier: float
    ece: float
    calibration: list[dict]
    predictions: list[dict]

    def row(self) -> dict:
        return {
            "n": self.n,
            "accuracy": round(self.accuracy, 4),
            "rps": round(self.rps, 4),
            "log_loss": round(self.log_loss, 4),
            "brier": round(self.brier, 4),
            "ece": round(self.ece, 4),
        }


def walk_forward(
    matches: Sequence[MatchResult],
    fit: Callable[[list[MatchResult], object], Callable[[MatchResult], Probs]],
    warmup: int = 100,
    block_days: int = 7,
) -> Report:
    ms = sorted(matches, key=lambda m: m.date)
    start = ms[warmup].date
    blocks: dict[int, list[MatchResult]] = {}
    for m in ms:
        if m.date >= start:
            blocks.setdefault((m.date - start).days // block_days, []).append(m)

    preds: list[dict] = []
    for k in sorted(blocks):
        block = blocks[k]
        cutoff = min(m.date for m in block)
        train = [m for m in ms if m.date < cutoff]
        assert all(m.date < cutoff for m in train), "leakage"
        assert cutoff - timedelta(days=0) > max(m.date for m in train), "leakage"
        predict = fit(train, cutoff)
        for m in block:
            p = np.clip(np.array(predict(m), dtype=float), 1e-9, 1)
            p = p / p.sum()
            preds.append({"match": m, "p": p, "o": outcome(m), "cutoff": cutoff})
    return score(preds)


def score(preds: list[dict]) -> Report:
    P = np.array([x["p"] for x in preds])
    O = np.array([x["o"] for x in preds])
    onehot = np.eye(3)[O]
    bins = np.linspace(0, 1, 11)
    cal = []
    flat_p, flat_o = P.ravel(), onehot.ravel()
    ece = 0.0
    for lo, hi in pairwise(bins):
        mask = (flat_p >= lo) & (flat_p < hi)
        if mask.sum() == 0:
            continue
        mp, mo = flat_p[mask].mean(), flat_o[mask].mean()
        ece += mask.sum() / len(flat_p) * abs(mp - mo)
        cal.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(mask.sum()),
                    "predicted": round(float(mp), 3), "observed": round(float(mo), 3)})
    return Report(
        n=len(preds),
        accuracy=float(np.mean(P.argmax(1) == O)),
        rps=float(np.mean([rps(p, o) for p, o in zip(P, O)])),
        log_loss=float(-np.mean(np.log(P[np.arange(len(O)), O]))),
        brier=float(np.mean(np.sum((P - onehot) ** 2, axis=1))),
        ece=float(ece),
        calibration=cal,
        predictions=preds,
    )


def walk_forward_window(
    matches: Sequence[MatchResult],
    fit: Callable[[list[MatchResult], object], Callable[[MatchResult], Probs]],
    start,
    end,
    block_days: int = 7,
    include: Callable[[MatchResult], bool] | None = None,
) -> Report:
    """Walk-forward over [start, end): refit per block on matches strictly before it."""
    ms = sorted(matches, key=lambda m: m.date)
    blocks: dict[int, list[MatchResult]] = {}
    for m in ms:
        if start <= m.date < end and (include is None or include(m)):
            blocks.setdefault((m.date - start).days // block_days, []).append(m)
    preds: list[dict] = []
    for k in sorted(blocks):
        block = blocks[k]
        cutoff = min(m.date for m in block)
        train = [m for m in ms if m.date < cutoff]
        assert train and max(m.date for m in train) < cutoff, "leakage"
        predict = fit(train, cutoff)
        for m in block:
            p = np.clip(np.array(predict(m), dtype=float), 1e-9, 1)
            preds.append({"match": m, "p": p / p.sum(), "o": outcome(m), "cutoff": cutoff})
    return score(preds)
