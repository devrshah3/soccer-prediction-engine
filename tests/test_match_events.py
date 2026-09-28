"""kickcast_api/match_events.py: goals + cards merged from martj42 (Goalscorer) and API-Football
(LiveEvent) with score-validated own-goal crediting and second-yellow -> single red."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.match_events import events_for_matches
from kickcast_api.models import Base, Goalscorer, League, LiveEvent, Match, Team


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ev.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(League(code="t", name="T", country="X", kind="domestic_league"))
    s.add_all([Team(id="home", name="Home", country="X"), Team(id="away", name="Away", country="X")])
    s.commit()
    return s


def _match(s, hg, ag, status="finished", day=27):
    m = Match(league_code="t", season="s", date=date(2026, 9, day), kickoff="16:00", home_team_id="home",
              away_team_id="away", home_goals=hg, away_goals=ag, status=status, round=None, neutral=False,
              source="t", source_id=f"t:{hg}:{ag}")
    s.add(m)
    s.commit()
    return m


def _live(s, m, minute, kind, team, player, detail):
    s.add(LiveEvent(match_id=m.id, minute=minute, event_type=kind, team_id=team, player=player, detail=detail, source="api-football"))


def test_goalscorer_csv_rows_with_penalty_and_own_goal(session):
    m = _match(session, 2, 1)
    for minute, team, name, og, pen in [(12, "home", "A Striker", False, False), (55, "home", "B Winger", False, True), (88, "home", "C Defender", True, False)]:
        session.add(Goalscorer(match_id=m.id, date=m.date, team_id=team, scorer_name=name, minute=minute, own_goal=og, penalty=pen, source="t"))
    session.commit()
    goals = events_for_matches(session, [m])[m.id]["goals"]
    assert [(g["minute"], g["scorer"], g["penalty"], g["own_goal"]) for g in goals] == [
        (12, "A Striker", False, False), (55, "B Winger", True, False), (88, "C Defender", False, True)]


def test_live_events_missed_penalty_is_not_a_goal_and_cards_are_typed(session):
    m = _match(session, 1, 0)
    _live(session, m, 20, "card", "away", "Def", "Yellow Card")
    _live(session, m, 30, "goal", "home", "Hitter", "Missed Penalty")
    _live(session, m, 40, "goal", "home", "Hitter", "Penalty")
    _live(session, m, 70, "card", "away", "Keeper", "Red Card")
    session.commit()
    ev = events_for_matches(session, [m])[m.id]
    assert [(g["minute"], g["scorer"], g["penalty"]) for g in ev["goals"]] == [(40, "Hitter", True)]
    assert [(c["minute"], c["player"], c["card"]) for c in ev["cards"]] == [(20, "Def", "yellow"), (70, "Keeper", "red")]


def test_second_yellow_is_one_red_at_that_minute(session):
    m = _match(session, 0, 0)
    _live(session, m, 30, "card", "home", "Rash", "Yellow Card")
    _live(session, m, 33, "card", "away", "Other", "Yellow Card")
    _live(session, m, 75, "card", "home", "Rash", "Second Yellow card")
    session.commit()
    cards = events_for_matches(session, [m])[m.id]["cards"]
    assert [(c["minute"], c["player"], c["card"]) for c in cards] == [(33, "Other", "yellow"), (75, "Rash", "red")]


def test_own_goal_is_credited_to_the_side_that_makes_the_score_add_up(session):
    # Final 1-0 to home; the only goal is an own goal reported under HOME (the own-goaler's
    # side would then be away): as-given gives 1-0 already -> keep.
    m = _match(session, 1, 0)
    _live(session, m, 50, "goal", "home", "P", "Own Goal")
    session.commit()
    assert events_for_matches(session, [m])[m.id]["goals"][0]["team_id"] == "home"
    # Final 0-1 (away won) but the OG is reported under HOME (the own-goaler's side): as-given
    # would credit home (1-0, wrong) -> flipped to away (0-1, matches).
    m2 = _match(session, 0, 1, day=26)
    _live(session, m2, 50, "goal", "home", "Q", "Own Goal")
    session.commit()
    g = events_for_matches(session, [m2])[m2.id]["goals"][0]
    assert g["own_goal"] is True and g["team_id"] == "away"


def test_prefers_the_source_that_is_complete_against_the_final_score(session):
    m = _match(session, 2, 0)
    session.add_all([
        Goalscorer(match_id=m.id, date=m.date, team_id="home", scorer_name="One", minute=10, own_goal=False, penalty=False, source="t"),
        Goalscorer(match_id=m.id, date=m.date, team_id="home", scorer_name="Two", minute=80, own_goal=False, penalty=False, source="t"),
    ])
    _live(session, m, 80, "goal", "home", "Two", "Normal Goal")  # poller only caught one of them
    session.commit()
    assert [g["scorer"] for g in events_for_matches(session, [m])[m.id]["goals"]] == ["One", "Two"]


def test_no_events_gives_empty_lists_not_an_error(session):
    m = _match(session, 3, 1, day=25)
    assert events_for_matches(session, [m])[m.id] == {"goals": [], "cards": []}


def test_a_live_matchs_goal_list_grows_as_polls_bring_in_new_events(session):
    """The poller REPLACES a match's events with the provider's full list each poll, so a goal
    scored between polls appears in the next read - and the served list never shows stale goals."""
    from kickcast_api.live.matching import sync_events

    m = _match(session, None, None, status="scheduled", day=24)
    goal = lambda minute, team, player: {"minute": minute, "event_type": "goal", "team_name": team, "player": player, "detail": "Normal Goal"}
    sync_events(session, m, [goal(12, "Home", "First")])
    session.commit()
    assert [g["scorer"] for g in events_for_matches(session, [m])[m.id]["goals"]] == ["First"]

    sync_events(session, m, [goal(12, "Home", "First"), goal(44, "Away", "Second")])
    session.commit()
    goals = events_for_matches(session, [m])[m.id]["goals"]
    assert [(g["minute"], g["scorer"], g["team_id"]) for g in goals] == [(12, "First", "home"), (44, "Second", "away")]
