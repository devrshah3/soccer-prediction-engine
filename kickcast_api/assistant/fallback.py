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


def answer(session: Session, question: str) -> dict:
    q = question.lower()
    teams = _mentioned_teams(session, question)

    other_year = _references_other_season(question)
    if other_year is not None:
        return {"text": _DECLINE_SPECIFIC_YEAR.format(year=other_year), "sources": [], "found": False}

    if any(w in q for w in _PREDICT_WORDS) and len(teams) == 2:
        r = tools.match_prediction_lookup(session, teams[0]["id"], teams[1]["id"])
        if r["found"]:
            p = r["prediction"]["probabilities"]
            text = (
                f"Our model gives {teams[0]['name']} {p['home']:.0%}, a draw {p['draw']:.0%}, "
                f"and {teams[1]['name']} {p['away']:.0%} (as of {r['prediction']['as_of']}, "
                f"evidence tier {r['prediction']['evidence']}). Not a promise of accuracy."
            )
            return {"text": text, "sources": [{"type": "kickcast_prediction", "data": r}], "found": True}
        return {"text": f"I don't have enough data to predict that matchup: {r['reason']}.", "sources": [], "found": False}

    if any(w in q for w in _NEXT_WORDS) and teams:
        r = tools.team_next_match(session, teams[0]["id"])
        if r["found"]:
            m = r["match"]
            text = (
                f"{m['home_team']['name']} vs {m['away_team']['name']} on {m['date']}"
                + (f" ({m['round']})" if m["round"] else "") + "."
            )
            return {"text": text, "sources": [{"type": "kickcast_match", "data": m}], "found": True}
        return {"text": f"I don't have a scheduled next match for {teams[0]['name']} in our database.", "sources": [], "found": False}

    if any(w in q for w in _RESULT_WORDS) and teams:
        r = tools.team_recent_results(session, teams[0]["id"], limit=1)
        if r["found"]:
            m = r["matches"][0]
            text = f"{m['home_team']['name']} {m['home_goals']} - {m['away_goals']} {m['away_team']['name']} ({m['date']})."
            return {"text": text, "sources": [{"type": "kickcast_match", "data": m}], "found": True}
        return {"text": f"I don't have a finished match on record for {teams[0]['name']}.", "sources": [], "found": False}

    if any(w in q for w in _TABLE_WORDS):
        if teams:
            r = tools.team_league_position(session, teams[0]["id"])
            if r["found"]:
                text = f"{teams[0]['name']} are {r['position']}{_ordinal(r['position'])} in {r['league_code']} ({r['season']}) with {r['pts']} points."
                return {"text": text, "sources": [{"type": "kickcast_standings", "data": r}], "found": True}
        return {
            "text": "I couldn't tell which league or team you mean - try naming a specific team, "
                    "or check the league standings page directly.",
            "sources": [], "found": False,
        }

    return {
        "text": "I can only answer from our own database right now (no AI assistant configured/available) - "
                "try asking about a specific team's next match, last result, league position, or a head-to-head "
                "prediction, naming the team(s) by name.",
        "sources": [], "found": False,
    }


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
