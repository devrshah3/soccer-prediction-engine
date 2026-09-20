from pathlib import Path

import yaml

from soccer_engine.cloud import offline_demo_ready


def test_cloud_configuration_uses_safe_production_commands() -> None:
    root = Path(__file__).parents[1]
    entrypoint = (root / "streamlit_app.py").read_text()
    requirements = (root / "requirements.txt").read_text()
    streamlit_config = (root / ".streamlit" / "config.toml").read_text()
    render = yaml.safe_load((root / "render.yaml").read_text())
    service = render["services"][0]

    assert "soccer_engine.dashboard.app" in entrypoint
    assert "-e ." in requirements
    assert "headless = true" in streamlit_config
    assert ".streamlit/secrets.toml" in (root / ".gitignore").read_text()
    assert service["buildCommand"] == (
        "pip install --upgrade pip && pip install . && soccer-engine demo"
    )
    assert service["startCommand"] == (
        "uvicorn soccer_engine.api.app:app --host 0.0.0.0 --port $PORT"
    )
    assert service["healthCheckPath"] == "/api/v1/health"


def test_offline_demo_readiness_requires_every_generated_artifact(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    model_dir = tmp_path / "models"
    required = (
        data_dir / "processed" / "matches.parquet",
        data_dir / "processed" / "player_match_stats.parquet",
        data_dir / "processed" / "goal_events.parquet",
        data_dir / "features" / "match_features.parquet",
        model_dir / "champion.joblib",
    )
    assert not offline_demo_ready(data_dir, model_dir)
    for path in required:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    assert offline_demo_ready(data_dir, model_dir)
