"""Recruiter-friendly Streamlit interface."""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from soccer_engine.batch import BatchEngine, BatchJobRequest
from soccer_engine.config import coverage_report
from soccer_engine.live import LiveEngine, StatsBombReplay
from soccer_engine.live.schemas import ReplayResult
from soccer_engine.services import SoccerService
from soccer_engine.storage import LocalStore

st.set_page_config(page_title="Global Soccer Prediction Engine", page_icon="⚽", layout="wide")
st.markdown(
    """
    <style>
    .stApp {background: linear-gradient(150deg, #071a15 0%, #102b24 55%, #071a15 100%);}
    [data-testid="stMetric"] {
      background:#12372f; border:1px solid #2e695a; padding:1rem; border-radius:12px;
    }
    h1, h2, h3 {letter-spacing:-0.025em;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("⚽ Global Soccer Prediction Engine")
st.caption(
    "Time-safe, calibrated soccer analytics · Predictions are uncertain, not betting guarantees"
)

page = st.sidebar.radio(
    "Explore",
    [
        "Match predictions",
        "Today's fixture slate",
        "Batch processing",
        "Live and replay",
        "Upcoming fixtures",
        "Global competitions",
        "Model performance",
        "Cross-league evaluation",
        "Provider health",
        "Data quality",
        "Award rankings",
    ],
)


def load_assets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, SoccerService]:
    service = SoccerService(LocalStore())
    return (
        service.matches(),
        service.optional_table("player_match_stats"),
        service.optional_table("goal_events"),
        service,
    )


try:
    matches, player_matches, goal_events, service = load_assets()
except FileNotFoundError:
    st.error("No trained demo found. Run `soccer-engine demo`, then refresh this page.")
    st.stop()

if page == "Match predictions":
    competitions = sorted(matches["competition_name"].unique())
    competition = st.sidebar.selectbox("Competition", competitions)
    subset = matches[matches["competition_name"] == competition].sort_values(
        "kickoff", ascending=False
    )
    labels = {
        row.match_id: (
            f"{row.home_team_name} vs {row.away_team_name} · {pd.Timestamp(row.kickoff).date()}"
        )
        for row in subset.itertuples()
    }
    fixture_id = st.selectbox(
        "Fixture (historical fixtures are shown as time-safe replays)",
        labels,
        format_func=lambda value: labels.get(value, str(value)),
    )
    fixture = matches[matches["match_id"] == fixture_id].iloc[0]
    prediction = service.predict(str(fixture_id))
    st.subheader(f"{prediction.home_team} vs {prediction.away_team}")
    st.caption(f"{prediction.competition} · {prediction.kickoff:%Y-%m-%d %H:%M %Z}")
    left, middle, right = st.columns(3)
    left.metric("Home win", f"{prediction.outcome.home_win:.1%}")
    middle.metric("Draw", f"{prediction.outcome.draw:.1%}")
    right.metric("Away win", f"{prediction.outcome.away_win:.1%}")
    chart_left, chart_right = st.columns(2)
    score_frame = pd.DataFrame([item.model_dump() for item in prediction.likely_scorelines])
    score_frame["score"] = (
        score_frame["home_goals"].astype(str) + "–" + score_frame["away_goals"].astype(str)
    )
    figure = go.Figure(
        go.Bar(x=score_frame["score"], y=score_frame["probability"], marker_color="#31c48d")
    )
    figure.update_layout(
        title="Most likely scorelines", yaxis_tickformat=".0%", template="plotly_dark"
    )
    chart_left.plotly_chart(figure, width="stretch")
    chart_right.subheader("Forecast context")
    chart_right.write(
        f"Expected goals: **{prediction.expected_home_goals:.2f} – "
        f"{prediction.expected_away_goals:.2f}**"
    )
    chart_right.write(f"Both teams score: **{prediction.both_teams_to_score:.1%}**")
    chart_right.write(f"Over 2.5 goals: **{prediction.over_2_5:.1%}**")
    chart_right.write(f"Reliability: **{prediction.reliability.title()}**")
    scorer_tab, lineup_tab, timing_tab = st.tabs(
        ["Likely goalscorers", "Expected lineups", "Goal timing"]
    )
    with scorer_tab:
        scorer_frame = pd.DataFrame([item.model_dump() for item in prediction.likely_goalscorers])
        if scorer_frame.empty:
            st.info("Player history is unavailable for this provider/team identity.")
        else:
            scorer_frame = scorer_frame[
                [
                    "player_name",
                    "team_name",
                    "starting_probability",
                    "expected_minutes",
                    "expected_goals",
                    "scoring_probability",
                    "first_scorer_probability",
                    "reliability",
                ]
            ]
            st.dataframe(
                scorer_frame,
                hide_index=True,
                width="stretch",
                column_config={
                    "starting_probability": st.column_config.ProgressColumn(format="percent"),
                    "scoring_probability": st.column_config.ProgressColumn(format="percent"),
                    "first_scorer_probability": st.column_config.ProgressColumn(format="percent"),
                },
            )
            st.caption("No player probability is a guarantee; starting status is not confirmed.")
    with lineup_tab:
        lineup_frame = pd.DataFrame([item.model_dump() for item in prediction.expected_lineups])
        if lineup_frame.empty:
            st.info("No earlier compatible lineup data is available.")
        else:
            st.dataframe(
                lineup_frame[
                    [
                        "team_name",
                        "player_name",
                        "position",
                        "starting_probability",
                        "expected_minutes",
                        "reliability",
                    ]
                ],
                hide_index=True,
                width="stretch",
            )
    with timing_tab:
        interval_frame = pd.DataFrame([item.model_dump() for item in prediction.goal_intervals])
        timing_figure = go.Figure()
        timing_figure.add_bar(
            x=interval_frame["interval"],
            y=interval_frame["home_goal_probability"],
            name=prediction.home_team,
            marker_color="#31c48d",
        )
        timing_figure.add_bar(
            x=interval_frame["interval"],
            y=interval_frame["away_goal_probability"],
            name=prediction.away_team,
            marker_color="#60a5fa",
        )
        timing_figure.update_layout(barmode="group", yaxis_tickformat=".0%", template="plotly_dark")
        st.plotly_chart(timing_figure, width="stretch")
        st.caption("Broad pre-match intervals are shown instead of a fake precise goal minute.")
    st.info("The model assigns probability partly from: " + "; ".join(prediction.important_factors))
    for warning in prediction.warnings:
        st.warning(warning)
elif page == "Today's fixture slate":
    st.subheader("Daily fixture intelligence")
    selected_date = st.date_input("Date")
    competition_values = ["All", *sorted(matches["competition_name"].unique())]
    selected_competition = st.selectbox("Competition", competition_values)
    historical = st.checkbox("Historical replay mode", help="Clearly labeled, time-safe replays")
    if st.button("Run daily batch"):
        with st.spinner("Processing fixtures..."):
            engine = BatchEngine(service)
            job = engine.run(
                BatchJobRequest(
                    date=selected_date.isoformat(),
                    competition=None if selected_competition == "All" else selected_competition,
                    allow_historical_replay=historical,
                )
            )
            st.session_state["batch_job_id"] = job.job_id
    job_id = st.session_state.get("batch_job_id")
    if job_id:
        engine = BatchEngine(service)
        job = engine.get_job(job_id)
        summary = engine.summary(job)
        metrics = st.columns(4)
        metrics[0].metric("Fixtures", summary.total_discovered_fixtures)
        metrics[1].metric("Full tier", summary.full_tier_predictions)
        metrics[2].metric("Standard tier", summary.standard_tier_predictions)
        metrics[3].metric("Basic tier", summary.basic_tier_predictions)
        tiers = ["All", "full", "standard", "basic", "unavailable"]
        tier_filter = st.selectbox("Prediction tier", tiers)
        rows = [item.model_dump(mode="json") for item in job.results]
        result_frame = pd.DataFrame(rows)
        if not result_frame.empty and tier_filter != "All":
            result_frame = result_frame[result_frame["tier"] == tier_filter]
        st.dataframe(result_frame, hide_index=True, width="stretch")
        predicted = [item for item in job.results if item.prediction is not None]
        if predicted:
            opened = st.selectbox(
                "Open complete prediction",
                predicted,
                format_func=lambda item: f"{item.fixture_id} · {item.competition} · {item.tier}",
            )
            if opened.prediction is not None:
                st.json(opened.prediction.model_dump(mode="json"))
elif page == "Batch processing":
    st.subheader("Batch job progress and coverage")
    engine = BatchEngine(service)
    jobs = [engine.get_job(path.stem) for path in engine.jobs_dir.glob("*.json")]
    if not jobs:
        st.info("No daily jobs have been started.")
    else:
        job = st.selectbox(
            "Job",
            sorted(jobs, key=lambda item: item.updated_at, reverse=True),
            format_func=lambda item: f"{item.request.date} · {item.job_id} · {item.status}",
        )
        st.progress(len(job.results) / max(job.discovered_fixtures, 1))
        st.json(engine.summary(job).model_dump(mode="json"))
elif page == "Live and replay":
    st.subheader("Live-state and historical replay")
    st.warning(
        "No paid live feed is configured. StatsBomb replays are delayed historical data, "
        "never presented as live."
    )
    fixture_options = matches[matches["provider"] == "statsbomb_open_data"].sort_values(
        "kickoff", ascending=False
    )
    replay_labels = {
        str(row.match_id): f"{row.home_team_name} vs {row.away_team_name}"
        for row in fixture_options.itertuples()
    }
    replay_id = st.selectbox(
        "Historical match",
        fixture_options["match_id"].tolist(),
        format_func=lambda value: replay_labels[str(value)],
    )
    if st.button("Run accelerated replay"):
        with st.spinner("Revealing timestamped events chronologically..."):
            replay = StatsBombReplay(LiveEngine(service))
            try:
                result = replay.run(str(replay_id), interval_minutes=10)
                st.session_state["replay_result"] = result
            except FileNotFoundError:
                st.error("Cached events are unavailable. Run player/event ingestion first.")
    replay_result_value: ReplayResult | None = st.session_state.get("replay_result")
    if replay_result_value:
        movement = pd.DataFrame(
            [
                {
                    "minute": item.minute,
                    "home": item.prediction.outcome.home_win,
                    "draw": item.prediction.outcome.draw,
                    "away": item.prediction.outcome.away_win,
                    "pace": item.prediction.match_pace,
                    "home_pressure": item.prediction.home_pressure,
                    "away_pressure": item.prediction.away_pressure,
                    "next_5": item.prediction.goal_within_5_minutes,
                }
                for item in replay_result_value.snapshots
            ]
        )
        st.line_chart(movement.set_index("minute")[["home", "draw", "away"]])
        st.line_chart(movement.set_index("minute")[["pace", "home_pressure", "away_pressure"]])
        st.line_chart(movement.set_index("minute")[["next_5"]])
        st.caption(
            f"{replay_result_value.revealed_events} normalized events · "
            f"{replay_result_value.source}"
        )
        state = LiveEngine(service).state(replay_result_value.match_id)
        st.dataframe(
            pd.DataFrame([event.model_dump(mode="json") for event in state.events]),
            hide_index=True,
            width="stretch",
        )
elif page == "Upcoming fixtures":
    st.subheader("Upcoming fixtures")
    timezone = st.selectbox("Timezone", ["UTC", "America/New_York", "Europe/London", "Asia/Tokyo"])
    fixtures = service.fixtures(timezone=timezone)
    if fixtures.empty:
        st.warning(
            "No active fixtures are cached. Set FOOTBALL_DATA_ORG_API_KEY and run "
            "`soccer-engine update-fixtures`, or continue with historical replays."
        )
    else:
        st.dataframe(fixtures, hide_index=True, width="stretch")
elif page == "Global competitions":
    st.subheader("Global competition and season coverage")
    report = coverage_report()
    st.metric("Registered priority competitions", report["registered_competitions"])
    st.metric("Observed StatsBomb competition-seasons", report["observed_statsbomb_pairs"])
    coverage_frame = pd.DataFrame(report["rows"])
    region = st.selectbox("Region", ["All", *sorted(coverage_frame["region"].unique())])
    if region != "All":
        coverage_frame = coverage_frame[coverage_frame["region"] == region]
    st.dataframe(coverage_frame, hide_index=True, width="stretch")
    st.caption(
        "Adapter-ready is capability metadata, not a claim that records are locally ingested."
    )
elif page == "Model performance":
    report_file = Path("reports/evaluation.json")
    if not report_file.exists():
        st.warning("Evaluation report not found.")
    else:
        report = json.loads(report_file.read_text())
        st.subheader("Untouched chronological holdout")
        st.json(report["test"])
        st.caption(report["warning"])
elif page == "Cross-league evaluation":
    path = Path("reports/global_evaluation.json")
    st.subheader("Cross-league and chronological evaluation")
    if not path.exists():
        st.warning("Run `soccer-engine evaluate-global` to generate this report.")
    else:
        report = json.loads(path.read_text())
        st.json(report["chronological_holdout"])
        st.subheader("Leave-one-competition-out results")
        st.json(report["cross_league_holdouts"])
elif page == "Provider health":
    st.subheader("Provider health and credentials")
    providers = pd.DataFrame(
        [
            ["StatsBomb Open Data", "Available", "No", "Historical matches/events"],
            ["football-data.co.uk", "Adapter ready", "No", "User-supplied CSV only"],
            ["football-data.org", "Credential required", "Yes", "Upcoming fixtures"],
            ["API-Football", "Adapter ready", "Yes", "Licensed future integration"],
            ["Sportmonks", "Adapter ready", "Yes", "Licensed future integration"],
            ["OpenLigaDB", "Adapter ready", "No", "Future public integration"],
        ],
        columns=["Provider", "Status", "Credential", "Scope"],
    )
    st.dataframe(providers, hide_index=True, width="stretch")
elif page == "Data quality":
    st.subheader("Freshness and coverage")
    st.metric("Normalized matches", f"{len(matches):,}")
    player_metric, goal_metric = st.columns(2)
    player_metric.metric("Player-match rows", f"{len(player_matches):,}")
    goal_metric.metric("Goal events", f"{len(goal_events):,}")
    st.write("Providers", matches["provider"].value_counts())
    st.write("Latest kickoff", pd.to_datetime(matches["kickoff"], utc=True).max())
    st.info(
        "The Phase 2 sample contains prior lineups, minutes, shots, xG, goals, and assists. "
        "Current injuries and suspensions are not available."
    )
else:
    st.subheader("Award rankings")
    st.info(
        "Schema and ranking contract are ready. Rankings remain disabled until Phase 4 labels "
        "and cutoff-safe candidate data are ingested; no scores are fabricated."
    )
