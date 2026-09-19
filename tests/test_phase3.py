import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from soccer_engine.api.app import app
from soccer_engine.config import CompetitionRegistry, coverage_report
from soccer_engine.evaluation.splits import rolling_window_splits
from soccer_engine.features.team import build_match_features
from soccer_engine.identity import IdentityCandidate, IdentityResolver, ResolutionStatus
from soccer_engine.ingestion import FootballDataOrgProvider, FootballDataUKProvider
from soccer_engine.normalization.matches import deduplicate_cross_provider_matches
from soccer_engine.schemas import MatchRecord, MatchStatus
from soccer_engine.services import SoccerService
from soccer_engine.storage import LocalStore


def _match(provider: str, identifier: str, home: str, away: str) -> MatchRecord:
    return MatchRecord(
        match_id=f"{provider}:{identifier}",
        provider=provider,
        provider_match_id=identifier,
        competition_id=f"{provider}:PL",
        competition_name="Premier League",
        season="2025/2026",
        kickoff=datetime(2026, 1, 1, 15, tzinfo=UTC),
        home_team_id=f"{provider}:{home}",
        home_team_name=home,
        away_team_id=f"{provider}:{away}",
        away_team_name=away,
        status=MatchStatus.FINISHED,
        home_score=1,
        away_score=0,
        source_url="test-only",
    )


def test_global_registry_and_observed_catalog_are_honest() -> None:
    registry = CompetitionRegistry()
    assert len(registry.competitions) >= 35
    report = coverage_report()
    assert report["observed_statsbomb_pairs"] == 80
    assert report["observed_statsbomb_matches"] == 3961
    assert any(row["status"] == "credential-required" for row in report["rows"])
    assert any(row["status"] == "adapter-ready" for row in report["rows"])


def test_global_catalog_exact_count() -> None:
    payload = json.loads(Path("src/soccer_engine/sample_data/statsbomb_catalog.json").read_text())
    assert len(payload["entries"]) == 80
    assert sum(row["matches"] for row in payload["entries"]) == 3961


def test_football_data_uk_normalizes_user_supplied_csv(tmp_path: Path) -> None:
    source = tmp_path / "2526"
    source.mkdir()
    (source / "E0.csv").write_text(
        "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG,Referee\n"
        "E0,16/08/2025,15:00,Man United,Arsenal,2,1,1,0,A Ref\n"
    )
    records = FootballDataUKProvider(tmp_path).fetch_matches("E0", "2526")
    assert len(records) == 1
    assert records[0].kickoff.tzinfo is not None
    assert records[0].status == MatchStatus.FINISHED


def test_football_data_org_mock_handles_fixture_statuses(monkeypatch, tmp_path: Path) -> None:
    provider = FootballDataOrgProvider(tmp_path, api_key="test-key")
    payload = {
        "matches": [
            {
                "id": 7,
                "utcDate": "2026-09-19T14:00:00Z",
                "status": "POSTPONED",
                "competition": {"code": "PL", "name": "Premier League"},
                "season": {"startDate": "2026-08-01"},
                "homeTeam": {"id": 1, "name": "Manchester United"},
                "awayTeam": {"id": 2, "name": "Arsenal"},
                "score": {"fullTime": {}, "halfTime": {}},
                "stage": "REGULAR_SEASON",
                "referees": [],
            }
        ]
    }
    monkeypatch.setattr(provider, "_get", lambda *_args, **_kwargs: payload)
    records = provider.fetch_upcoming_fixtures("PL")
    assert records[0].status == MatchStatus.POSTPONED
    assert (tmp_path / "fixtures_PL.json").exists()


def test_identity_uses_provider_ids_and_flags_ambiguity() -> None:
    resolver = IdentityResolver()
    resolver.register(IdentityCandidate("team:manu", "Manchester United", {"one": "10"}, "England"))
    resolver.register(IdentityCandidate("team:other", "Manchester United", {"two": "99"}, "USA"))
    assert (
        resolver.resolve("Man United", provider="one", provider_id="10").internal_id == "team:manu"
    )
    assert resolver.resolve("Manchester United").status == ResolutionStatus.AMBIGUOUS
    assert resolver.resolve("Manchester City").status == ResolutionStatus.UNMATCHED


