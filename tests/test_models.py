import numpy as np

from soccer_engine.models.goals import PoissonGoalModel
from soccer_engine.training import elo_baseline, home_advantage_baseline


def test_baseline_probabilities_sum_to_one(small_matches) -> None:
    from soccer_engine.features.team import build_match_features

    features = build_match_features(small_matches)
    for probabilities in (elo_baseline(features), home_advantage_baseline(features)):
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_score_distribution_is_normalized() -> None:
    distribution = PoissonGoalModel().distribution(1.5, 1.1)
    np.testing.assert_allclose(distribution.sum(), 1.0)
