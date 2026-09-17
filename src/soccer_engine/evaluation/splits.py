"""Time-ordered validation splits."""

from collections.abc import Iterator

import numpy as np
import pandas as pd


def chronological_holdout(
    frame: pd.DataFrame, train_fraction: float = 0.7, validation_fraction: float = 0.15
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return contiguous train, validation, and test partitions."""

    if not 0 < train_fraction < 1 or not 0 <= validation_fraction < 1:
        raise ValueError("split fractions must be between zero and one")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train and validation fractions must leave a test partition")
    ordered = frame.sort_values(["kickoff", "match_id"]).reset_index(drop=True)
    train_end = max(1, int(len(ordered) * train_fraction))
    validation_end = max(train_end + 1, int(len(ordered) * (train_fraction + validation_fraction)))
    return (
        ordered.iloc[:train_end].copy(),
        ordered.iloc[train_end:validation_end].copy(),
        ordered.iloc[validation_end:].copy(),
    )


def expanding_window_splits(
    frame: pd.DataFrame, n_splits: int = 3, minimum_train_size: int = 50
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield expanding train windows followed by non-overlapping validation windows."""

    size = len(frame)
    if size <= minimum_train_size:
        raise ValueError("not enough rows for an expanding-window split")
    fold_size = max(1, (size - minimum_train_size) // n_splits)
    for split in range(n_splits):
        train_end = minimum_train_size + split * fold_size
        valid_end = size if split == n_splits - 1 else min(size, train_end + fold_size)
        if train_end < valid_end:
            yield np.arange(0, train_end), np.arange(train_end, valid_end)


def rolling_window_splits(
    frame: pd.DataFrame,
    train_size: int,
    test_size: int,
    step: int | None = None,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield fixed-width chronological training windows followed by future tests."""

    if train_size < 1 or test_size < 1:
        raise ValueError("rolling window sizes must be positive")
    step = step or test_size
    ordered_size = len(frame)
    for test_start in range(train_size, ordered_size - test_size + 1, step):
        yield (
            np.arange(test_start - train_size, test_start),
            np.arange(test_start, test_start + test_size),
        )
