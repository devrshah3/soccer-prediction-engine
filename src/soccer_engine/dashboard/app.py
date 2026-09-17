"""Recruiter-friendly Streamlit interface."""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from soccer_engine.features.team import build_match_features
from soccer_engine.inference.predictor import predict_fixture
from soccer_engine.storage import LocalStore
from soccer_engine.training import ModelBundle

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
    "Explore", ["Match predictions", "Model performance", "Data quality", "Award rankings"]
)


def load_assets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, ModelBundle]:
    store = LocalStore()
    matches = store.read_frame("matches")
    try:
        players = store.read_frame("player_match_stats")
        goals = store.read_frame("goal_events")
    except FileNotFoundError:
        players, goals = pd.DataFrame(), pd.DataFrame()
    return matches, players, goals, ModelBundle.load(Path("models/champion.joblib"))


try:
    matches, player_matches, goal_events, bundle = load_assets()
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
    feature = build_match_features(matches)
    feature = feature[feature["match_id"] == fixture_id]
    prediction = predict_fixture(
        fixture,
        feature,
        bundle,
        player_matches=player_matches,
        goal_events=goal_events,
    )
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
elif page == "Model performance":
    report_file = Path("reports/evaluation.json")
    if not report_file.exists():
        st.warning("Evaluation report not found.")
    else:
        report = json.loads(report_file.read_text())
        st.subheader("Untouched chronological holdout")
        st.json(report["test"])
        st.caption(report["warning"])
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
