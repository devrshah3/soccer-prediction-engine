"""Gemini integration: DB-first tool-calling, then Google Search grounding only for
what our tools couldn't answer. Key-gated on GEMINI_API_KEY (free tier).

VERIFIED against a real key and real calls (2026-09-23, key format "AQ." - Google's
newer auth-key format, bound to a service account; the google-genai SDK (2.25.0) takes
it identically via `genai.Client(api_key=...)`, no special handling needed):
  - `gemini-2.5-flash` (the old default here) is 404 NOT_FOUND for new users - Google's
    own error told us to migrate to `models/gemini-3.6-flash`. Switched MODEL to that;
    confirmed with a real call (real "OK" reply, real usage_metadata back).
  - response.function_calls is a list of objects with .name (str) and .args (dict),
    exactly what ask_gemini() below assumes; response.candidates[0].content round-trips
    back into `contents` correctly for a SINGLE tool call. A REAL multi-turn round trip
    (needed whenever the model wants a second tool call after seeing the first result,
    which is common) was NOT actually verified in the original pass - it silently threw
    on the second turn: `types.Content(role="tool", ...)` is rejected by the live API
    ("Role 'tool' is not supported... valid role: SYSTEM, SYSTEM_1, USER, ASSISTANT,
    DEVELOPER, CONTEXT, USER_CONTEXT, MODEL, USER"), caught by the broad except below and
    silently downgraded to the DB-only fallback with mode="db_fallback" - every question
    needing 2+ tool calls (i.e. resolve_team then anything) was silently degraded before
    this was found and fixed to role="user" (confirmed working end-to-end for real).
  - Google Search grounding (ask_gemini_with_search, below) returned a REAL
    429 RESOURCE_EXHAUSTED on the very first attempt, not a rate limit from repeated
    calls. Confirmed against Google's own pricing docs: grounding is genuinely "Not
    available" on the free tier for Gemini 3.x Flash models without a billing account
    attached (2.5 models get 1,500 free grounded requests/day, but 2.5-flash itself is
    the model that's 404ing for new users, so that path is closed too). This is not a
    bug in this code - it's a real product/billing limitation on this key. Per the
    project's no-spending-money rule, we do NOT enable billing to unlock it.
    ask_gemini_with_search already fails closed (broad except -> None -> DB/Wikipedia
    fallback) so nothing breaks, it just never succeeds on this tier. See
    kickcast_api/assistant/wikipedia.py for the free, keyless substitute this project
    uses instead for outside-DB facts (match write-ups etc.) - added specifically
    because Search grounding turned out to be unavailable.

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

from ..models import League
from . import quota
from .tools import TOOLS, TOOLS_BY_NAME


def _humanize_league_codes(session: Session, obj: Any) -> Any:
    """Item 4 regression fix: Gemini gets tool results verbatim as its function-response
    context and will happily quote a raw field back ("...in en.1 for the 2026-27
    season..."), verified live before this was added. Recursively swap any "league_code"
    key for the real "league_name" (from the leagues table) before a tool result ever
    reaches the model, so there is no internal code left for it to parrot."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "league_code" and isinstance(v, str):
                league = session.get(League, v)
                out["league_name"] = league.name if league else v
            else:
                out[k] = _humanize_league_codes(session, v)
        return out
    if isinstance(obj, list):
        return [_humanize_league_codes(session, v) for v in obj]
    return obj

SYSTEM_INSTRUCTION = (
    "You are the Soccer Prediction Engine assistant. For any factual claim about a match score, "
    "scorer, minute, table position, fixture date, or our model's prediction, you MUST "
    "call one of the provided tools and use only what it returns - never state such a "
    "fact from your own knowledge, and never state a fact a tool reported as not found. "
    "If no tool can answer the question, say plainly that you don't know rather than "
    "guessing. For match write-ups, news, or context not in our database, you may use "
    "web search, and must cite what you found. Keep answers concise and always mention "
    "dates for anything time-sensitive. Always refer to a competition by its real name "
    "(e.g. \"Premier League\"), never an internal code. Reply in plain text only - no "
    "Markdown (no **bold**, no headings, no bullet-point asterisks) - the chat UI does "
    "not render it."
)

MODEL = "gemini-3.6-flash"
MAX_TOOL_ITERATIONS = 5


def _function_declarations() -> list[types.FunctionDeclaration]:
    return [
        types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.parameters)
        for t in TOOLS
    ]


