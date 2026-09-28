"""Goals and cards for a match, merged from the sources we actually have - never invented.

Sources (see also replay.py's docstring for the real per-source findings):
  - `Goalscorer` (martj42 goalscorers.csv): international goals only - scorer, minute,
    penalty/own-goal flags, the CREDITED team. Lags weeks behind (last row 2026-07-19).
  - `LiveEvent` (API-Football, written by kickcast_api/live/): goals AND cards for any
    competition it polled while the match was live, plus the final list fetched once when
    the match went final. Needs API_FOOTBALL_KEY and the 100 calls/day budget.
  - football-data.org's free tier returns NO goals/bookings arrays at all (checked with real
    calls, 2026-09-28) - so nothing is read from it here.

Everything is batched by match id: list endpoints call `events_for_matches` once per
response, never once per row.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Goalscorer, LiveEvent, LiveMatchState, Match


def _goal_from_live(e: LiveEvent) -> dict | None:
    detail = (e.detail or "").lower()
    if e.event_type != "goal" or "missed" in detail:  # "Missed Penalty" is not a goal
        return None
    return {
        "team_id": e.team_id, "scorer": e.player or "Unknown", "minute": e.minute,
        "own_goal": "own" in detail, "penalty": "penalty" in detail,
    }


def _credit_own_goals(goals: list[dict], home_id: str, away_id: str, hg: int | None, ag: int | None) -> None:
    """API-Football reports an own goal under ONE of the two teams; which one (the own-goaler's
    side or the side credited) is not something we could verify against a real response - the
    free-plan quota was spent. So decide per match from the data: pick the attribution whose
    per-team goal counts equal the final score. If neither/both do, or there's no final score,
    leave the team as the source gave it."""
    own = [g for g in goals if g["own_goal"] and g["team_id"] in (home_id, away_id)]
    if not own or hg is None or ag is None:
        return

    def counts(flip: bool) -> tuple[int, int]:
        h = a = 0
        for g in goals:
            team = g["team_id"]
            if g["own_goal"] and flip and team in (home_id, away_id):
                team = away_id if team == home_id else home_id
            h += team == home_id
            a += team == away_id
        return h, a

    as_given, flipped = counts(False) == (hg, ag), counts(True) == (hg, ag)
    if flipped and not as_given:
        for g in own:
            g["team_id"] = away_id if g["team_id"] == home_id else home_id


def _cards_from_live(rows: list[LiveEvent]) -> list[dict]:
    cards: list[dict] = []
    for e in sorted(rows, key=lambda r: r.minute):
        if e.event_type != "card":
            continue
        detail = (e.detail or "").lower()
        if "red" in detail or "second yellow" in detail:
            # A second yellow shows as ONE red at that minute: drop the same player's earlier yellow.
            if "second yellow" in detail:
                for i in range(len(cards) - 1, -1, -1):
                    if cards[i]["player"] == e.player and cards[i]["card"] == "yellow":
                        del cards[i]
                        break
            kind = "red"
        elif "yellow" in detail:
            kind = "yellow"
        else:
            continue
        cards.append({"team_id": e.team_id, "player": e.player or "Unknown", "minute": e.minute, "card": kind})
    return cards


def events_for_matches(session: Session, matches: list[Match]) -> dict[int, dict]:
    """{match_id: {"goals": [...], "cards": [...]}} - only for matches that have started or
    finished (a future fixture has no events by definition); empty lists when we have none."""
    ids = [m.id for m in matches if m.status != "not_played"]
    if not ids:
        return {}
    scorer_rows: dict[int, list[Goalscorer]] = {}
    for r in session.query(Goalscorer).filter(Goalscorer.match_id.in_(ids)).order_by(Goalscorer.minute.asc()):
        scorer_rows.setdefault(r.match_id, []).append(r)
    live_rows: dict[int, list[LiveEvent]] = {}
    for r in session.query(LiveEvent).filter(LiveEvent.match_id.in_(ids)):
        live_rows.setdefault(r.match_id, []).append(r)

    out: dict[int, dict] = {}
    for m in matches:
        if m.id not in ids:
            continue
        live = live_rows.get(m.id, [])
        from_live = [g for e in sorted(live, key=lambda r: r.minute) if (g := _goal_from_live(e))]
        _credit_own_goals(from_live, m.home_team_id, m.away_team_id, m.home_goals, m.away_goals)
        from_csv = [
            {"team_id": e.team_id, "scorer": e.scorer_name, "minute": e.minute, "own_goal": e.own_goal, "penalty": e.penalty}
            for e in scorer_rows.get(m.id, [])
        ]
        total = (m.home_goals + m.away_goals) if m.home_goals is not None and m.away_goals is not None else None
        # Prefer the source whose list is complete against the final score; otherwise the longer one.
        if total is not None and len(from_csv) == total and len(from_live) != total:
            goals = from_csv
        elif len(from_live) >= len(from_csv):
            goals = from_live
        else:
            goals = from_csv
        out[m.id] = {"goals": goals, "cards": _cards_from_live(live)}
    return out


def live_updated_at(session: Session, match_id: int) -> str | None:
    state = session.get(LiveMatchState, match_id)
    return state.last_updated_at if state else None
