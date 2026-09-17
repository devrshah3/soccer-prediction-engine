"""Local DuckDB and Parquet lakehouse storage."""

from pathlib import Path

import duckdb
import pandas as pd

ENTITY_TABLES = (
    "competitions",
    "seasons",
    "teams",
    "venues",
    "players",
    "matches",
    "match_team_stats",
    "player_match_stats",
    "lineups",
    "events",
    "goal_events",
    "fixtures",
    "provider_identities",
    "identity_review_queue",
    "coverage",
    "awards",
    "award_candidates",
    "predictions",
)


class LocalStore:
    """Persist layered Parquet datasets and query them through DuckDB."""

    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = data_dir
        self.processed_dir = data_dir / "processed"
        self.database_path = data_dir / "soccer_engine.duckdb"

    def initialize(self) -> None:
        """Create normalized entity tables and local layer directories."""

        for layer in ("raw", "interim", "processed", "features", "predictions"):
            (self.data_dir / layer).mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.database_path)) as connection:
            for name in ENTITY_TABLES:
                connection.execute(
                    f"CREATE TABLE IF NOT EXISTS {name} "
                    "(internal_id VARCHAR PRIMARY KEY, payload JSON, updated_at TIMESTAMPTZ)"
                )

    def write_frame(self, name: str, frame: pd.DataFrame, layer: str = "processed") -> Path:
        """Atomically write a dataframe to a named Parquet table."""

        target_dir = self.data_dir / layer
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{name}.parquet"
        temporary = target.with_suffix(".parquet.tmp")
        frame.to_parquet(temporary, index=False)
        temporary.replace(target)
        return target

    def read_frame(self, name: str, layer: str = "processed") -> pd.DataFrame:
        """Read a named Parquet table."""

        target = self.data_dir / layer / f"{name}.parquet"
        if not target.exists():
            raise FileNotFoundError(f"missing {layer} table {name!r}; run the preceding workflow")
        return pd.read_parquet(target)
