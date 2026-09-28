"""Replay = yesterday, nothing else (item 6): every match played on the viewer's local
"yesterday", across every competition, with the real events we actually have, a
pre-match-prediction-vs-result comparison, and a short recap written only from verified
facts.

Real event-source findings (2026-09-28, each checked with one real call/read):
  - martj42 goalscorers.csv (internationals; already ingested into `Goalscorer`): goals
    only (scorer, minute, penalty/own-goal flag), and it LAGS - the freshly re-downloaded
    file's last row was 2026-07-19 and results.csv's was 2026-08-26, nothing for the
    2026-09-26/27 Nations League days.
  - API-Football GET /fixtures?date=2026-09-27: HTTP 200 but errors.requests "You have
    reached the request limit for the day" - the free plan's daily budget was already
    spent, so current-season access could not be re-tested today (a 2026-09-23 real call
    had already shown the free plan has no access to the current season at all).
  - football-data.org GET /v4/matches/560583 (PL, Fulham 1-1 Man United, 2026-09-20):
    HTTP 200 with fullTime/halfTime score and referee, but NO goals/bookings/
    substitutions arrays - no event timeline for club matches from our free sources.
So: goals for internationals when martj42 has them, nothing else - never cards/subs,
never a timeline we can't source. Everything else is said plainly as unavailable.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from .assistant import cache, gemini_client, quota
from .models import Goalscorer, League, Match
from .precompute import get_precomputed_prediction
from .serialize import team_names

RECAP_LABEL = "Recap written from verified match data"
NO_EVENTS_NOTE = "Detailed events aren't available for this match on our free data sources."
GEMINI_RECAP_RESERVE = 8  # never spend the last calls of the day's chat budget on recaps
MAX_GEMINI_RECAPS_PER_REQUEST = 3


def local_calendar_date(match_date: date, kickoff: str | None, offset_minutes: int) -> date:
    """A match's stored date is its UTC calendar date; this is the viewer's local one
    (offset_minutes = minutes EAST of UTC). Mirrors frontend/src/lib/localDate.ts."""
    if not kickoff:
        return match_date
    try:
        hh, mm = kickoff.split(":")[:2]
        utc = datetime(match_date.year, match_date.month, match_date.day, int(hh), int(mm), tzinfo=UTC)
    except (ValueError, TypeError):
        return match_date
    return (utc + timedelta(minutes=offset_minutes)).date()


def matches_on_local_date(session: Session, local_date: date, offset_minutes: int) -> list[Match]:
    candidates = (
        session.query(Match)
        .filter(Match.date >= local_date - timedelta(days=1), Match.date <= local_date + timedelta(days=1))
        .all()
    )
    hits = [m for m in candidates if local_calendar_date(m.date, m.kickoff, offset_minutes) == local_date]
    return sorted(hits, key=lambda m: (m.date, m.kickoff or "", m.id))


def most_recent_day_with_matches(session: Session, before: date, finished_only: bool = False) -> date | None:
    statuses = ["finished"] if finished_only else ["finished", "not_played"]
    row = (
        session.query(Match.date)
        .filter(Match.date < before, Match.status.in_(statuses))
        .order_by(Match.date.desc())
        .first()
    )
    return row[0] if row else None


def _outcome(home_goals: int, away_goals: int) -> str:
    return "home" if home_goals > away_goals else "away" if away_goals > home_goals else "draw"


def _events_for(session: Session, match_ids: list[int]) -> dict[int, list[Goalscorer]]:
    if not match_ids:
        return {}
    rows = (
        session.query(Goalscorer)
        .filter(Goalscorer.match_id.in_(match_ids))
        .order_by(Goalscorer.minute.asc())
        .all()
    )
    out: dict[int, list[Goalscorer]] = {}
    for r in rows:
        if r.match_id is not None:
            out.setdefault(r.match_id, []).append(r)
    return out


def _label_outcome(outcome: str, home: str, away: str) -> str:
    return "a draw" if outcome == "draw" else f"a {home if outcome == 'home' else away} win"


def _facts(row: dict) -> str:
    """The complete, plain-language set of verified facts about one match - the ONLY
    material a recap (template or Gemini-phrased) may draw on."""
    home, away = row["home_team"]["name"], row["away_team"]["name"]
    where = f"{row['league_name']}" + (f", {row['round']}" if row["round"] else "")
    if not row["has_result"]:
        return (
            f"{home} vs {away} ({where}) was scheduled for {row['date']}"
            + (f" at {row['kickoff']} UTC" if row["kickoff"] else "")
            + ". No result has been recorded in our data sources yet."
        )
    parts = [f"{home} {row['home_goals']}-{row['away_goals']} {away} ({where}, {row['date']})."]
    if row["events_status"] == "complete" and row["events"]:
        goals = []
        for e in row["events"]:
            tag = " (own goal)" if e["own_goal"] else " (penalty)" if e["penalty"] else ""
            minute = f"{e['minute']}'" if e["minute"] is not None else "minute unknown"
            goals.append(f"{e['player']} for {e['team_name']}, {minute}{tag}")
        parts.append("Goals: " + "; ".join(goals) + ".")
    elif row["events_status"] == "complete":
        parts.append("Neither team scored.")
    elif row["events_status"] == "partial":
        parts.append(f"Only {len(row['events'])} of the {row['home_goals'] + row['away_goals']} goals have a recorded scorer.")
    else:
        parts.append("Goal scorers and minutes are not available for this match.")
    pr = row["prediction_result"]
    if pr is not None:
        parts.append(
            f"Our pre-match model favoured {_label_outcome(pr['predicted'], home, away)} "
            f"({round(pr['predicted_probability'] * 100)}%) and gave the actual outcome, "
            f"{_label_outcome(pr['actual'], home, away)}, {round(pr['actual_probability'] * 100)}%."
        )
    return " ".join(parts)


_NUMBER = re.compile(r"\d+")
_DECLINE = ("don't know", "do not know", "cannot", "can't", "no data", "not available")


def _gemini_recap_is_grounded(text: str, facts: str) -> bool:
    """Reject a Gemini rewrite that introduces any number (score, minute, percentage)
    not already written in the facts, or that reads like a decline."""
    if any(p in text.lower() for p in _DECLINE):
        return False
    return all(n in _NUMBER.findall(facts) for n in _NUMBER.findall(text))


def _recap(session: Session, row: dict, budget: list[int]) -> dict:
    facts = _facts(row)
    template = {"text": facts, "mode": "template", "label": RECAP_LABEL}
    if not row["has_result"] or budget[0] <= 0:
        return template
    if not (gemini_client.gemini_for_lookups_enabled() and gemini_client.available()):
        return template
    question = f"Write a short match recap for match {row['id']}"
    key = f"{question}\x00{facts}"
    cache_key = hashlib.sha256(key.encode()).hexdigest()
    cached = cache.get_cached(session, cache_key)
    if cached is not None:
        return cached
    if quota.gemini_quota_remaining(session) <= GEMINI_RECAP_RESERVE:
        return template
    budget[0] -= 1
    composed = gemini_client.ask_gemini_with_context(
        session, "Write a two-to-three sentence recap of this match.", facts, "verified match facts"
    )
    if composed is None:
        return template  # call failed/quota - not cached, so a later view can retry
    if not _gemini_recap_is_grounded(composed["text"], facts):
        cache.set_cached(session, cache_key, template)  # rejected rewrite: don't re-spend quota on it
        return template
    result = {"text": composed["text"].strip(), "mode": "gemini", "label": RECAP_LABEL}
    cache.set_cached(session, cache_key, result)
    return result


def day_replay(session: Session, local_date: date, offset_minutes: int) -> dict:
    matches = matches_on_local_date(session, local_date, offset_minutes)
    ids = [m.id for m in matches]
    events_by_match = _events_for(session, ids)
    team_ids = {t for m in matches for t in (m.home_team_id, m.away_team_id)}
    names = team_names(session, team_ids)
    leagues = {lg.code: lg for lg in session.query(League).all()}

    rows = []
    for m in matches:
        hg, ag = m.home_goals, m.away_goals
        has_result = m.status == "finished" and hg is not None and ag is not None
        goal_rows = events_by_match.get(m.id, [])
        events = [
            {
                "minute": e.minute,
                "player": e.scorer_name,
                "team_id": e.team_id,
                "team_name": names.get(e.team_id, e.team_id),
                "own_goal": e.own_goal,
                "penalty": e.penalty,
            }
            for e in goal_rows
        ]
        total_goals = (hg or 0) + (ag or 0)
        if not has_result:
            events_status = None
        elif len(events) == total_goals:
            events_status = "complete"
        elif events:
            events_status = "partial"
        else:
            events_status = "none"

        stored = get_precomputed_prediction(session, m.id)
        prediction = None
        prediction_result = None
        if stored is not None:
            probs = stored["probabilities"]
            prediction = {
                "probabilities": probs, "as_of": stored["as_of"], "computed_at": stored.get("computed_at"),
                "model_version": stored["model_version"], "evidence": stored.get("evidence"),
            }
            if has_result and hg is not None and ag is not None:
                predicted = max(probs, key=lambda k: probs[k])
                actual = _outcome(hg, ag)
                prediction_result = {
                    "predicted": predicted, "predicted_probability": probs[predicted],
                    "actual": actual, "actual_probability": probs[actual], "correct": predicted == actual,
                }

        league = leagues.get(m.league_code)
        rows.append({
            "id": m.id,
            "league_code": m.league_code,
            "league_name": league.name if league else m.league_code,
            "league_country": league.country if league else None,
            "round": m.round,
            "date": m.date.isoformat(),
            "kickoff": m.kickoff,
            "status": m.status,
            "home_team": {"id": m.home_team_id, "name": names.get(m.home_team_id, m.home_team_id)},
            "away_team": {"id": m.away_team_id, "name": names.get(m.away_team_id, m.away_team_id)},
            "home_goals": hg if has_result else None,
            "away_goals": ag if has_result else None,
            "has_result": has_result,
            "events": events,
            "events_status": events_status,
            "prediction": prediction,
            "prediction_result": prediction_result,
        })

    budget = [MAX_GEMINI_RECAPS_PER_REQUEST]
    for row in rows:
        row["recap"] = _recap(session, row, budget)

    any_result = any(r["has_result"] for r in rows)
    recent_any = None if rows else most_recent_day_with_matches(session, local_date)
    recent_results = None if any_result else most_recent_day_with_matches(session, local_date, finished_only=True)
    return {
        "date": local_date.isoformat(),
        "matches": rows,
        "no_events_note": NO_EVENTS_NOTE,
        "most_recent_day_with_matches": recent_any.isoformat() if recent_any else None,
        "most_recent_day_with_results": recent_results.isoformat() if recent_results else None,
    }
