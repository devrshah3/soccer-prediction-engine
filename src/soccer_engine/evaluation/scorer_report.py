"""Season-level scorer evaluation for locally ingested compatible player data."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from soccer_engine.evaluation.player import evaluate_goalscorers
from soccer_engine.features.team import build_match_features
from soccer_engine.models.goals import PoissonGoalModel


def generate_scorer_evaluation(
    matches: pd.DataFrame,
    player_matches: pd.DataFrame,
    output: Path = Path("reports/scorer_evaluation.json"),
) -> dict[str, Any]:
    """Hold out the complete latest compatible season and retain chronological provenance."""

    player_matches = player_matches.copy()
    player_matches["kickoff"] = pd.to_datetime(player_matches["kickoff"], utc=True)
    player_match_ids = set(player_matches["match_id"].astype(str))
    compatible = matches[matches["match_id"].astype(str).isin(player_match_ids)].copy()
    compatible["kickoff"] = pd.to_datetime(compatible["kickoff"], utc=True)
    latest_season = compatible.sort_values("kickoff").iloc[-1]["season"]
    holdout_matches = compatible[compatible["season"] == latest_season]
    holdout_start = holdout_matches["kickoff"].min()
    features = build_match_features(matches).dropna(subset=["outcome"])
    train = features[features["kickoff"] < holdout_start]
    test = features[features["match_id"].isin(holdout_matches["match_id"])]
    goal_model = PoissonGoalModel().fit(train)
    metrics = evaluate_goalscorers(test, matches, player_matches, goal_model)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "protocol": "complete latest compatible season holdout",
        "competition": str(holdout_matches.iloc[0]["competition_name"]),
        "season": str(latest_season),
        "training_matches": len(train),
        "held_out_matches": len(test),
        "training_period": [str(train["kickoff"].min()), str(train["kickoff"].max())],
        "holdout_period": [str(test["kickoff"].min()), str(test["kickoff"].max())],
        "player_dataset": {
            "compatible_matches": len(compatible),
            "player_match_rows": len(player_matches),
            "players": int(player_matches["player_id"].nunique()),
        },
        "metrics": metrics,
        "limitation": (
            "StatsBomb's locally packaged compatible player sample contains four WSL seasons. "
            "It does not establish cross-competition scorer performance."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    return report
