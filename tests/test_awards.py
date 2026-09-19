import importlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from soccer_engine.api.app import app
from soccer_engine.awards import AwardEngine, AwardRegistry
from soccer_engine.awards.features import build_player_period_features
from soccer_engine.awards.schemas import AwardCoverage, MediaObservation
from soccer_engine.evaluation.awards import evaluate_awards
from soccer_engine.storage import LocalStore


def _award_engine(tmp_path: Path) -> tuple[AwardEngine, datetime]:
    kickoff = datetime(2023, 9, 10, 12, tzinfo=UTC)
    matches = []
    players = []
    for index in range(10):
        match_id = f"match:{index}"
        match_time = kickoff + timedelta(days=index * 7)
        matches.append(
            {
                "match_id": match_id,
                "season": "2023/2024",
                "competition_name": "FA Women's Super League",
                "kickoff": match_time,
                "home_team_id": "team:a",
                "away_team_id": "team:b",
                "status": "finished",
            }
        )
        for player_id, player_name, team_id, position, goals in (
            ("p:forward", "Forward", "team:a", "Center Forward", int(index % 2 == 0)),
            ("p:defender", "Defender", "team:b", "Center Back", int(index in {1, 8})),
        ):
            players.append(
                {
                    "match_id": match_id,
                    "kickoff": match_time,
                    "provider": "test",
                    "provider_player_id": player_id,
                    "player_id": player_id,
                    "player_name": player_name,
                    "team_id": team_id,
                    "team_name": team_id,
                    "position": position,
                    "in_squad": True,
                    "started": True,
                    "minutes": 90.0,
                    "goals": goals,
                    "non_penalty_goals": goals,
                    "assists": int(player_id == "p:defender" and index == 2),
                    "expected_goals": float(goals) + 0.2,
                    "shots": goals + 1,
                    "shots_on_target": goals,
                    "penalties_taken": 0,
                    "penalties_scored": 0,
                    "first_goal": False,
                    "source_url": "test",
                }
            )
    store = LocalStore(tmp_path / "data")
    store.write_frame("matches", pd.DataFrame(matches))
    store.write_frame("player_match_stats", pd.DataFrame(players))
    return AwardEngine(store, snapshot_dir=tmp_path / "snapshots"), kickoff + timedelta(days=28)


def test_post_cutoff_matches_do_not_affect_earlier_ranking(tmp_path: Path) -> None:
    engine, as_of = _award_engine(tmp_path)
    before = engine.rank("wsl_golden_boot", as_of, "2023/2024", simulations=500, seed=9)
    players = engine.store.read_frame("player_match_stats")
    future = pd.to_datetime(players["kickoff"], utc=True) > as_of
    players.loc[future & (players["player_id"] == "p:defender"), "goals"] = 99
    engine.store.write_frame("player_match_stats", players)
    after = engine.rank("wsl_golden_boot", as_of, "2023/2024", simulations=500, seed=9)
    assert [item.model_dump() for item in before.candidates] == [
        item.model_dump() for item in after.candidates
    ]


def test_probabilities_sum_and_simulation_is_reproducible(tmp_path: Path) -> None:
    engine, as_of = _award_engine(tmp_path)
    first = engine.rank("wsl_golden_boot", as_of, "2023/2024", simulations=400, seed=3)
    second = engine.rank("wsl_golden_boot", as_of, "2023/2024", simulations=400, seed=3)
    assert sum(item.winner_probability for item in first.candidates) == pytest.approx(1)
    assert [item.winner_probability for item in first.candidates] == [
        item.winner_probability for item in second.candidates
    ]


def test_edition_rules_and_eligibility_are_enforced(tmp_path: Path) -> None:
    engine, _ = _award_engine(tmp_path)
    registry = AwardRegistry()
    editions = registry.get("wsl_golden_boot").editions
    assert editions[0].tie_break == "shared"
    assert editions[-1].edition == "2023/2024"
    world_cup_rules = {
        item.edition: item.tie_break for item in registry.get("world_cup_golden_boot").editions
    }
    assert world_cup_rules["1994"] == "shared"
    assert world_cup_rules["2022"] == "assists_then_minutes"
    result = engine.rank(
        "wsl_golden_boot",
        datetime(2023, 8, 1, tzinfo=UTC),
        edition="2023/2024",
    )
    assert result.status == AwardCoverage.UNAVAILABLE


