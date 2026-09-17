"""Command-line workflows."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer

from soccer_engine.batch import BatchEngine, BatchJobRequest
from soccer_engine.config import coverage_report, get_settings
from soccer_engine.evaluation.global_report import generate_global_evaluation
from soccer_engine.evaluation.live import evaluate_live_replays
from soccer_engine.evaluation.scorer_report import generate_scorer_evaluation
from soccer_engine.features.team import build_match_features
from soccer_engine.inference import predict_fixture
from soccer_engine.ingestion import FootballDataOrgProvider, StatsBombOpenDataProvider
from soccer_engine.live import StatsBombReplay
from soccer_engine.normalization import deduplicate_matches, records_to_frame
from soccer_engine.normalization.players import normalize_statsbomb_players
from soccer_engine.services import SoccerService
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


@app.command("ingest-global-sample")
def ingest_global_sample() -> None:
    """Load every cataloged StatsBomb match index from the bundled attributed snapshot."""

    source = Path(__file__).parent / "sample_data" / "statsbomb_global_matches.json"
    if not source.exists():
        raise typer.BadParameter(
            "generated snapshot missing; run scripts/build_global_statsbomb_sample.py first"
        )
    payload = json.loads(source.read_text())
    frame = pd.DataFrame(payload["matches"])
    path = _store().write_frame("matches", frame)
    typer.echo(
        f"Wrote {len(frame)} unique matches across "
        f"{frame['competition_name'].nunique()} observed competitions to {path}."
    )


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


@app.command("ingest-player-data")
def ingest_player_data(
    sample: Annotated[bool, typer.Option(help="Use the compact attributed offline sample")] = False,
) -> None:
    """Ingest player-match statistics, lineup participation, and goal events."""

    store = _store()
    if sample:
        expanded = Path(__file__).parent / "sample_data" / "statsbomb_wsl_players.json"
        source = (
            expanded
            if expanded.exists()
            else Path(__file__).parent / "sample_data" / "wsl_2023_24_players.json"
        )
        payload = json.loads(source.read_text())
        player_frame = pd.DataFrame(payload["player_matches"])
        goal_frame = pd.DataFrame(payload["goal_events"])
    else:
        matches = store.read_frame("matches")
        provider = StatsBombOpenDataProvider(get_settings().data_dir / "raw" / "statsbomb")
        player_rows: list[dict[str, Any]] = []
        goal_rows: list[dict[str, Any]] = []
        for raw_match in matches.itertuples(index=False):
            match: Any = raw_match
            if match.provider != provider.name:
                continue
            provider_id = str(match.provider_match_id)
            source_url = f"{provider.base_url}/events/{provider_id}.json"
            players, goals = normalize_statsbomb_players(
                match_id=str(match.match_id),
                kickoff=pd.Timestamp(match.kickoff).to_pydatetime(),
                lineups=provider.fetch_lineups(provider_id),
                events=provider.fetch_events(provider_id),
                source_url=source_url,
            )
            player_rows.extend(record.model_dump(mode="json") for record in players)
            goal_rows.extend(record.model_dump(mode="json") for record in goals)
        player_frame = pd.DataFrame(player_rows)
        goal_frame = pd.DataFrame(goal_rows)
    player_path = store.write_frame("player_match_stats", player_frame)
    goal_path = store.write_frame("goal_events", goal_frame)
    typer.echo(
        f"Wrote {len(player_frame)} player-match rows to {player_path} "
        f"and {len(goal_frame)} goal events to {goal_path}."
    )


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
    try:
        player_matches = _store().read_frame("player_match_stats")
    except FileNotFoundError:
        player_matches = pd.DataFrame()
    bundle, report = train_and_evaluate(
        _store().read_frame("matches"),
        settings.model_dir / "champion.joblib",
        Path("reports/evaluation.json"),
        player_matches=player_matches,
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


@app.command("evaluate-global")
def evaluate_global() -> None:
    """Run expanding, rolling, season, league, and tournament evaluations."""

    report = generate_global_evaluation(_store().read_frame("matches"))
    typer.echo(json.dumps(report, indent=2))


@app.command("evaluate-scorers")
def evaluate_scorers() -> None:
    """Evaluate scorer probabilities on a complete future-season holdout."""

    store = _store()
    report = generate_scorer_evaluation(
        store.read_frame("matches"), store.read_frame("player_match_stats")
    )
    typer.echo(json.dumps(report, indent=2))


@app.command()
def coverage(
    output: Annotated[Path | None, typer.Option(help="Optional JSON output path")] = None,
) -> None:
    """Report configured capability separately from locally observed records."""

    report = coverage_report()
    rendered = json.dumps(report, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered)
    typer.echo(rendered)


@app.command("update-fixtures")
def update_fixtures(
    competition: Annotated[str, typer.Option(help="football-data.org competition code")] = "PL",
) -> None:
    """Refresh upcoming fixtures through the optional authenticated provider."""

    try:
        provider = FootballDataOrgProvider()
    except ValueError as error:
        raise typer.BadParameter(
            "live refresh is credential-required; set FOOTBALL_DATA_ORG_API_KEY"
        ) from error
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
    active = combined[combined["status"].isin(["scheduled", "postponed"])]
    store.write_frame("fixtures", active)
    typer.echo(
        f"Refreshed {len(new_frame)} {competition} records; {len(active)} active fixtures cached."
    )


@app.command("fixtures")
def list_fixtures(
    target_date: Annotated[str | None, typer.Option("--date", help="Local date YYYY-MM-DD")] = None,
    competition: Annotated[str | None, typer.Option(help="Exact competition name")] = None,
    timezone: Annotated[str, typer.Option(help="IANA timezone")] = "UTC",
) -> None:
    """List active fixtures with user-facing timezone conversion."""

    try:
        frame = SoccerService().fixtures(
            target_date=target_date, competition=competition, timezone=timezone
        )
    except (FileNotFoundError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    if frame.empty:
        typer.echo(
            "No scheduled or postponed fixtures matched; live data may be unavailable or stale."
        )
        return
    columns = [
        "match_id",
        "competition_name",
        "kickoff",
        "home_team_name",
        "away_team_name",
        "status",
    ]
    typer.echo(frame[columns].to_string(index=False))


def _prediction_for_id(fixture_id: str) -> str:
    settings = get_settings()
    matches = _store().read_frame("matches")
    selected = matches[matches["match_id"] == fixture_id]
    if selected.empty:
        raise typer.BadParameter(f"unknown fixture ID: {fixture_id}")
    features = build_match_features(matches)
    feature = features[features["match_id"] == fixture_id]
    bundle = ModelBundle.load(settings.model_dir / "champion.joblib")
    try:
        player_matches = _store().read_frame("player_match_stats")
        goal_events = _store().read_frame("goal_events")
    except FileNotFoundError:
        player_matches = pd.DataFrame()
        goal_events = pd.DataFrame()
    result = predict_fixture(
        selected.iloc[0],
        feature,
        bundle,
        player_matches=player_matches,
        goal_events=goal_events,
    )
    return result.model_dump_json(indent=2)


@app.command()
def predict(fixture_id: Annotated[str, typer.Option(help="Provider-qualified fixture ID")]) -> None:
    """Predict a selected normalized fixture."""

    typer.echo(_prediction_for_id(fixture_id))


@app.command("predict-date")
def predict_date(
    target_date: Annotated[str, typer.Option("--date", help="UTC date: YYYY-MM-DD")],
    competition: Annotated[
        str | None, typer.Option(help="Competition name or provider code")
    ] = None,
    workers: Annotated[int, typer.Option(min=1, max=32)] = 4,
    timezone: Annotated[str, typer.Option(help="IANA timezone for the selected date")] = "UTC",
    historical_replay: Annotated[
        bool, typer.Option(help="Allow time-safe predictions for completed historical fixtures")
    ] = False,
    force: Annotated[
        bool, typer.Option(help="Regenerate even when the input fingerprint is cached")
    ] = False,
) -> None:
    """Run or resume concurrent, tiered inference for every fixture on a date."""

    try:
        request = BatchJobRequest(
            date=target_date,
            competition=competition,
            workers=workers,
            timezone=timezone,
            allow_historical_replay=historical_replay,
            force=force,
        )
        engine = BatchEngine()
        job = engine.run(request)
    except (FileNotFoundError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(job.model_dump_json(indent=2))


@app.command("batch-status")
def batch_status(job_id: Annotated[str, typer.Option(help="Deterministic batch job ID")]) -> None:
    """Inspect an interrupted, running, or completed daily job."""

    try:
        typer.echo(BatchEngine().get_job(job_id).model_dump_json(indent=2))
    except KeyError as error:
        raise typer.BadParameter(f"unknown batch job: {job_id}") from error


@app.command("daily-summary")
def daily_summary(
    target_date: Annotated[str, typer.Option("--date", help="Date used for batch inference")],
) -> None:
    """Report prediction tiers, failures, caching, providers, and processing time."""

    engine = BatchEngine()
    job = engine.find_daily_job(target_date)
    if job is None:
        raise typer.BadParameter(f"no batch job found for {target_date}")
    typer.echo(engine.summary(job).model_dump_json(indent=2))


@app.command("live-replay")
def live_replay(
    match_id: Annotated[str, typer.Option(help="StatsBomb-qualified normalized match ID")],
    interval: Annotated[int, typer.Option(min=1, max=45)] = 5,
) -> None:
    """Run an accelerated historical event replay; output is explicitly not live."""

    try:
        result = StatsBombReplay().run(match_id, interval)
    except (KeyError, FileNotFoundError) as error:
        raise typer.BadParameter(f"replay unavailable: {error}") from error
    typer.echo(result.model_dump_json(indent=2))


@app.command("evaluate-live-replay")
def evaluate_live_replay(
    limit: Annotated[int, typer.Option(min=1, max=500)] = 50,
    interval: Annotated[int, typer.Option(min=1, max=45)] = 10,
) -> None:
    """Backtest live-state probabilities on a chronological historical replay holdout."""

    report = evaluate_live_replays(StatsBombReplay(), limit=limit, interval_minutes=interval)
    typer.echo(json.dumps(report, indent=2))


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
    ingest_player_data(sample=True)
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
