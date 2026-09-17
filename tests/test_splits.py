from soccer_engine.evaluation.splits import chronological_holdout, expanding_window_splits


def test_chronological_splits_are_ordered(small_matches) -> None:
    train, validation, test = chronological_holdout(small_matches)
    assert train["kickoff"].max() < validation["kickoff"].min()
    assert validation["kickoff"].max() < test["kickoff"].min()


def test_expanding_windows_never_train_on_future(small_matches) -> None:
    for train_indices, validation_indices in expanding_window_splits(
        small_matches, n_splits=3, minimum_train_size=20
    ):
        assert train_indices.max() < validation_indices.min()
