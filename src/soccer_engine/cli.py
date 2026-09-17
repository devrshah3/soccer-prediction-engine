"""Command-line workflows."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from soccer_engine.config import get_settings
from soccer_engine.features.team import build_match_features
from soccer_engine.inference import predict_fixture
from soccer_engine.ingestion import FootballDataOrgProvider, StatsBombOpenDataProvider
from soccer_engine.normalization import deduplicate_matches, records_to_frame
from soccer_engine.storage import LocalStore
from soccer_engine.training import ModelBundle, train_and_evaluate
from soccer_engine.utils.logging import configure_logging

app = typer.Typer(no_args_is_help=True, help="Time-safe global soccer prediction workflows.")


def _store() -> LocalStore:
    settings = get_settings()
    return LocalStore(settings.data_dir)


@app.command()
def ingest(
    competition_id: Annotated[str, typer.Option(help="StatsBomb competition ID")] = "37",
    season_id: Annotated[str, typer.Option(help="StatsBomb season ID")] = "281",
    sample: Annotated[bool, typer.Option(help="Use the bundled attributed offline sample")] = False,
) -> None:
    """Cache a StatsBomb Open Data match index."""

    settings = get_settings()
    provider = StatsBombOpenDataProvider(settings.data_dir / "raw" / "statsbomb")
    if sample:
        source = Path(__file__).parent / "sample_data" / "wsl_2023_24.json"
        target = provider.cache_dir / "matches" / competition_id / f"{season_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    matches = provider.fetch_matches(competition_id, season_id)
    typer.echo(f"Cached and validated {len(matches)} StatsBomb matches.")


@app.command()
def normalize(
    competition_id: str = "37",
    season_id: str = "281",
) -> None:
    """Normalize cached provider data into Parquet and DuckDB layers."""

    settings = get_settings()
    provider = StatsBombOpenDataProvider(settings.data_dir / "raw" / "statsbomb")
    records = deduplicate_matches(provider.fetch_matches(competition_id, season_id))
    frame = records_to_frame(records)
    store = _store()
    store.initialize()
    path = store.write_frame("matches", frame)
    typer.echo(f"Wrote {len(frame)} normalized matches to {path}.")


@app.command("build-features")
def build_features() -> None:
    """Build leakage-safe pre-match feature tables."""

    store = _store()
    frame = build_match_features(store.read_frame("matches"))
    path = store.write_frame("match_features", frame, layer="features")
    typer.echo(f"Wrote {len(frame)} time-safe rows to {path}.")


@app.command()
def train() -> None:
    """Select, fit, and version outcome and goal models."""

    settings = get_settings()
    bundle, report = train_and_evaluate(
        _store().read_frame("matches"),
        settings.model_dir / "champion.joblib",
        Path("reports/evaluation.json"),
    )
    typer.echo(f"Champion: {report['champion']} · model version {bundle.version}")
    typer.echo(json.dumps(report["test"], indent=2))


@app.command()
def evaluate() -> None:
    """Print the immutable report produced during champion training."""

    path = Path("reports/evaluation.json")
    if not path.exists():
        raise typer.BadParameter("evaluation missing; run soccer-engine train")
    typer.echo(path.read_text())


@app.command("update-fixtures")
def update_fixtures(
    competition: Annotated[str, typer.Option(help="football-data.org competition code")] = "PL",
) -> None:
    """Refresh upcoming fixtures through the optional authenticated provider."""

    provider = FootballDataOrgProvider()
    records = provider.fetch_upcoming_fixtures(competition)
    new_frame = records_to_frame(records)
    store = _store()
    try:
        existing = store.read_frame("matches")
        combined = pd.concat([existing, new_frame], ignore_index=True)
    except FileNotFoundError:
        combined = new_frame
    combined = combined.sort_values("ingested_at").drop_duplicates("match_id", keep="last")
    store.write_frame("matches", combined)
    typer.echo(f"Updated {len(new_frame)} scheduled {competition} fixtures.")


def _prediction_for_id(fixture_id: str) -> str:
    settings = get_settings()
    matches = _store().read_frame("matches")
    selected = matches[matches["match_id"] == fixture_id]
    if selected.empty:
        raise typer.BadParameter(f"unknown fixture ID: {fixture_id}")
    features = build_match_features(matches)
    feature = features[features["match_id"] == fixture_id]
    bundle = ModelBundle.load(settings.model_dir / "champion.joblib")
    result = predict_fixture(selected.iloc[0], feature, bundle)
    return result.model_dump_json(indent=2)


@app.command()
def predict(fixture_id: Annotated[str, typer.Option(help="Provider-qualified fixture ID")]) -> None:
    """Predict a selected normalized fixture."""

    typer.echo(_prediction_for_id(fixture_id))


@app.command("predict-date")
def predict_date(
    target_date: Annotated[str, typer.Option("--date", help="UTC date: YYYY-MM-DD")],
) -> None:
    """Predict all scheduled fixtures on a UTC calendar date."""

    matches = _store().read_frame("matches")
    kickoff = pd.to_datetime(matches["kickoff"], utc=True)
    try:
        parsed_date = pd.Timestamp(target_date).date()
    except ValueError as error:
        raise typer.BadParameter("date must use YYYY-MM-DD") from error
    selected = matches[(kickoff.dt.date == parsed_date) & (matches["status"] == "scheduled")]
    if selected.empty:
        typer.echo("No scheduled fixtures found for that date.")
        raise typer.Exit()
    for fixture_id in selected["match_id"]:
        typer.echo(_prediction_for_id(str(fixture_id)))


@app.command("rank-awards")
def rank_awards(award: str, as_of: str) -> None:
    """Expose the award interface without inventing rankings before Phase 4."""

    raise typer.BadParameter(
        f"{award} ranking as of {as_of} is unavailable until cutoff-safe candidate data is ingested"
    )


@app.command("serve-api")
def serve_api(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the FastAPI service."""

    import uvicorn

    uvicorn.run("soccer_engine.api.app:app", host=host, port=port, reload=False)


@app.command()
def dashboard() -> None:
    """Run the Streamlit dashboard."""

    path = Path(__file__).parent / "dashboard" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(path)], check=True)


@app.command()
def demo() -> None:
    """Run the full offline sample pipeline and print one holdout prediction."""

    ingest(sample=True)
    normalize()
    build_features()
    train()
    matches = _store().read_frame("matches").sort_values("kickoff")
    held_out = matches.iloc[int(len(matches) * 0.85)]
    typer.echo("Time-safe historical replay from the held-out period:")
    typer.echo(_prediction_for_id(str(held_out["match_id"])))


def main() -> None:
    configure_logging(get_settings().log_level)
    app()


if __name__ == "__main__":
    main()
