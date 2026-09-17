"""Multi-protocol chronological evaluation for global match-level data."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix

from soccer_engine.evaluation.metrics import bootstrap_interval, outcome_metrics
from soccer_engine.evaluation.splits import expanding_window_splits, rolling_window_splits
from soccer_engine.features.team import build_match_features
from soccer_engine.models.outcome import OutcomeModel
from soccer_engine.training import elo_baseline, home_advantage_baseline


def _evaluate(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, Any]:
    model = OutcomeModel(kind="logistic").fit(train)
    actual = test["outcome"].to_numpy()
    predicted = model.predict_proba(test)
    metrics = outcome_metrics(actual, predicted)
    labels = np.array(["away", "draw", "home"])
    predicted_labels = labels[np.argmax(predicted, axis=1)]
    interval = bootstrap_interval(
        lambda y, p: outcome_metrics(y, p)["log_loss"], actual, predicted, samples=300
    )
    classes, counts = np.unique(train["outcome"].to_numpy(), return_counts=True)
    most_common = classes[np.argmax(counts)]
    common_probs = np.full((len(test), 3), 1e-6)
    class_index = {"away": 0, "draw": 1, "home": 2}
    common_probs[:, class_index[str(most_common)]] = 1 - 2e-6
    return {
        "train_matches": len(train),
        "held_out_matches": len(test),
        "train_period": [str(train["kickoff"].min()), str(train["kickoff"].max())],
        "test_period": [str(test["kickoff"].min()), str(test["kickoff"].max())],
        "competitions": sorted(test["competition_name"].unique().tolist()),
        "seasons": sorted(test["season"].astype(str).unique().tolist()),
        "model": {
            **metrics,
            "log_loss_95_ci": list(interval),
            "confusion_matrix": confusion_matrix(actual, predicted_labels, labels=labels).tolist(),
            "per_class": classification_report(
                actual,
                predicted_labels,
                labels=labels,
                output_dict=True,
                zero_division=0,
            ),
        },
        "baselines": {
            "most_common": outcome_metrics(actual, common_probs),
            "home_advantage": outcome_metrics(actual, home_advantage_baseline(test)),
            "elo": outcome_metrics(actual, elo_baseline(test)),
        },
    }


def generate_global_evaluation(
    matches: pd.DataFrame, output: Path = Path("reports/global_evaluation.json")
) -> dict[str, Any]:
    """Run expanding, rolling, season, league, and tournament views without shuffling."""

    features = build_match_features(matches).dropna(subset=["outcome"])
    features = features.sort_values(["kickoff", "match_id"]).reset_index(drop=True)
    split = int(len(features) * 0.8)
    main = _evaluate(features.iloc[:split], features.iloc[split:])
    expanding = [
        _evaluate(features.iloc[train], features.iloc[test])
        for train, test in expanding_window_splits(
            features, n_splits=3, minimum_train_size=max(500, len(features) // 2)
        )
    ]
    train_size = max(1000, len(features) // 2)
    test_size = max(200, len(features) // 10)
    rolling = [
        _evaluate(features.iloc[train], features.iloc[test])
        for train, test in rolling_window_splits(features, train_size, test_size)
    ]
    latest_year = max(
        int(str(season)[:4]) for season in features["season"] if str(season)[:4].isdigit()
    )
    future_mask = features["season"].astype(str).str.startswith(str(latest_year))
    season_holdout = _evaluate(features[~future_mask], features[future_mask])
    model = OutcomeModel(kind="logistic").fit(features.iloc[:split])
    test = features.iloc[split:].copy()
    test_probabilities = model.predict_proba(test)
    per_competition = {}
    for competition, group in test.groupby("competition_name"):
        if len(group) < 5:
            continue
        indices = test.index.get_indexer(group.index)
        per_competition[str(competition)] = {
            "held_out_matches": len(group),
            "period": [str(group["kickoff"].min()), str(group["kickoff"].max())],
            **outcome_metrics(group["outcome"].to_numpy(), test_probabilities[indices]),
        }
    cross_league = {}
    eligible = features["competition_name"].value_counts()
    for competition in eligible[eligible >= 100].index:
        league_test = features[features["competition_name"] == competition]
        league_train = features[features["competition_name"] != competition]
        cross_league[str(competition)] = _evaluate(league_train, league_test)
    tournament = {
        name: value
        for name, value in per_competition.items()
        if any(token in name.lower() for token in ("cup", "euro", "champions", "copa"))
    }
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "matches": len(features),
            "competitions": int(features["competition_name"].nunique()),
            "seasons": int(features[["competition_name", "season"]].drop_duplicates().shape[0]),
            "period": [str(features["kickoff"].min()), str(features["kickoff"].max())],
        },
        "chronological_holdout": main,
        "expanding_window": expanding,
        "rolling_window": rolling,
        "future_season_holdout": season_holdout,
        "per_competition": per_competition,
        "cross_league_holdouts": cross_league,
        "tournament_specific": tournament,
        "limitations": [
            "StatsBomb Open Data is a curated subset, not a representative global match census.",
            "Cross-league results include heterogeneous eras and are not deployment claims.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    return report
