"""Team-level card-rate model: expected yellows/reds per team, split home/away.

Simpler than Dixon-Coles on purpose - cards don't have the same attack/defence
interaction goals do (a team's booking rate is mostly about ITS OWN discipline and
the referee, not directly its opponent's). Empirical-Bayes shrinkage estimator:
time-decayed weighted average of a team's own card counts in that venue split,
shrunk toward the league's home/away average for teams with little history.

    expected(team, home) = (sum(w_i * count_i) + l2 * league_mean) / (sum(w_i) + l2)

Same leakage discipline as DixonColes: fit() rejects any observation on/after the
cutoff date. Validated walk-forward in scripts/backtest_cards.py /
reports/backtest_cards.json against a league-average baseline.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

import numpy as np

MODEL_VERSION = "card-rate-v1"


@dataclass(frozen=True)
class CardObservation:
    date: date
    team: str
    is_home: bool
    yellow: int
    red: int


class LeakageError(ValueError):
    pass


@dataclass
class CardModel:
    xi: float = 0.002  # time decay per day
    l2: float = 6.0  # shrinkage strength (in units of "pseudo-matches" toward league mean)
    as_of: date | None = None
    home_yellow: dict[str, float] = field(default_factory=dict)
    away_yellow: dict[str, float] = field(default_factory=dict)
    home_red: dict[str, float] = field(default_factory=dict)
    away_red: dict[str, float] = field(default_factory=dict)
    league_home_yellow: float = 0.0
    league_away_yellow: float = 0.0
    league_home_red: float = 0.0
    league_away_red: float = 0.0
    n_home: dict[str, int] = field(default_factory=dict)
    n_away: dict[str, int] = field(default_factory=dict)

    def fit(self, observations: Iterable[CardObservation], as_of: date) -> CardModel:
        obs = list(observations)
        late = [o for o in obs if o.date >= as_of]
        if late:
            raise LeakageError(f"{len(late)} observations on/after cutoff {as_of} (first: {late[0]})")
        if len(obs) < 20:
            raise ValueError("need at least 20 observations to fit")

        def weight(o: CardObservation) -> float:
            return float(np.exp(-self.xi * (as_of - o.date).days))

        home_obs = [o for o in obs if o.is_home]
        away_obs = [o for o in obs if not o.is_home]

        def league_mean(rows: list[CardObservation], attr: str) -> float:
            w = np.array([weight(o) for o in rows])
            v = np.array([getattr(o, attr) for o in rows], dtype=float)
            return float((w * v).sum() / w.sum()) if len(rows) else 0.0

        self.league_home_yellow = league_mean(home_obs, "yellow")
        self.league_away_yellow = league_mean(away_obs, "yellow")
        self.league_home_red = league_mean(home_obs, "red")
        self.league_away_red = league_mean(away_obs, "red")

        def per_team(rows: list[CardObservation], attr: str, prior: float) -> tuple[dict[str, float], dict[str, int]]:
            by_team: dict[str, list[CardObservation]] = {}
            for o in rows:
                by_team.setdefault(o.team, []).append(o)
            rates, counts = {}, {}
            for team, team_obs in by_team.items():
                w = np.array([weight(o) for o in team_obs])
                v = np.array([getattr(o, attr) for o in team_obs], dtype=float)
                rates[team] = float((w * v).sum() + self.l2 * prior) / float(w.sum() + self.l2)
                counts[team] = len(team_obs)
            return rates, counts

        self.home_yellow, self.n_home = per_team(home_obs, "yellow", self.league_home_yellow)
        self.away_yellow, self.n_away = per_team(away_obs, "yellow", self.league_away_yellow)
        self.home_red, _ = per_team(home_obs, "red", self.league_home_red)
        self.away_red, _ = per_team(away_obs, "red", self.league_away_red)
        self.as_of = as_of
        return self

    def predict(self, team: str, is_home: bool) -> dict:
        if self.as_of is None:
            raise RuntimeError("model not fitted")
        if is_home:
            yellow = self.home_yellow.get(team, self.league_home_yellow)
            red = self.home_red.get(team, self.league_home_red)
            n = self.n_home.get(team, 0)
        else:
            yellow = self.away_yellow.get(team, self.league_away_yellow)
            red = self.away_red.get(team, self.league_away_red)
            n = self.n_away.get(team, 0)
        return {
            "model_version": MODEL_VERSION,
            "as_of": self.as_of.isoformat(),
            "team": team,
            "is_home": is_home,
            "expected_yellow": round(yellow, 3),
            "expected_red": round(red, 4),
            "train_matches": n,
            "evidence": "A" if n >= 8 else ("B" if n > 0 else "C"),
        }
