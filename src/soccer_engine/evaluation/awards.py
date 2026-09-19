"""Chronological evaluation for award rankings on locally supported editions."""

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from soccer_engine.awards import AwardEngine


def _ece(probabilities: list[float], outcomes: list[int]) -> float:
    predicted = np.asarray(probabilities)
    actual = np.asarray(outcomes)
    total = 0.0
    for lower, upper in zip(np.linspace(0, 1, 6)[:-1], np.linspace(0, 1, 6)[1:], strict=True):
        mask = (predicted > lower) & (predicted <= upper)
        if mask.any():
            total += float(mask.mean() * abs(predicted[mask].mean() - actual[mask].mean()))
    return total


def _kendall(left: np.ndarray, right: np.ndarray) -> float:
    concordant = discordant = left_ties = right_ties = 0
    for first in range(len(left)):
        for second in range(first + 1, len(left)):
            left_difference = left[first] - left[second]
            right_difference = right[first] - right[second]
            if left_difference == 0 and right_difference == 0:
                continue
            if left_difference == 0:
                left_ties += 1
                continue
            if right_difference == 0:
                right_ties += 1
                continue
            product = left_difference * right_difference
            concordant += int(product > 0)
            discordant += int(product < 0)
    comparable = concordant + discordant
    denominator = math.sqrt((comparable + left_ties) * (comparable + right_ties))
    return (concordant - discordant) / denominator if denominator else 0.0


