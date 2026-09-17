import shutil
from pathlib import Path

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
    bundle, report = train_and_evaluate(
        matches,
        model_path=tmp_path / "model.joblib",
        report_path=tmp_path / "evaluation.json",
    )
    features = build_match_features(matches)
    index = int(len(matches) * 0.9)
    prediction = predict_fixture(matches.iloc[index], features.iloc[[index]], bundle)
    assert prediction.outcome.home_win + prediction.outcome.draw + prediction.outcome.away_win == 1
    assert len(prediction.likely_scorelines) == 5
    assert report["dataset"]["matches"] == 132
