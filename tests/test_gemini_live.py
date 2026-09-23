"""Real Gemini API calls (skipped automatically if GEMINI_API_KEY isn't set) - the
mocked tests in test_assistant.py exercise service.py's orchestration logic, but can't
catch a real SDK/API-shape bug like the one this file guards against: role="tool" being
silently rejected by the live API on the SECOND turn of a tool-calling conversation
(see gemini_client.py's module docstring - every question needing 2+ tool calls was
being silently downgraded to the DB-only fallback before this was caught and fixed).

Calls the SDK directly (not through ask_gemini, which fails closed on ANY exception -
the right behavior for the app, but useless for a test that needs to tell "the real
free-tier daily cap was hit" (skip - not a regression) apart from "the SDK/API rejected
our request shape" (fail - IS a regression, this is exactly how the role bug was found).
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any, cast

import pytest
from google import genai
from google.genai import errors, types
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kickcast_api.assistant import gemini_client
from kickcast_api.assistant.tools import TOOLS_BY_NAME
from kickcast_api.models import Base, Match, Team

pytestmark = pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="needs a real GEMINI_API_KEY")


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gemini_live.db'}")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Team(id="team-a", name="Rovers United", country="Testland"))
    s.add(Team(id="team-b", name="Athletic Town", country="Testland"))
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
    user would ask, requiring the model to chain two tool calls in one conversation.
    Skips (not fails) on a real daily-quota 429 - that's an external constraint (see
    quota.py's DEFAULT_GEMINI_DAILY_QUOTA docstring), not a code regression. Any other
    exception (e.g. a 400 over an invalid role/shape) fails the test for real."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    tool = types.Tool(function_declarations=gemini_client._function_declarations())
    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text="When does Rovers United play next?")])
    ]
    tool_names: list[str] = []
    final_text = ""

    for _ in range(4):
        try:
            response = client.models.generate_content(
                model=gemini_client.MODEL, contents=cast(Any, contents),
                config=types.GenerateContentConfig(system_instruction=gemini_client.SYSTEM_INSTRUCTION, tools=[tool]),
            )
        except errors.ClientError as e:
            if e.code == 429:
                pytest.skip(f"real free-tier daily quota exhausted (not a code regression): {e}")
            raise  # any other error (e.g. a 400 over role/shape) is a real regression - let it fail the test

        calls = getattr(response, "function_calls", None) or []
        if not calls:
            final_text = getattr(response, "text", None) or ""
            break
        assert response.candidates and response.candidates[0].content is not None
        contents.append(response.candidates[0].content)
        response_parts = []
        for call in calls:
            tool_names.append(call.name)
            tool_obj = TOOLS_BY_NAME.get(call.name)
            result = tool_obj.run(session, **(call.args or {})) if tool_obj else {"found": False}
            response_parts.append(types.Part(function_response=types.FunctionResponse(name=call.name, response=result)))
        contents.append(types.Content(role="user", parts=response_parts))  # NOT role="tool" - see module docstring

    assert "resolve_team" in tool_names
    assert "team_next_match" in tool_names
    assert "2026-10-01" in final_text or "Athletic Town" in final_text