def evaluate_awards(
    engine: AwardEngine | None = None,
    output: Path = Path("reports/award_evaluation.json"),
    simulations: int = 3000,
) -> dict[str, Any]:
    """Evaluate scoring snapshots in edition order using only pre-cutoff inputs."""

    engine = engine or AwardEngine()
    players = engine.store.read_frame("player_match_stats")
    matches = engine.store.read_frame("matches")
    matches["kickoff"] = pd.to_datetime(matches["kickoff"], utc=True)
    player_matches = players.drop(columns=["kickoff"], errors="ignore").merge(
        matches[["match_id", "season", "competition_name", "kickoff"]], on="match_id"
    )
    editions = engine.registry.get("wsl_golden_boot").editions
    snapshots: list[dict[str, Any]] = []
    candidate_probabilities: list[float] = []
    candidate_actual: list[int] = []
    previous_winners: set[str] = set()
    baseline_hits: dict[str, list[float]] = {
        "goals_only": [],
        "goal_contribution": [],
        "previous_edition": [],
        "transparent_simulation": [],
    }
    stages = {"early": 0.25, "midseason": 0.5, "late": 0.75}
    for edition in editions:
        season_matches = matches[
            (matches["season"].astype(str) == edition.edition)
            & (matches["competition_name"] == "FA Women's Super League")
        ].sort_values("kickoff")
        if season_matches.empty:
            continue
        complete = player_matches[
            (player_matches["season"].astype(str) == edition.edition)
            & (player_matches["competition_name"] == "FA Women's Super League")
        ]
        final_goals = complete.groupby("player_id")["goals"].sum()
        winners = set(final_goals[final_goals == final_goals.max()].index.astype(str))
        for stage, fraction in stages.items():
            cutoff_index = max(0, int(len(season_matches) * fraction) - 1)
            as_of = pd.Timestamp(season_matches.iloc[cutoff_index]["kickoff"]).to_pydatetime()
            prediction = engine.rank(
                "wsl_golden_boot",
                as_of,
                edition=edition.edition,
                simulations=simulations,
                seed=42,
                save_snapshot=False,
            )
            ranks = {row.candidate_id: row.rank for row in prediction.candidates}
            best_rank = min(
                (ranks.get(winner, len(ranks) + 1) for winner in winners),
                default=len(ranks) + 1,
            )
            winning_mass = sum(
                row.winner_probability
                for row in prediction.candidates
                if row.candidate_id in winners
            )
            target = {
                row.candidate_id: (1 / len(winners) if row.candidate_id in winners else 0)
                for row in prediction.candidates
            }
            brier = sum(
                (row.winner_probability - target[row.candidate_id]) ** 2
                for row in prediction.candidates
            )
            for row in prediction.candidates:
                candidate_probabilities.append(row.winner_probability)
                candidate_actual.append(int(row.candidate_id in winners))
            observed = (
                complete[complete["kickoff"] <= as_of]
                .groupby("player_id")
                .agg(goals=("goals", "sum"), assists=("assists", "sum"))
            )
            goals_pick = str(observed["goals"].idxmax())
            contribution_pick = str((observed["goals"] + observed["assists"]).idxmax())
            simulation_pick = prediction.candidates[0].candidate_id
            baseline_hits["goals_only"].append(float(goals_pick in winners))
            baseline_hits["goal_contribution"].append(float(contribution_pick in winners))
            baseline_hits["previous_edition"].append(
                float(bool(previous_winners) and bool(previous_winners & winners))
            )
            baseline_hits["transparent_simulation"].append(float(simulation_pick in winners))
            predicted_values = np.asarray([row.winner_probability for row in prediction.candidates])
            final_values = np.asarray(
                [float(final_goals.get(row.candidate_id, 0)) for row in prediction.candidates]
            )
            spearman = pd.Series(predicted_values).corr(pd.Series(final_values), method="spearman")
            snapshots.append(
                {
                    "edition": edition.edition,
                    "stage": stage,
                    "as_of": as_of.isoformat(),
                    "candidates": len(prediction.candidates),
                    "observed_winners": sorted(winners),
                    "top_one_hit": int(best_rank == 1),
                    "top_three_hit": int(best_rank <= 3),
                    "top_five_hit": int(best_rank <= 5),
                    "reciprocal_rank": 1 / best_rank,
                    "ndcg": 1 / math.log2(best_rank + 1),
                    "winner_log_loss": -math.log(max(winning_mass, 1e-12)),
                    "multiclass_brier": brier,
                    "spearman": float(spearman) if pd.notna(spearman) else 0.0,
                    "kendall": _kendall(predicted_values, final_values),
                }
            )
        previous_winners = winners
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "award_id": "wsl_golden_boot",
        "label_status": "derived_from_complete_statsbomb_season_not_official_vote_totals",
        "editions": len({row["edition"] for row in snapshots}),
        "snapshots": len(snapshots),
        "date_range": [snapshots[0]["as_of"], snapshots[-1]["as_of"]] if snapshots else [],
        "candidate_rows": sum(row["candidates"] for row in snapshots),
        "metrics": {
            "top_one_accuracy": float(np.mean([row["top_one_hit"] for row in snapshots])),
            "top_three_hit_rate": float(np.mean([row["top_three_hit"] for row in snapshots])),
            "top_five_hit_rate": float(np.mean([row["top_five_hit"] for row in snapshots])),
            "mean_reciprocal_rank": float(np.mean([row["reciprocal_rank"] for row in snapshots])),
            "ndcg": float(np.mean([row["ndcg"] for row in snapshots])),
            "winner_log_loss": float(np.mean([row["winner_log_loss"] for row in snapshots])),
            "multiclass_brier": float(np.mean([row["multiclass_brier"] for row in snapshots])),
            "calibration_error": _ece(candidate_probabilities, candidate_actual),
            "spearman": float(np.mean([row["spearman"] for row in snapshots])),
            "kendall": float(np.mean([row["kendall"] for row in snapshots])),
        },
        "by_prediction_stage": {
            stage: {
                "snapshots": len(rows),
                "top_one_accuracy": float(np.mean([row["top_one_hit"] for row in rows])),
                "winner_log_loss": float(np.mean([row["winner_log_loss"] for row in rows])),
            }
            for stage in stages
            if (rows := [row for row in snapshots if row["stage"] == stage])
        },
        "baseline_top_one_accuracy": {
            name: float(np.mean(values)) for name, values in baseline_hits.items()
        },
        "unavailable_baselines": {
            "trophy_only": "No cutoff-safe trophy table is locally ingested.",
            "media_only": "No attributed historical media corpus is locally ingested.",
        },
        "edition_results": snapshots,
        "warnings": [
            "Only four WSL editions are available; confidence intervals would not be meaningful.",
            "Final leaders are derived from the compatible StatsBomb snapshot and are not "
            "represented as official vote totals.",
            "No robust superiority claim is supported by this sample size.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    return report
