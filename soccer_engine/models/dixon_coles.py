"""Pre-match goal model: Dixon-Coles (1997) with time-decay weights and L2 shrinkage.

home goals ~ Poisson(lam),  lam = exp(home_adv + att[home] + dfn[away])
away goals ~ Poisson(mu),   mu  = exp(att[away] + dfn[home])
plus the Dixon-Coles low-score correction (rho) on 0-0, 1-0, 0-1, 1-1.

`dfn` is "goals conceded" strength: higher = weaker defence.
L2 shrinkage pulls teams with few matches toward league average.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson

MODEL_VERSION = "dixon-coles-v1"


@dataclass(frozen=True)
class MatchResult:
    date: date
    home: str
    away: str
    home_goals: int
    away_goals: int
    neutral: bool = False
    home_xg: float | None = None  # non-penalty xG + penalty xG, if known
    away_xg: float | None = None


class LeakageError(ValueError):
    """Raised when training data is not strictly before the forecast cutoff."""


@dataclass
class DixonColes:
    xi: float = 0.0019  # time decay per day (~1 year half-life)
    l2: float = 0.5  # shrinkage strength toward league average
    xg_weight: float = 0.0  # 0 = fit on goals only, 1 = fit on xG only
    max_goals: int = 10
    teams: list[str] = field(default_factory=list)
    att: np.ndarray = field(default_factory=lambda: np.zeros(0))
    dfn: np.ndarray = field(default_factory=lambda: np.zeros(0))
    home_adv: float = 0.0
    rho: float = 0.0
    as_of: date | None = None
    matches_per_team: dict[str, int] = field(default_factory=dict)
    n_train: int = 0

    def fit(self, matches: Iterable[MatchResult], as_of: date) -> DixonColes:
        data = list(matches)
        late = [m for m in data if m.date >= as_of]
        if late:
            raise LeakageError(
                f"{len(late)} training matches on/after cutoff {as_of} (first: {late[0]})"
            )
        if len(data) < 10:
            raise ValueError("need at least 10 matches to fit")

        self.teams = sorted({m.home for m in data} | {m.away for m in data})
        idx = {t: i for i, t in enumerate(self.teams)}
        n = len(self.teams)
        h = np.array([idx[m.home] for m in data])
        a = np.array([idx[m.away] for m in data])
        x = np.array([m.home_goals for m in data], dtype=float)
        y = np.array([m.away_goals for m in data], dtype=float)
        # low-score correction uses real scorelines; strength targets may blend in xG
        c00 = (x == 0) & (y == 0)
        c01 = (x == 0) & (y == 1)
        c10 = (x == 1) & (y == 0)
        c11 = (x == 1) & (y == 1)
        if self.xg_weight > 0:
            wx = self.xg_weight
            x = np.array(
                [m.home_goals if m.home_xg is None else (1 - wx) * m.home_goals + wx * m.home_xg
                 for m in data]
            )
            y = np.array(
                [m.away_goals if m.away_xg is None else (1 - wx) * m.away_goals + wx * m.away_xg
                 for m in data]
            )
        neutral = np.array([m.neutral for m in data], dtype=float)
        age = np.array([(as_of - m.date).days for m in data], dtype=float)
        w = np.exp(-self.xi * age)

        const = gammaln(x + 1) + gammaln(y + 1)
        l2 = self.l2

        def unpack(p: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
            att = p[:n] - p[:n].mean()
            return att, p[n : 2 * n], p[2 * n], p[2 * n + 1]

        def nll(p: np.ndarray) -> tuple[float, np.ndarray]:
            att, dfn, hadv, rho = unpack(p)
            log_lam = hadv * (1 - neutral) + att[h] + dfn[a]
            log_mu = att[a] + dfn[h]
            lam, mu = np.exp(log_lam), np.exp(log_mu)

            tau = np.ones_like(lam)
            tau[c00] = 1 - lam[c00] * mu[c00] * rho
            tau[c01] = 1 + lam[c01] * rho
            tau[c10] = 1 + mu[c10] * rho
            tau[c11] = 1 - rho
            tau = np.clip(tau, 1e-10, None)

            ll = w * (np.log(tau) + x * log_lam - lam + y * log_mu - mu - const)

            # d log-lik / d log_lam, d log_mu, d rho
            g_lam = x - lam
            g_mu = y - mu
            g_rho = np.zeros_like(lam)
            g_lam[c00] += -lam[c00] * mu[c00] * rho / tau[c00]
            g_mu[c00] += -lam[c00] * mu[c00] * rho / tau[c00]
            g_rho[c00] = -lam[c00] * mu[c00] / tau[c00]
            g_lam[c01] += lam[c01] * rho / tau[c01]
            g_rho[c01] = lam[c01] / tau[c01]
            g_mu[c10] += mu[c10] * rho / tau[c10]
            g_rho[c10] = mu[c10] / tau[c10]
            g_rho[c11] = -1 / tau[c11]
            g_lam *= w
            g_mu *= w
            g_rho *= w

            g_att = np.zeros(n)
            g_dfn = np.zeros(n)
            np.add.at(g_att, h, g_lam)
            np.add.at(g_dfn, a, g_lam)
            np.add.at(g_att, a, g_mu)
            np.add.at(g_dfn, h, g_mu)
            g_att -= g_att.mean()  # mean-centring constraint
            g_hadv = float(np.sum(g_lam * (1 - neutral)))

            obj = -ll.sum() + l2 * (np.sum(att**2) + np.sum(dfn**2))
            grad = -np.concatenate([g_att, g_dfn, [g_hadv, g_rho.sum()]])
            grad[:n] += 2 * l2 * att
            grad[n : 2 * n] += 2 * l2 * dfn
            return float(obj), grad

        base = np.log(max((x.mean() + y.mean()) / 2, 0.1))
        p0 = np.concatenate([np.zeros(n), np.full(n, base), [0.25, -0.05]])
        bounds = [(None, None)] * (2 * n) + [(-1, 1), (-0.3, 0.3)]
        res = minimize(nll, p0, jac=True, method="L-BFGS-B", bounds=bounds)
        if not res.success and "ABNORMAL" not in str(res.message):
            raise RuntimeError(f"fit failed: {res.message}")

        self.att, self.dfn, self.home_adv, self.rho = unpack(res.x)
        self.base_dfn = float(np.mean(self.dfn))
        self.as_of = as_of
        self.n_train = len(data)
        counts: dict[str, int] = {}
        for m in data:
            counts[m.home] = counts.get(m.home, 0) + 1
            counts[m.away] = counts.get(m.away, 0) + 1
        self.matches_per_team = counts
        return self

    # ------------------------------------------------------------------ predict
    def _strength(self, team: str) -> tuple[float, float, bool]:
        if team in self.teams:
            i = self.teams.index(team)
            return float(self.att[i]), float(self.dfn[i]), True
        return 0.0, self.base_dfn, False  # unseen team -> league average

    def expected_goals(self, home: str, away: str, neutral: bool = False) -> tuple[float, float]:
        ah, dh, _ = self._strength(home)
        aa, da, _ = self._strength(away)
        hadv = 0.0 if neutral else self.home_adv
        return float(np.exp(hadv + ah + da)), float(np.exp(aa + dh))

    def score_matrix(self, lam: float, mu: float) -> np.ndarray:
        g = np.arange(self.max_goals + 1)
        m = np.outer(poisson.pmf(g, lam), poisson.pmf(g, mu))
        m[0, 0] *= 1 - lam * mu * self.rho
        m[0, 1] *= 1 + lam * self.rho
        m[1, 0] *= 1 + mu * self.rho
        m[1, 1] *= 1 - self.rho
        m = np.clip(m, 0, None)
        return m / m.sum()

    def predict(self, home: str, away: str, neutral: bool = False) -> dict:
        if self.as_of is None:
            raise RuntimeError("model not fitted")
        lam, mu = self.expected_goals(home, away, neutral)
        m = self.score_matrix(lam, mu)
        g = np.arange(self.max_goals + 1)
        diff = g[:, None] - g[None, :]
        total = g[:, None] + g[None, :]
        flat = np.argsort(m, axis=None)[::-1][:5]
        top = [
            {"score": f"{i}-{j}", "prob": round(float(m[i, j]), 4)}
            for i, j in (np.unravel_index(k, m.shape) for k in flat)
        ]
        n_home = self.matches_per_team.get(home, 0)
        n_away = self.matches_per_team.get(away, 0)
        return {
            "model_version": MODEL_VERSION,
            "as_of": self.as_of.isoformat(),
            "home": home,
            "away": away,
            "neutral": neutral,
            "expected_goals": {"home": round(lam, 3), "away": round(mu, 3)},
            "expected_margin": round(lam - mu, 3),
            "probabilities": {
                "home": float(m[diff > 0].sum()),
                "draw": float(m[diff == 0].sum()),
                "away": float(m[diff < 0].sum()),
            },
            "totals": {
                f"over_{t}": float(m[total > t].sum()) for t in (0.5, 1.5, 2.5, 3.5)
            },
            "btts": float(m[1:, 1:].sum()),
            "likely_scorelines": top,
            "evidence": evidence_tier(n_home, n_away),
            "train_matches": {"home": n_home, "away": n_away, "total": self.n_train},
        }


def evidence_tier(n_home: int, n_away: int) -> str:
    """A: both teams well observed; B: thin data for one; C: a team unseen."""
    lo = min(n_home, n_away)
    if lo == 0:
        return "C"
    if lo < 8:
        return "B"
    return "A"


def to_results(rows: Sequence[dict]) -> list[MatchResult]:
    return [
        MatchResult(
            date=r["date"],
            home=r["home"],
            away=r["away"],
            home_goals=int(r["home_goals"]),
            away_goals=int(r["away_goals"]),
            neutral=bool(r.get("neutral", False)),
            home_xg=r.get("home_xg"),
            away_xg=r.get("away_xg"),
        )
        for r in rows
    ]
