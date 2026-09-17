import json
import shutil
from pathlib import Path

import pandas as pd

from soccer_engine.features.team import build_match_features
from soccer_engine.inference import predict_fixture
from soccer_engine.ingestion.statsbomb import StatsBombOpenDataProvider
from soccer_engine.normalization import records_to_frame
from soccer_engine.training import train_and_evaluate


def test_small_end_to_end_pipeline(tmp_path: Path) -> None:
    provider = StatsBombOpenDataProvider(tmp_path / "raw")
    source = Path("src/soccer_engine/sample_data/wsl_2023_24.json")
    target = provider.cache_dir / "matches" / "37" / "281.json"
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    matches = records_to_frame(provider.fetch_matches("37", "281"))
    payload = json.loads(Path("src/soccer_engine/sample_data/wsl_2023_24_players.json").read_text())
    player_matches = pd.DataFrame(payload["player_matches"])
    bundle, report = train_and_evaluate(
        matches,
        model_path=tmp_path / "model.joblib",
        report_path=tmp_path / "evaluation.json",
        player_matches=player_matches,
    )
    features = build_match_features(matches)
    index = int(len(matches) * 0.9)
    prediction = predict_fixture(
        matches.iloc[index],
        features.iloc[[index]],
        bundle,
        player_matches=player_matches,
        goal_events=pd.DataFrame(payload["goal_events"]),
    )
    assert prediction.outcome.home_win + prediction.outcome.draw + prediction.outcome.away_win == 1
    assert len(prediction.likely_scorelines) == 5
    assert len(prediction.expected_lineups) == 22
    assert prediction.likely_goalscorers
    assert len(prediction.goal_intervals) == 6
    assert report["test"]["goalscorers"]["available"] is True
    assert report["dataset"]["matches"] == 132
