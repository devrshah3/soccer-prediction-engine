import shutil
from pathlib import Path

from soccer_engine.ingestion.statsbomb import StatsBombOpenDataProvider


def test_bundled_statsbomb_sample_is_real_and_parseable(tmp_path: Path) -> None:
    provider = StatsBombOpenDataProvider(tmp_path)
    source = Path("src/soccer_engine/sample_data/wsl_2023_24.json")
    target = tmp_path / "matches" / "37" / "281.json"
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    matches = provider.fetch_matches("37", "281")
    assert len(matches) == 132
    assert {match.provider for match in matches} == {"statsbomb_open_data"}
    assert all(
        match.source_url.startswith("https://raw.githubusercontent.com/statsbomb")
        for match in matches
    )
