"""Credential-free cloud bootstrap for the bundled offline demonstration."""

import logging
from pathlib import Path
from threading import Lock

from soccer_engine.config import get_settings

LOGGER = logging.getLogger(__name__)
_BOOTSTRAP_LOCK = Lock()


def _required_artifacts(data_dir: Path, model_dir: Path) -> tuple[Path, ...]:
    return (
        data_dir / "processed" / "matches.parquet",
        data_dir / "processed" / "player_match_stats.parquet",
        data_dir / "processed" / "goal_events.parquet",
        data_dir / "features" / "match_features.parquet",
        model_dir / "champion.joblib",
    )


def offline_demo_ready(data_dir: Path | None = None, model_dir: Path | None = None) -> bool:
    """Return whether every generated artifact required by the offline UI exists."""

    settings = get_settings()
    resolved_data = data_dir or settings.data_dir
    resolved_models = model_dir or settings.model_dir
    return all(path.exists() for path in _required_artifacts(resolved_data, resolved_models))


def ensure_offline_demo() -> bool:
    """Build the bundled demo once when a fresh cloud clone has no generated assets.

    Returns ``True`` when this call generated the assets and ``False`` when an existing
    installation was already ready. The workflow uses only committed, attributed sample data.
    """

    settings = get_settings()
    with _BOOTSTRAP_LOCK:
        if offline_demo_ready(settings.data_dir, settings.model_dir):
            return False

        LOGGER.info("cloud_offline_demo_bootstrap_started")
        # Imported lazily so normal API startup does not load the CLI orchestration layer.
        from soccer_engine.cli import build_features, ingest, ingest_player_data, normalize, train

        ingest(competition_id="37", season_id="281", sample=True)
        normalize(competition_id="37", season_id="281")
        ingest_player_data(sample=True)
        build_features()
        train()

        missing = [
            str(path)
            for path in _required_artifacts(settings.data_dir, settings.model_dir)
            if not path.exists()
        ]
        if missing:
            raise RuntimeError(f"offline demo bootstrap did not create: {', '.join(missing)}")
        LOGGER.info("cloud_offline_demo_bootstrap_completed")
        return True
