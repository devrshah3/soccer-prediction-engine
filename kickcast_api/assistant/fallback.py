"""DB-only fallback: answers a narrow set of question shapes without any LLM, by
keyword-matching intent and substring-matching team names already in our database, then
calling the exact same tools.py functions the Gemini path uses. Used when GEMINI_API_KEY
is missing or the daily quota is used up.

This is deliberately NOT natural-language understanding - it's a small set of rules. If
nothing matches, it says so rather than guessing, per the "never invent a fact" rule.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..models import Team
from . import tools

_NEXT_WORDS = ("next", "when", "upcoming", "fixture", "play next", "playing next")
_RESULT_WORDS = ("score", "result", "beat", "lost", "won", "lose", "win against", "draw")
_TABLE_WORDS = ("table", "standings", "position", "top of", "leading", "first place", "where are")
_PREDICT_WORDS = ("predict", "odds", "chance", "probability", "who will win", "favourite", "favorite")
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

_DECLINE_SPECIFIC_YEAR = (
    "I can only answer from our own database right now (no AI assistant configured/available), "
    "and our database lookups here only cover the CURRENT/most recent match, standings and "
    "predictions - not a specific match from {year}. Ask again once the assistant's AI mode is "
    "available, or check the team's fixtures/results page for older matches we do have on file."
)


def _references_other_season(question: str) -> str | None:
    """These fallback tools only ever answer 'next'/'most recent'/'current' - never a specific
    past match - so a question naming a year outside the current season is out of scope for all
    of them. Returns that year if so, else None. (Current season years pass through normally.)"""
    now = datetime.now(UTC)
    current_season_years = {now.year, now.year + 1, now.year - 1}
    for m in _YEAR_RE.finditer(question):
        year = int(m.group(1))
        if year not in current_season_years:
            return m.group(1)
    return None


def _mentioned_teams(session: Session, question: str) -> list[dict]:
    q = question.lower()
    names = session.query(Team.id, Team.name).all()
    hits = [(tid, name) for tid, name in names if len(name) >= 4 and name.lower() in q]
    hits.sort(key=lambda h: -len(h[1]))  # longest/most-specific name match first
    seen: set[str] = set()
    out = []
    for tid, name in hits:
        if tid in seen:
            continue
        seen.add(tid)
        out.append({"id": tid, "name": name})
        if len(out) >= 2:
            break
    return out


def is_simple_lookup(session: Session, question: str) -> bool:
    """True if this question is one of our narrow, keyword-matched DB-lookup shapes (next
    match, last result, table position, head-to-head prediction) naming the right number
    of teams we recognize - regardless of whether the specific lookup then succeeds (a
    "we don't have that on record" answer is still a DB-only answer, not a reason to spend
    a Gemini call). Used to route these straight to `answer()` below with no LLM call at
    all: an LLM adds nothing here since it would just call the exact same tools.py
    functions to produce the exact same fact.

    False for a question naming an out-of-scope year even if it otherwise contains a
    result/table/etc. keyword - e.g. "what was the score of the 2016 Champions League
    final" contains "score", but needs a real write-up (Wikipedia/Gemini), not our "most
    recent finished match" lookup, which can never answer a specific past match by year.
    """
    if _references_other_season(question) is not None:
        return False
    q = question.lower()
    has_predict = any(w in q for w in _PREDICT_WORDS)
    has_next = any(w in q for w in _NEXT_WORDS)
    has_result = any(w in q for w in _RESULT_WORDS)
    has_table = any(w in q for w in _TABLE_WORDS)
    if not (has_predict or has_next or has_result or has_table):
        return False  # no recognized keyword at all - skip the DB query, not our shape
    teams = _mentioned_teams(session, question)
    if has_predict and len(teams) == 2:
        return True
    if has_next and teams:
        return True
    if has_result and teams:
        return True
    return has_table


def _next_match_facts(session: Session, session_team: dict, m: dict) -> str:
    """The base "next match" fact, plus a couple of cheap, genuinely useful extras
    (opponent's recent form, our model's prediction) using the SAME tool calls the
    Gemini function-calling path would use - gathered once here instead, so a hybrid
    Gemini-phrased answer (B1) has real material for "a short useful extra" without
    Gemini ever being allowed to invent one itself."""
    lines = [
        f"{session_team['name']}'s next match: {m['home_team']['name']} vs {m['away_team']['name']} "
        f"on {m['date']}" + (f" ({m['round']})" if m["round"] else "") + "."
    ]
    opponent = m["away_team"] if m["home_team"]["id"] == session_team["id"] else m["home_team"]
    pos = tools.team_league_position(session, opponent["id"])
    if pos["found"] and pos.get("form"):
        lines.append(f"{opponent['name']}'s recent form (last 5, oldest first): {' '.join(pos['form'])}.")
    pred = tools.match_prediction_lookup(session, m["home_team"]["id"], m["away_team"]["id"])
    if pred["found"]:
        p = pred["prediction"]["probabilities"]
        lines.append(
            f"Our model's prediction for this match: {m['home_team']['name']} {p['home']:.0%} to win, "
            f"draw {p['draw']:.0%}, {m['away_team']['name']} {p['away']:.0%} to win "
            f"(evidence tier {pred['prediction']['evidence']})."
        )
    return " ".join(lines)


def answer(session: Session, question: str) -> dict:
    """Returns {"text", "sources", "found", "facts"}. "facts" is a plain-language,
    complete write-up of everything actually retrieved (never more than that) - safe to
    hand an LLM as strict grounding (see gemini_client.compose_from_facts): it must
    never state anything beyond what's written here."""
    q = question.lower()
    teams = _mentioned_teams(session, question)

    other_year = _references_other_season(question)
    if other_year is not None:
        return {"text": _DECLINE_SPECIFIC_YEAR.format(year=other_year), "sources": [], "found": False, "facts": None}

    if any(w in q for w in _PREDICT_WORDS) and len(teams) == 2:
        r = tools.match_prediction_lookup(session, teams[0]["id"], teams[1]["id"])
        if r["found"]:
            p = r["prediction"]["probabilities"]
            text = (
                f"Our model gives {teams[0]['name']} {p['home']:.0%}, a draw {p['draw']:.0%}, "
                f"and {teams[1]['name']} {p['away']:.0%} (as of {r['prediction']['as_of']}, "
                f"evidence tier {r['prediction']['evidence']}). Not a promise of accuracy."
            )
            facts = (
                f"Matchup: {teams[0]['name']} vs {teams[1]['name']}. Our model's prediction: "
                f"{teams[0]['name']} {p['home']:.0%}, draw {p['draw']:.0%}, {teams[1]['name']} {p['away']:.0%} "
                f"(evidence tier {r['prediction']['evidence']}, as of {r['prediction']['as_of']})."
            )
            return {"text": text, "sources": [{"type": "kickcast_prediction", "data": r}], "found": True, "facts": facts}
        text = f"I don't have enough data to predict that matchup: {r['reason']}."
        return {"text": text, "sources": [], "found": False, "facts": text}

    if any(w in q for w in _NEXT_WORDS) and teams:
        r = tools.team_next_match(session, teams[0]["id"])
        if r["found"]:
            m = r["match"]
            text = (
                f"{m['home_team']['name']} vs {m['away_team']['name']} on {m['date']}"
                + (f" ({m['round']})" if m["round"] else "") + "."
            )
            facts = _next_match_facts(session, teams[0], m)
            return {"text": text, "sources": [{"type": "kickcast_match", "data": m}], "found": True, "facts": facts}
        text = f"I don't have a scheduled next match for {teams[0]['name']} in our database."
        return {"text": text, "sources": [], "found": False, "facts": text}

    if any(w in q for w in _RESULT_WORDS) and teams:
        r = tools.team_recent_results(session, teams[0]["id"], limit=1)
        if r["found"]:
            m = r["matches"][0]
            text = f"{m['home_team']['name']} {m['home_goals']} - {m['away_goals']} {m['away_team']['name']} ({m['date']})."
            facts = f"{teams[0]['name']}'s most recent finished match: {text}"
            return {"text": text, "sources": [{"type": "kickcast_match", "data": m}], "found": True, "facts": facts}
        text = f"I don't have a finished match on record for {teams[0]['name']}."
        return {"text": text, "sources": [], "found": False, "facts": text}

    if any(w in q for w in _TABLE_WORDS):
        if teams:
            r = tools.team_league_position(session, teams[0]["id"])
            if r["found"]:
                text = f"{teams[0]['name']} are {r['position']}{_ordinal(r['position'])} in {r['league_code']} ({r['season']}) with {r['pts']} points."
                facts = (
                    f"{teams[0]['name']} standing: position {r['position']} in {r['league_code']} ({r['season']}), "
                    f"{r['pts']} points, played {r['played']}"
                    + (f", recent form (last 5, oldest first): {' '.join(r['form'])}" if r.get("form") else "")
                    + "."
                )
                return {"text": text, "sources": [{"type": "kickcast_standings", "data": r}], "found": True, "facts": facts}
        text = (
            "I couldn't tell which league or team you mean - try naming a specific team, "
            "or check the league standings page directly."
        )
        return {"text": text, "sources": [], "found": False, "facts": None}

    text = (
        "I can only answer from our own database right now (no AI assistant configured/available) - "
        "try asking about a specific team's next match, last result, league position, or a head-to-head "
        "prediction, naming the team(s) by name."
    )
    return {"text": text, "sources": [], "found": False, "facts": None}


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
