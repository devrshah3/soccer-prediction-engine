"""Real Gemini API calls (skipped automatically if GEMINI_API_KEY isn't set) - the
mocked tests in test_assistant.py exercise service.py's orchestration logic, but can't
catch a real SDK/API-shape bug like the one this file guards against: role="tool" being
silently rejected by the live API on the SECOND turn of a tool-calling conversation
(see gemini_client.py's module docstring - every question needing 2+ tool calls was
being silently downgraded to the DB-only fallback before this was caught and fixed).
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.assistant import gemini_client
from kickcast_api.models import Base, Match, Team

pytestmark = pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="needs a real GEMINI_API_KEY")


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gemini_live.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Team(id="team-a", name="Rovers United", country="Testland"))
    s.add(Team(id="team-b", name="Athletic Town", country="Testland"))
    from datetime import date

    s.add(
        Match(
            league_code="test.1", season="2024-25", date=date(2026, 10, 1), kickoff=None,
            home_team_id="team-a", away_team_id="team-b", home_goals=None, away_goals=None,
            status="scheduled", round="Matchday 1", neutral=False,
            source="synthetic", source_id="synthetic:1",
        )
    )
    s.commit()
    return s


def test_real_multi_turn_tool_call_completes_without_role_error(session):
    """Forces exactly the 2-call sequence that broke before the role="tool" fix:
    resolve_team (name -> id) then team_next_match (id -> fixture) - a real question a
    user would ask, requiring the model to chain two tool calls in one conversation."""
    result = gemini_client.ask_gemini(session, "When does Rovers United play next?")
    assert result is not None, (
        "ask_gemini returned None - if this regresses, check for a role= error in the "
        "SDK exception (currently swallowed by ask_gemini's broad except - temporarily "
        "remove it to see the real traceback, as the role='tool' bug required)"
    )
    tool_names = [s["tool"] for s in result["sources"] if s.get("type") == "kickcast_tool"]
    assert "resolve_team" in tool_names
    assert "team_next_match" in tool_names
    assert "2026-10-01" in result["text"] or "Athletic Town" in result["text"]