def test_transfer_rows_do_not_create_duplicate_candidates(tmp_path: Path) -> None:
    engine, as_of = _award_engine(tmp_path)
    players = engine.store.read_frame("player_match_stats")
    players.loc[
        (players["player_id"] == "p:forward")
        & (pd.to_datetime(players["kickoff"], utc=True) <= as_of),
        ["team_id", "team_name"],
    ] = ["team:new", "New Team"]
    engine.store.write_frame("player_match_stats", players)
    result = engine.rank("wsl_golden_boot", as_of, "2023/2024", simulations=200)
    assert [item.candidate_id for item in result.candidates].count("p:forward") == 1


def test_club_and_other_competition_statistics_are_separated(tmp_path: Path) -> None:
    engine, as_of = _award_engine(tmp_path)
    matches = engine.store.read_frame("matches")
    players = engine.store.read_frame("player_match_stats")
    extra_match = matches.iloc[0].copy()
    extra_match["match_id"] = "international:1"
    extra_match["competition_name"] = "International Friendlies"
    extra_player = players.iloc[0].copy()
    extra_player["match_id"] = "international:1"
    extra_player["goals"] = 50
    engine.store.write_frame("matches", pd.concat([matches, extra_match.to_frame().T]))
    engine.store.write_frame("player_match_stats", pd.concat([players, extra_player.to_frame().T]))
    result = engine.rank("wsl_golden_boot", as_of, "2023/2024", simulations=200)
    forward = next(item for item in result.candidates if item.candidate_id == "p:forward")
    assert forward.current_goals == 3


def _media(article_date: datetime, observation_id: str = "obs:1") -> MediaObservation:
    return MediaObservation(
        observation_id=observation_id,
        award_id="ballon_dor",
        edition="2025",
        publication="Example",
        article_date=article_date,
        url="https://example.test/ranking",
        candidate_id="p:one",
        candidate_name="One",
        extracted_rank=1,
        confidence=0.9,
        reliability_weight=0.8,
        retrieved_at=article_date,
        availability_cutoff=article_date,
    )


def test_post_cutoff_media_is_excluded_and_duplicates_removed(tmp_path: Path) -> None:
    engine, _ = _award_engine(tmp_path)
    cutoff = datetime(2025, 6, 1, tzinfo=UTC)
    engine.add_media_observations(
        [_media(cutoff - timedelta(days=1)), _media(cutoff + timedelta(days=1), "obs:2")]
    )
    visible = engine.media("ballon_dor", "2025", cutoff)
    assert len(visible) == 1
    engine.add_media_observations([_media(cutoff - timedelta(days=1), "obs:3")])
    assert len(engine.media("ballon_dor", "2025", cutoff)) == 1


def test_missing_media_is_not_converted_to_positive_sentiment(tmp_path: Path) -> None:
    engine, _ = _award_engine(tmp_path)
    candidates = pd.DataFrame(
        [
            {
                "award_id": "ballon_dor",
                "edition": "2025",
                "candidate_id": value,
                "candidate_name": value,
                "statistical_score": score,
                "team_achievement_score": 0,
                "international_score": 0,
                "position_group": "attack",
                "candidate_pool_complete": True,
                "data_completeness": 0.7,
                "availability_cutoff": "2025-05-01T00:00:00Z",
                "source": "manual test",
            }
            for value, score in (("one", 2), ("two", 1))
        ]
    )
    engine.store.write_frame("award_candidates", candidates)
    result = engine.rank("ballon_dor", datetime(2025, 6, 1, tzinfo=UTC), edition="2025")
    assert all(item.media_score is None for item in result.candidates)
    assert all(
        "Media component is unavailable." in item.missing_evidence for item in result.candidates
    )


def test_position_aware_normalization_preserves_non_attacker_candidate(tmp_path: Path) -> None:
    engine, _ = _award_engine(tmp_path)
    frame = pd.DataFrame(
        [
            {
                "award_id": "ballon_dor",
                "edition": "2025",
                "candidate_id": "forward",
                "candidate_name": "Forward",
                "position_group": "attack",
                "statistical_score": 20,
                "team_achievement_score": 0,
                "international_score": 0,
                "candidate_pool_complete": True,
                "data_completeness": 0.8,
                "availability_cutoff": "2025-05-01T00:00:00Z",
                "source": "test",
            },
            {
                "award_id": "ballon_dor",
                "edition": "2025",
                "candidate_id": "keeper",
                "candidate_name": "Keeper",
                "position_group": "goalkeeper",
                "statistical_score": 5,
                "team_achievement_score": 1,
                "international_score": 1,
                "candidate_pool_complete": True,
                "data_completeness": 0.8,
                "availability_cutoff": "2025-05-01T00:00:00Z",
                "source": "test",
            },
        ]
    )
    engine.store.write_frame("award_candidates", frame)
    result = engine.rank("ballon_dor", datetime(2025, 6, 1, tzinfo=UTC), edition="2025")
    keeper = next(item for item in result.candidates if item.candidate_id == "keeper")
    assert keeper.statistical_score == 0.5
    assert keeper.rank == 1


