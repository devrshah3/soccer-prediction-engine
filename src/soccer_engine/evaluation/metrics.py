"""Probabilistic evaluation metrics and bootstrap intervals."""

from collections.abc import Callable

import numpy as np
from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss

CLASS_ORDER = np.array(["away", "draw", "home"])


def ranked_probability_score(y_true: np.ndarray, probabilities: np.ndarray) -> float:
    """Compute multiclass ranked probability score for ordered outcomes."""

    encoded = np.column_stack([y_true == label for label in CLASS_ORDER]).astype(float)
    return float(
        np.mean(
            np.sum(
                (np.cumsum(probabilities, axis=1)[:, :-1] - np.cumsum(encoded, axis=1)[:, :-1])
                ** 2,
                axis=1,
            )
            / 2
        )
    )


def multiclass_brier_score(y_true: np.ndarray, probabilities: np.ndarray) -> float:
    encoded = np.column_stack([y_true == label for label in CLASS_ORDER]).astype(float)
    return float(np.mean(np.sum((probabilities - encoded) ** 2, axis=1)))


def expected_calibration_error(
    y_true: np.ndarray, probabilities: np.ndarray, bins: int = 10
) -> float:
    predicted = CLASS_ORDER[np.argmax(probabilities, axis=1)]
    confidence = np.max(probabilities, axis=1)
    correct = predicted == y_true
    error = 0.0
    edges = np.linspace(0, 1, bins + 1)
    for lower, upper in zip(edges[:-1], edges[1:], strict=True):
        mask = (confidence > lower) & (confidence <= upper)
        if mask.any():
            error += mask.mean() * abs(correct[mask].mean() - confidence[mask].mean())
    return float(error)


def outcome_metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    """Evaluate ordered, calibrated outcome probabilities."""

    predicted = CLASS_ORDER[np.argmax(probabilities, axis=1)]
    return {
        "accuracy": float(accuracy_score(y_true, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predicted)),
        "log_loss": float(log_loss(y_true, probabilities, labels=CLASS_ORDER)),
        "brier_score": multiclass_brier_score(y_true, probabilities),
        "ranked_probability_score": ranked_probability_score(y_true, probabilities),
        "calibration_error": expected_calibration_error(y_true, probabilities),
    }


def bootstrap_interval(
    metric: Callable[[np.ndarray, np.ndarray], float],
    y_true: np.ndarray,
    probabilities: np.ndarray,
    samples: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """Return a seeded 95% nonparametric bootstrap interval."""

    generator = np.random.default_rng(seed)
    values = []
    for _ in range(samples):
        indices = generator.integers(0, len(y_true), len(y_true))
        values.append(metric(y_true[indices], probabilities[indices]))
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))
