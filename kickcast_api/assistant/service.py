"""Top-level assistant orchestration: cache -> Gemini (DB tools, then search grounding
for what the tools couldn't answer) -> DB-only fallback. This is the only entry point
routes/assistant.py should call.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import cache, fallback, gemini_client


def _all_tools_missed(sources: list[dict]) -> bool:
    tool_results = [s for s in sources if s.get("type") == "kickcast_tool"]
    if not tool_results:
        return True  # no tool was even called - question is probably outside our DB
    return all(isinstance(s.get("result"), dict) and s["result"].get("found") is False for s in tool_results)


def ask(session: Session, question: str) -> dict:
    question = question.strip()
    if not question:
        return {"text": "Ask me something about a team, fixture, table, or prediction.", "sources": [], "mode": "invalid", "cached": False}

    cached = cache.get_cached(session, question)
    if cached is not None:
        return {**cached, "cached": True}

    if gemini_client.available():
        result = gemini_client.ask_gemini(session, question)
        if result is not None:
            if _all_tools_missed(result["sources"]):
                search_result = gemini_client.ask_gemini_with_search(session, question)
                if search_result is not None:
                    result = search_result
            answer = {"text": result["text"], "sources": result["sources"], "mode": "gemini"}
            cache.set_cached(session, question, answer)  # only Gemini answers are cached - they cost quota
            return {**answer, "cached": False}

    fb = fallback.answer(session, question)
    return {"text": fb["text"], "sources": fb["sources"], "mode": "db_fallback", "cached": False}