def test_player_period_features_are_position_aware_and_penalty_adjusted(tmp_path: Path) -> None:
    engine, as_of = _award_engine(tmp_path)
    rows = engine.store.read_frame("player_match_stats")
    rows = rows[pd.to_datetime(rows["kickoff"], utc=True) <= as_of]
    features = build_player_period_features(rows)
    assert {
        "goals_per_90",
        "non_penalty_goals_per_90",
        "assists_per_90",
        "position_adjusted_production",
        "penalty_adjusted_goals",
    }.issubset(features.columns)
    assert set(features["position_group"]) == {"attack", "defence"}
    assert (features["data_completeness"] == 0.75).all()


def test_puskas_is_metadata_only_without_video_analysis(tmp_path: Path) -> None:
    engine, _ = _award_engine(tmp_path)
    frame = pd.DataFrame(
        [
            {
                "nomination_id": "goal:1",
                "award_id": "fifa_puskas",
                "edition": "2025",
                "player_id": "p:one",
                "player_name": "One",
                "competition": "Test Cup",
                "goal_date": "2025-01-01T00:00:00Z",
                "availability_cutoff": "2025-02-01T00:00:00Z",
                "official_vote_share": 0.4,
                "match_importance": 0.5,
                "source": "official nominee announcement",
            }
        ]
    )
    engine.store.write_frame("goal_nominations", frame)
    result = engine.rank("fifa_puskas", datetime(2025, 6, 1, tzinfo=UTC), edition="2025")
    assert result.status == AwardCoverage.METADATA_ONLY
    assert any("No visual beauty" in warning for warning in result.warnings)


def test_unsupported_award_is_clear(tmp_path: Path) -> None:
    engine, _ = _award_engine(tmp_path)
    with pytest.raises(KeyError, match="unsupported award"):
        engine.rank("invented_award", datetime.now(UTC))


def test_tie_rules_allocate_winner_mass(tmp_path: Path) -> None:
    engine, as_of = _award_engine(tmp_path)
    candidates = pd.DataFrame(
        [
            {
                "player_id": player,
                "player_name": player,
                "team_name": player,
                "position": "Forward",
                "goals": 2,
                "expected_additional_goals": 0,
                "expected_remaining_minutes": 0,
                "goal_rate_90": 0.2,
            }
            for player in ("a", "b")
        ]
    )
    result = engine._simulate_scoring(
        "wsl_golden_boot", "2023/2024", as_of, candidates, 100, 42, True
    )
    assert [item.winner_probability for item in result.candidates] == [0.5, 0.5]
    assert all(item.shared_award_probability == 1 for item in result.candidates)


def test_assists_then_minutes_breaks_scoring_ties(tmp_path: Path) -> None:
    engine, as_of = _award_engine(tmp_path)
    candidates = pd.DataFrame(
        [
            {
                "player_id": "assists",
                "player_name": "Assists Leader",
                "team_name": "A",
                "position": "Forward",
                "goals": 4,
                "assists": 2,
                "minutes": 500,
                "expected_additional_goals": 0,
                "expected_remaining_minutes": 0,
                "goal_rate_90": 0.5,
            },
            {
                "player_id": "minutes",
                "player_name": "Minutes Leader",
                "team_name": "B",
                "position": "Forward",
                "goals": 4,
                "assists": 1,
                "minutes": 400,
                "expected_additional_goals": 0,
                "expected_remaining_minutes": 0,
                "goal_rate_90": 0.5,
            },
        ]
    )
    result = engine._simulate_scoring(
        "world_cup_golden_boot",
        "2022",
        as_of,
        candidates,
        100,
        42,
        True,
        "assists_then_minutes",
    )
    by_id = {item.candidate_id: item for item in result.candidates}
    assert by_id["assists"].winner_probability == 1
    assert by_id["minutes"].winner_probability == 0
    assert all(item.shared_award_probability == 0 for item in result.candidates)