def test_cross_provider_duplicate_is_flagged_not_silently_merged() -> None:
    records, review = deduplicate_cross_provider_matches(
        [
            _match("one", "1", "Man United", "Arsenal"),
            _match("two", "2", "Manchester United", "Arsenal FC"),
        ]
    )
    assert len(records) == 1
    assert review == [("one:1", "two:2")]


def test_cross_season_and_competition_features_remain_time_safe(
    small_matches: pd.DataFrame,
) -> None:
    frame = small_matches.copy()
    frame["competition_id"] = ["league:a" if i % 2 else "league:b" for i in range(len(frame))]
    frame["competition_name"] = frame["competition_id"]
    frame["season"] = ["2023/2024" if i < 20 else "2024/2025" for i in range(len(frame))]
    frame["stage"] = "Regular Season"
    original = build_match_features(frame)
    changed = frame.copy()
    changed.loc[39, ["home_score", "away_score"]] = [99, 0]
    rebuilt = build_match_features(changed)
    pd.testing.assert_frame_equal(original.iloc[:39], rebuilt.iloc[:39])
    assert {"competition_strength", "promoted_home", "opponent_adjusted_form"}.issubset(
        {name.removeprefix("home_") for name in original.columns} | set(original.columns)
    )


def test_rolling_splits_are_strictly_ordered(small_matches: pd.DataFrame) -> None:
    splits = list(rolling_window_splits(small_matches, train_size=20, test_size=5))
    assert splits
    assert all(train.max() < test.min() for train, test in splits)


def test_fixture_service_filters_status_date_and_timezone(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        [
            _match("one", "1", "A", "B").model_dump(mode="json"),
            {
                **_match("one", "2", "C", "D").model_dump(mode="json"),
                "status": "scheduled",
                "kickoff": "2026-09-19T01:00:00Z",
            },
        ]
    )
    store = LocalStore(tmp_path)
    store.write_frame("matches", frame)
    fixtures = SoccerService(store).fixtures(target_date="2026-09-18", timezone="America/New_York")
    assert fixtures["match_id"].tolist() == ["one:2"]


def test_versioned_phase3_api_routes_exist() -> None:
    paths = app.openapi()["paths"]
    required = {
        "/api/v1/competitions",
        "/api/v1/seasons",
        "/api/v1/fixtures",
        "/api/v1/predictions/{fixture_id}",
        "/api/v1/predictions/batch",
        "/api/v1/predictions/batch/{job_id}",
        "/api/v1/predictions/daily/{date}",
        "/api/v1/predictions/daily/{date}/summary",
        "/api/v1/live/events",
        "/api/v1/live/commentary",
        "/api/v1/live/matches",
        "/api/v1/live/matches/{fixture_id}",
        "/api/v1/live/matches/{fixture_id}/prediction",
        "/api/v1/live/matches/{fixture_id}/timeline",
        "/api/v1/live/replay/{match_id}",
        "/api/v1/awards",
        "/api/v1/awards/{award_id}",
        "/api/v1/awards/{award_id}/editions",
        "/api/v1/awards/{award_id}/candidates",
        "/api/v1/awards/{award_id}/rankings",
        "/api/v1/awards/{award_id}/predictions",
        "/api/v1/awards/{award_id}/leaderboard",
        "/api/v1/awards/{award_id}/history",
        "/api/v1/awards/{award_id}/evaluation",
        "/api/v1/awards/{award_id}/media-observations",
        "/api/v1/awards/recompute",
        "/api/v1/providers",
        "/api/v1/evaluation",
        "/api/v1/data-quality",
    }
    assert required.issubset(paths)
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["version"] == "0.4.0"
