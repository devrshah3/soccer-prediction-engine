"""Gemini integration: DB-first tool-calling, then Google Search grounding only for
what our tools couldn't answer. Key-gated on GEMINI_API_KEY (free tier).

IMPORTANT CAVEAT (see MORNING_REPORT.md): this has been written against the installed
google-genai SDK's real type signatures (verified by introspecting the installed
package, not guessed), but has NEVER been run against a live API key, because none was
provided. The tool-execution LOOP (service.py's orchestration, which never lets Gemini
state a fact without a tool result backing it) is unit-tested with a mocked Gemini
client. The actual wire-level correctness of these specific google-genai calls is
UNVERIFIED - test this for real the first time a real GEMINI_API_KEY is added.

System instruction is deliberately strict: never state a score/scorer/table
position/prediction that didn't come from a tool call; say so and stop rather than
guess when a tool reports `"found": false`.
"""

from __future__ import annotations

import os
from typing import Any, cast

from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from . import quota
from .tools import TOOLS, TOOLS_BY_NAME

SYSTEM_INSTRUCTION = (
    "You are the KickCast soccer assistant. For any factual claim about a match score, "
    "scorer, minute, table position, fixture date, or our model's prediction, you MUST "
    "call one of the provided tools and use only what it returns - never state such a "
    "fact from your own knowledge, and never state a fact a tool reported as not found. "
    "If no tool can answer the question, say plainly that you don't know rather than "
    "guessing. For match write-ups, news, or context not in our database, you may use "
    "web search, and must cite what you found. Keep answers concise and always mention "
    "dates for anything time-sensitive."
)

MODEL = "gemini-2.5-flash"
MAX_TOOL_ITERATIONS = 5


def _function_declarations() -> list[types.FunctionDeclaration]:
    return [
        types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.parameters)
        for t in TOOLS
    ]


def available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def ask_gemini(session: Session, question: str) -> dict | None:
    """Returns {"text", "sources", "used_search"} or None if unavailable/quota-exhausted/
    errored (callers must fall back to the DB-only path in that case, never silently
    return an empty/fabricated answer)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    if quota.gemini_quota_remaining(session) <= 0:
        return None

    client = genai.Client(api_key=api_key)
    tool = types.Tool(function_declarations=_function_declarations())
    contents: list[types.Content] = [types.Content(role="user", parts=[types.Part(text=question)])]
    sources: list[dict] = []

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            response = client.models.generate_content(
                model=MODEL, contents=cast(Any, contents),
                config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION, tools=[tool]),
            )
            quota.record_gemini_call(session)
            calls = getattr(response, "function_calls", None) or []
            if not calls:
                text = getattr(response, "text", None) or ""
                if not text.strip():
                    return None
                return {"text": text, "sources": sources, "used_search": False}

            if not response.candidates:
                return None
            candidate_content = response.candidates[0].content
            if candidate_content is None:
                return None
            contents.append(candidate_content)
            response_parts = []
            for call in calls:
                tool_obj = TOOLS_BY_NAME.get(call.name)
                result = tool_obj.run(session, **(call.args or {})) if tool_obj else {"found": False, "error": "unknown tool"}
                sources.append({"type": "kickcast_tool", "tool": call.name, "args": call.args, "result": result})
                response_parts.append(types.Part(function_response=types.FunctionResponse(name=call.name, response=result)))
            contents.append(types.Content(role="tool", parts=response_parts))

        return None  # exhausted iterations without a final answer - don't guess, fall back
    except Exception:  # noqa: BLE001 - fail closed to DB fallback on any SDK/network error, deliberate
        # Any SDK/network error: fail closed to the DB-only fallback, never surface a
        # half-formed or fabricated answer.
        return None


def ask_gemini_with_search(session: Session, question: str) -> dict | None:
    """Separate call using ONLY Google Search grounding (no function-calling tool mixed
    in - some Gemini API versions reject combining built-in tools like google_search
    with custom function declarations in one request), for questions our own DB tools
    couldn't answer. Used only when ask_gemini's tool calls came back empty/not-found."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    if quota.gemini_quota_remaining(session) <= 0:
        return None

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=MODEL, contents=question,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION, tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        quota.record_gemini_call(session)
        text = getattr(response, "text", None) or ""
        if not text.strip():
            return None
        grounding_sources = []
        if response.candidates:
            metadata = response.candidates[0].grounding_metadata
            for chunk in (metadata.grounding_chunks if metadata and metadata.grounding_chunks else []):
                if chunk.web:
                    grounding_sources.append({"title": chunk.web.title, "url": chunk.web.uri})
        return {"text": text, "sources": grounding_sources, "used_search": True}
    except Exception:  # noqa: BLE001 - fail closed to DB fallback on any SDK/network error, deliberate
        return None