def test_european_golden_shoe_applies_league_coefficients(tmp_path: Path) -> None:
    engine, _ = _award_engine(tmp_path)
    candidates = pd.DataFrame(
        [
            {
                "award_id": "european_golden_shoe",
                "edition": "2025/2026",
                "candidate_id": "weighted",
                "candidate_name": "Weighted League Player",
                "team_name": "A",
                "position": "Forward",
                "current_goals": 10,
                "league_coefficient": 2.0,
                "expected_additional_goals": 0.0,
                "candidate_pool_complete": True,
                "schedule_complete": True,
                "availability_cutoff": "2026-01-01T00:00:00Z",
                "source": "licensed leaderboard",
            },
            {
                "award_id": "european_golden_shoe",
                "edition": "2025/2026",
                "candidate_id": "raw",
                "candidate_name": "Raw Goals Leader",
                "team_name": "B",
                "position": "Forward",
                "current_goals": 12,
                "league_coefficient": 1.0,
                "expected_additional_goals": 0.0,
                "candidate_pool_complete": True,
                "schedule_complete": True,
                "availability_cutoff": "2026-01-01T00:00:00Z",
                "source": "licensed leaderboard",
            },
        ]
    )
    engine.store.write_frame("award_candidates", candidates)
    result = engine.rank(
        "european_golden_shoe",
        datetime(2026, 2, 1, tzinfo=UTC),
        edition="2025/2026",
        simulations=100,
    )
    assert result.candidates[0].candidate_id == "weighted"
    assert result.candidates[0].winner_probability == 1
    assert result.source_attribution == ["licensed leaderboard"]


def test_dashboard_uses_central_award_engine() -> None:
    source = Path("src/soccer_engine/dashboard/app.py").read_text()
    assert "AwardEngine(service.store)" in source
    assert "award_engine.rank(" in source


def test_award_api_schemas_and_unavailable_behavior_are_stable() -> None:
    client = TestClient(app)
    assert client.get("/api/v1/awards").status_code == 200
    definition = client.get("/api/v1/awards/ballon_dor")
    assert definition.status_code == 200
    assert definition.json()["category"] == "narrative"
    assert client.get("/api/v1/awards/ballon_dor/editions").status_code == 200
    prediction = client.get(
        "/api/v1/awards/ballon_dor/predictions",
        params={"as_of": "2025-06-01T00:00:00Z", "edition": "2025"},
    )
    assert prediction.status_code == 200
    assert prediction.json()["status"] == "unavailable"
    missing = client.get("/api/v1/awards/not_real")
    assert missing.status_code == 404


def test_all_award_api_operations_use_central_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _ = _award_engine(tmp_path)
    api_module = importlib.import_module("soccer_engine.api.app")
    monkeypatch.setattr(api_module, "_award_engine", lambda: engine)
    client = TestClient(app)
    params = {"as_of": "2023-10-15T00:00:00Z", "edition": "2023/2024"}
    for suffix in (
        "candidates",
        "rankings",
        "predictions",
        "leaderboard",
        "history",
        "evaluation",
    ):
        response = client.get(f"/api/v1/awards/wsl_golden_boot/{suffix}", params=params)
        assert response.status_code == 200
    media = _media(datetime(2025, 5, 1, tzinfo=UTC)).model_dump(mode="json")
    assert (
        client.post("/api/v1/awards/ballon_dor/media-observations", json=[media]).status_code == 200
    )
    recomputed = client.post(
        "/api/v1/awards/recompute",
        json={
            "award_id": "wsl_golden_boot",
            "edition": "2023/2024",
            "as_of": "2023-10-15T00:00:00Z",
            "simulations": 200,
            "seed": 42,
        },
    )
    assert recomputed.status_code == 200
    assert recomputed.json()["status"] == "statistical_only"


def test_historical_evaluation_is_chronological(tmp_path: Path) -> None:
    engine, _ = _award_engine(tmp_path)
    report = evaluate_awards(engine, output=tmp_path / "evaluation.json", simulations=200)
    cutoffs = [pd.Timestamp(item["as_of"]) for item in report["edition_results"]]
    assert cutoffs == sorted(cutoffs)
    assert [item["stage"] for item in report["edition_results"]] == [
        "early",
        "midseason",
        "late",
    ]


def test_time_travel_snapshots_are_immutable_and_ordered(tmp_path: Path) -> None:
    engine, first_cutoff = _award_engine(tmp_path)
    second_cutoff = first_cutoff + timedelta(days=14)
    engine.rank("wsl_golden_boot", first_cutoff, "2023/2024", simulations=200)
    engine.rank("wsl_golden_boot", second_cutoff, "2023/2024", simulations=200)
    history = engine.history("wsl_golden_boot")
    assert len(history) == 2
    assert [item["as_of"] for item in history] == sorted(item["as_of"] for item in history)
    assert history[0]["data_version"] != history[1]["data_version"]
