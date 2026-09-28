"""kickcast_api/precompute.py: B.8's stored-prediction system - computed after every
ingest (scripts/ingest.py) and on a nightly schedule, so serving is a DB read instead of
a per-request model.predict() call.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api import precompute
from kickcast_api.models import Base, League, Match, PrecomputedPrediction, Team


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'precompute.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(League(code="test.1", name="Test League", country="Testland", kind="domestic_league"))
    for i in range(8):
        s.add(Team(id=f"team-{i}", name=f"Team {i}", country="Testland"))
    s.commit()

    d = date(2024, 8, 1)
    for match_id in range(1, 25):  # 24 finished matches - enough training history
        i = match_id - 1
        h, a = i % 8, (i + 1) % 8
        s.add(
            Match(
                league_code="test.1", season="2024-25", date=d, kickoff="15:00",
                home_team_id=f"team-{h}", away_team_id=f"team-{a}",
                home_goals=match_id % 4, away_goals=(match_id + 1) % 3,
                status="finished", round=f"Matchday {match_id}", neutral=False,
                source="synthetic", source_id=f"synthetic:{match_id}",
            )
        )
        d += timedelta(days=7)
    # Two upcoming fixtures: one inside the 90-day window, one well outside it.
    s.add(
        Match(
            league_code="test.1", season="2024-25", date=datetime.now(UTC).date() + timedelta(days=10),
            kickoff="15:00", home_team_id="team-0", away_team_id="team-1",
            home_goals=None, away_goals=None, status="scheduled", round="Matchday 25",
            neutral=False, source="synthetic", source_id="synthetic:upcoming-near",
        )
    )
    s.add(
        Match(
            league_code="test.1", season="2024-25", date=datetime.now(UTC).date() + timedelta(days=120),
            kickoff="15:00", home_team_id="team-2", away_team_id="team-3",
            home_goals=None, away_goals=None, status="scheduled", round="Matchday 26",
            neutral=False, source="synthetic", source_id="synthetic:upcoming-far",
        )
    )
    s.commit()
    return s


def test_precompute_writes_a_row_for_a_scheduled_match_inside_the_window(session):
    near = session.query(Match).filter(Match.source_id == "synthetic:upcoming-near").one()
    written = precompute.precompute_predictions(session)
    assert written >= 1
    row = session.get(PrecomputedPrediction, near.id)
    assert row is not None
    assert row.model_version and row.computed_at and row.data_cutoff


def test_precompute_skips_a_scheduled_match_outside_the_90_day_window(session):
    far = session.query(Match).filter(Match.source_id == "synthetic:upcoming-far").one()
    precompute.precompute_predictions(session)
    assert session.get(PrecomputedPrediction, far.id) is None


def test_get_precomputed_prediction_returns_none_when_not_yet_computed(session):
    far = session.query(Match).filter(Match.source_id == "synthetic:upcoming-far").one()
    assert precompute.get_precomputed_prediction(session, far.id) is None


def test_get_precomputed_prediction_round_trips_real_probabilities(session):
    near = session.query(Match).filter(Match.source_id == "synthetic:upcoming-near").one()
    precompute.precompute_predictions(session)
    pred = precompute.get_precomputed_prediction(session, near.id)
    assert pred is not None
    probs = pred["probabilities"]
    assert abs(sum(probs.values()) - 1) < 1e-6
    assert pred["computed_at"]


def test_precompute_updates_an_existing_row_rather_than_duplicating(session):
    near = session.query(Match).filter(Match.source_id == "synthetic:upcoming-near").one()
    precompute.precompute_predictions(session)
    precompute.precompute_predictions(session)  # run again, e.g. simulating the nightly job
    assert session.query(PrecomputedPrediction).filter(PrecomputedPrediction.match_id == near.id).count() == 1
