"""DB-only fallback: answers a narrow set of question shapes without any LLM, by
keyword-matching intent and substring-matching team names already in our database, then
calling the exact same tools.py functions the Gemini path uses. Used when GEMINI_API_KEY
is missing or the daily quota is used up.

This is deliberately NOT natural-language understanding - it's a small set of rules. If
nothing matches, it says so rather than guessing, per the "never invent a fact" rule.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from . import tools
from .entities import COMPETITION_NAMES, find_competitions, find_teams
from .intent import Intent, classify, references_other_season


def prediction_sentence(session: Session, r: dict, asked: list[dict]) -> str:
    """One sentence for a head-to-head prediction. Home/away order, names and date come from
    the fixture record in `r["match"]` - never from the order the teams appear in the
    question (asked = the two teams as the user named them, only used when NO fixture exists,
    where the model was run with asked[0] as the home side)."""
    p = r["prediction"]["probabilities"]
    tail = f"(as of {r['prediction']['as_of']}, evidence tier {r['prediction']['evidence']}). Not a promise of accuracy."
    m = r.get("match")
    if m is None:
        a, b = asked[0]["name"], asked[1]["name"]
        return (
            f"There is no scheduled fixture between {a} and {b} in our data, so this is a hypothetical with "
            f"{a} as the home side: our model gives {a} {p['home']:.0%}, a draw {p['draw']:.0%}, and {b} {p['away']:.0%} {tail}"
        )
    home, away = m["home_team"]["name"], m["away_team"]["name"]
    when = date.fromisoformat(m["date"]).strftime("%a %b %d, %Y").replace(" 0", " ")
    venue = "neutral venue" if m.get("neutral") else "home"
    n = r.get("fixtures_upcoming", 1)
    which = f", the next of {n} scheduled fixtures between them" if n > 1 else ""
    return (
        f"{home} ({venue}) vs {away} on {when}{which}: our model gives {home} {p['home']:.0%}, "
        f"a draw {p['draw']:.0%}, and {away} {p['away']:.0%} {tail}"
    )

_NEXT_WORDS = ("next", "when", "upcoming", "fixture", "play next", "playing next")
_RESULT_WORDS = ("score", "result", "beat", "lost", "won", "lose", "win against", "draw")
_TABLE_WORDS = ("table", "standings", "position", "top of", "leading", "first place", "where are")
_PREDICT_WORDS = ("predict", "odds", "chance", "probability", "who will win", "favourite", "favorite")

_DECLINE_SPECIFIC_YEAR = (
    "I can only answer from our own database right now (no AI assistant configured/available), "
    "and our database lookups here only cover the CURRENT/most recent match, standings and "
    "predictions - not a specific match from {year}. Ask again once the assistant's AI mode is "
    "available, or check the team's fixtures/results page for older matches we do have on file."
)

ASK_WHICH_MATCH = (
    "Which match do you mean? Name the teams, for example \"Barcelona vs Real Madrid\"."
)


def _references_other_season(question: str) -> str | None:
    return references_other_season(question)


def _mentioned_teams(session: Session, question: str) -> list[dict]:
    return find_teams(session, question)


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


def _nf(text: str) -> dict:
    return {"text": text, "sources": [], "found": False, "facts": text}


def _scorers_sentence(session: Session, m: dict) -> str:
    events = tools.match_goal_events(session, m["id"])
    if not events:
        return "Goal scorers aren't on record for this match."
    parts = []
    for e in events:
        tag = " (o.g.)" if e["own_goal"] else " (pen.)" if e["penalty"] else ""
        parts.append(f"{e['scorer']} {e['minute']}'{tag}" if e["minute"] is not None else f"{e['scorer']}{tag}")
    return "Scorers: " + ", ".join(parts) + "."


def answer(session: Session, question: str, intent: Intent | None = None, teams: list[dict] | None = None) -> dict:
    """Returns {"text", "sources", "found", "facts"}. "facts" is a plain-language,
    complete write-up of everything actually retrieved (never more than that) - safe to
    hand an LLM as strict grounding: it must never state anything beyond what's written here.
    Dispatches on the deterministic intent (intent.classify), never on overlapping keyword lists."""
    intent = intent or classify(question)
    teams = teams if teams is not None else find_teams(session, question)

    other_year = _references_other_season(question)
    if other_year is not None:
        return {"text": _DECLINE_SPECIFIC_YEAR.format(year=other_year), "sources": [], "found": False, "facts": None}

    if intent is Intent.PREDICTION:
        if len(teams) < 2:
            return _nf("Which two teams? Ask like \"Predict Barcelona vs Real Madrid\".")
        r = tools.match_prediction_lookup(session, teams[0]["id"], teams[1]["id"])
        if not r["found"]:
            return _nf(f"I don't have enough data to predict that matchup: {r['reason']}.")
        text = prediction_sentence(session, r, teams)
        return {"text": text, "sources": [{"type": "kickcast_prediction", "data": r}], "found": True, "facts": text}

    if intent is Intent.MATCH_LOOKUP:
        if not teams:
            return _nf(ASK_WHICH_MATCH)
        r = tools.team_next_match(session, teams[0]["id"])
        if not r["found"]:
            return _nf(f"I don't have a scheduled next match for {teams[0]['name']} in our database.")
        m = r["match"]
        text = (
            f"{m['home_team']['name']} vs {m['away_team']['name']} on {m['date']}"
            + (f" ({m['round']})" if m["round"] else "") + "."
        )
        facts = _next_match_facts(session, teams[0], m)
        return {"text": text, "sources": [{"type": "kickcast_match", "data": m}], "found": True, "facts": facts}

    if intent is Intent.RESULT:
        if not teams:
            return _nf(ASK_WHICH_MATCH)
        r = tools.team_recent_results(session, teams[0]["id"], limit=1)
        if not r["found"]:
            return _nf(f"I don't have a finished match on record for {teams[0]['name']}.")
        m = r["matches"][0]
        text = f"{m['home_team']['name']} {m['home_goals']} - {m['away_goals']} {m['away_team']['name']} ({m['date']})."
        if "scor" in question.lower():
            text += " " + _scorers_sentence(session, m)
        facts = f"{teams[0]['name']}'s most recent finished match: {text}"
        return {"text": text, "sources": [{"type": "kickcast_match", "data": m}], "found": True, "facts": facts}

    if intent is Intent.TABLE:
        if teams:
            r = tools.team_league_position(session, teams[0]["id"])
            if r["found"]:
                text = f"{teams[0]['name']} are {r['position']}{_ordinal(r['position'])} in {r['league_name']} ({r['season']}) with {r['pts']} points."
                facts = (
                    f"{teams[0]['name']} standing: position {r['position']} in {r['league_name']} ({r['season']}), "
                    f"{r['pts']} points, played {r['played']}"
                    + (f", recent form (last 5, oldest first): {' '.join(r['form'])}" if r.get("form") else "")
                    + "."
                )
                return {"text": text, "sources": [{"type": "kickcast_standings", "data": r}], "found": True, "facts": facts}
        comps = [c for c in find_competitions(question) if c not in ("CL", "international")]
        if comps:
            r = tools.league_standings_top(session, comps[0], n=5)
            if r["found"]:
                rows = ", ".join(f"{t['position']}. {t['team_name']} {t['pts']}" for t in r["table"])
                text = f"{COMPETITION_NAMES[comps[0]]} {r['season']} top of the table: {rows}."
                return {"text": text, "sources": [], "found": True, "facts": text}
        return _nf("Which team or league table do you mean? Name a team, or a league such as \"Premier League\".")

    if intent is Intent.TOP_SCORERS:
        comps = find_competitions(question)
        if not comps:
            return _nf("Which competition's top scorers? For example \"Premier League top scorers\".")
        r = tools.league_top_scorers_lookup(comps[0])
        if not r["found"]:
            return _nf(f"I don't have current top-scorer data for the {COMPETITION_NAMES[comps[0]]} right now.")
        rows = ", ".join(f"{x['player']} ({x['team_name']}) {x['goals']}" for x in r["scorers"])
        text = f"{COMPETITION_NAMES[comps[0]]} top scorers {r['season']}: {rows}."
        return {"text": text, "sources": [], "found": True, "facts": text}

    return unknown_reply()


EXAMPLE_QUESTIONS = (
    "Predict Barcelona vs Real Madrid",
    "When does Arsenal play next?",
    "Where do Man City stand in the table?",
)


def unknown_reply() -> dict:
    text = (
        "I don't recognize that one. Try: "
        + "; ".join(f"\"{q}\"" for q in EXAMPLE_QUESTIONS)
        + "."
    )
    return {"text": text, "sources": [], "found": False, "facts": None}


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