def available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def gemini_for_lookups_enabled() -> bool:
    """B3: ASSISTANT_GEMINI_FOR_LOOKUPS (default true) - lets a simple DB lookup (next
    match, last result, table position, prediction) be phrased by Gemini instead of a
    plain template (B1). Set to false to save quota when it's tight; the plain template
    is always the fallback regardless, so turning this off never breaks an answer."""
    return os.environ.get("ASSISTANT_GEMINI_FOR_LOOKUPS", "true").strip().lower() not in ("false", "0", "no")


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
                result = _humanize_league_codes(session, result)
                sources.append({"type": "kickcast_tool", "tool": call.name, "args": call.args, "result": result})
                response_parts.append(types.Part(function_response=types.FunctionResponse(name=call.name, response=result)))
            # NOT role="tool" - VERIFIED against a real call (2026-09-23): the live API
            # rejects it with "Role 'tool' is not supported. Please use a valid role:
            # SYSTEM, SYSTEM_1, USER, ASSISTANT, DEVELOPER, CONTEXT, USER_CONTEXT, MODEL,
            # USER" - this silently broke every multi-tool-call conversation (anything
            # needing more than one round of tool calls) until caught here; "user" is
            # confirmed to work end-to-end against a real multi-turn call.
            contents.append(types.Content(role="user", parts=response_parts))

        return None  # exhausted iterations without a final answer - don't guess, fall back
    except Exception:  # noqa: BLE001 - fail closed to DB fallback on any SDK/network error, deliberate
        # Any SDK/network error: fail closed to the DB-only fallback, never surface a
        # half-formed or fabricated answer.
        return None


def ask_gemini_with_context(session: Session, question: str, context: str, context_label: str) -> dict | None:
    """Answer using ONLY the given text (e.g. a Wikipedia extract, or the plain-language
    DB facts fallback.answer() gathers - see service.py's hybrid path, B1) as grounding -
    the real substitute for Search grounding on this key (see module docstring). The
    system instruction is explicit: answer only from the provided context, say so and
    stop if the context doesn't contain the answer, never fall back to unaided parametric
    knowledge presented as fact. May add ONE brief observation drawn from the context
    itself (e.g. an opponent's form, if it's in there) - never a new fact, scorer, date,
    result, or link that isn't already written in the context."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    if quota.gemini_quota_remaining(session) <= 0:
        return None

    client = genai.Client(api_key=api_key)
    prompt = (
        f"Using ONLY the {context_label} text below, answer the question in natural, "
        "concise plain text (no Markdown). Be specific (exact minutes, names, scores) "
        "where the text supports it. You may add ONE brief, genuinely useful observation "
        "if the text below already contains it (e.g. an opponent's recent form, or our "
        "model's prediction) - but never state a scorer, date, result, or link that is "
        "not written in the text below. If the text does not contain the answer, say "
        "plainly that you don't know from this source - do not use outside knowledge.\n\n"
        f"--- {context_label} ---\n{context}\n--- end ---\n\n"
        f"Question: {question}"
    )
    try:
        response = client.models.generate_content(
            model=MODEL, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION),
        )
        quota.record_gemini_call(session)
        text = getattr(response, "text", None) or ""
        if not text.strip():
            return None
        return {"text": text, "used_search": False}
    except Exception:  # noqa: BLE001 - fail closed, deliberate (see other methods in this file)
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
