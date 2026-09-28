"""Recognised entities in a question: teams (with aliases), competitions, years, players.

Deterministic string matching against our own database - no LLM. Used to (a) resolve which
teams a question is about, (b) build a Wikipedia search from entities instead of the raw
sentence, and (c) gate a Wikipedia article on actually mentioning one of them.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Goalscorer, Team

# team id -> other ways people (and video titles) name it. The DB names are inconsistent
# ("Ath Madrid", "Paris SG", "Man United"), so these matter for both questions and titles.
TEAM_ALIASES: dict[str, tuple[str, ...]] = {
    "madrid": ("real madrid",),
    "barcelona": ("fc barcelona", "barca"),
    "atletico madrid": ("atletico madrid", "atletico", "atleti", "ath madrid"),
    "paris saint germain": ("paris saint-germain", "paris saint germain", "paris sg", "psg"),
    "manchester united": ("manchester united", "man united", "man utd"),
    "manchester city": ("manchester city", "man city"),
    "tottenham hotspur": ("tottenham hotspur", "tottenham", "spurs"),
    "internazionale milano": ("inter milan", "internazionale", "inter"),
    "bayern munchen": ("bayern munich", "bayern munchen", "bayern"),
    "borussia dortmund": ("borussia dortmund", "dortmund", "bvb"),
    "bayer leverkusen": ("bayer leverkusen", "leverkusen"),
    "milan": ("ac milan",),
    "roma": ("as roma",),
    "newcastle united": ("newcastle united", "newcastle"),
    "wolverhampton wanderers": ("wolverhampton wanderers", "wolverhampton", "wolves"),
    "west ham united": ("west ham united", "west ham"),
    "napoli": ("ssc napoli",),
}

# league code -> the names people use for that competition
COMPETITION_ALIASES: dict[str, tuple[str, ...]] = {
    "en.1": ("premier league", "english premier league", "epl"),
    "es.1": ("la liga", "laliga"),
    "it.1": ("serie a",),
    "de.1": ("bundesliga",),
    "fr.1": ("ligue 1", "ligue1"),
    "CL": ("champions league", "uefa champions league", "ucl"),
    "international": ("nations league", "world cup", "euros", "european championship", "international"),
}
COMPETITION_NAMES = {
    "en.1": "Premier League", "es.1": "La Liga", "it.1": "Serie A", "de.1": "Bundesliga",
    "fr.1": "Ligue 1", "CL": "Champions League", "international": "international football",
}

_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")


def normalize(text: str) -> str:
    """Lower-case, accent-stripped, punctuation-light form used for all matching."""
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", t)).strip()


def contains_phrase(haystack: str, phrase: str) -> bool:
    """Whole-word(s) match of a normalised phrase inside normalised text."""
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", haystack) is not None


@dataclass(frozen=True)
class TeamRef:
    id: str
    name: str


def team_variants(session: Session) -> dict[str, tuple[str, list[str]]]:
    """team id -> (display name, normalised variants). Names/ids need 4+ characters (short ones
    match too much); explicit aliases such as "psg" or "bvb" may be 3."""
    out: dict[str, tuple[str, list[str]]] = {}
    for tid, name in session.query(Team.id, Team.name).all():
        aliases = {normalize(a) for a in TEAM_ALIASES.get(tid, ())}
        names = {normalize(name), normalize(tid)}
        variants = {v for v in names if len(v) >= 4} | {v for v in aliases if len(v) >= 3}
        out[tid] = (name, sorted(variants))
    return out


def find_teams(session: Session, question: str, limit: int = 2) -> list[dict]:
    """Teams named in the question, in the order they appear. The longest matching phrase wins
    and matched spans never overlap ("Real Madrid" is one team, not "Madrid" too)."""
    text = normalize(question)
    candidates: list[tuple[int, int, str, str]] = []
    for tid, (name, variants) in team_variants(session).items():
        for v in variants:
            for m in re.finditer(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", text):
                candidates.append((m.start(), m.end(), tid, name))
    candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
    taken: list[tuple[int, int]] = []
    chosen: dict[str, tuple[int, str]] = {}
    for start, end, tid, name in candidates:
        if tid in chosen or any(start < e and s < end for s, e in taken):
            continue
        taken.append((start, end))
        chosen[tid] = (start, name)
    ordered = sorted(chosen.items(), key=lambda kv: kv[1][0])
    return [{"id": tid, "name": name} for tid, (_, name) in ordered[:limit]]


def team_title_variants(session: Session, team_id: str) -> list[str]:
    """Every normalised way a video title might name this team. Deliberately excludes the bare
    team id ("madrid"), which would also match "Atletico Madrid"."""
    team = session.get(Team, team_id)
    names = {normalize(team.name)} if team else set()
    names |= {normalize(a) for a in TEAM_ALIASES.get(team_id, ())}
    return sorted(n for n in names if n)


def find_competitions(question: str) -> list[str]:
    text = normalize(question)
    return [code for code, names in COMPETITION_ALIASES.items() if any(contains_phrase(text, normalize(n)) for n in names)]


def find_years(question: str) -> list[str]:
    return _YEAR.findall(question)


def find_players(session: Session, question: str) -> list[str]:
    """Goalscorer names (full or surname) that appear in the question."""
    text = normalize(question)
    found: list[str] = []
    for (name,) in session.query(Goalscorer.scorer_name).distinct().all():
        full = normalize(name)
        parts = full.split()
        if len(full) >= 5 and contains_phrase(text, full) or len(parts) >= 2 and len(parts[-1]) >= 5 and contains_phrase(text, parts[-1]):
            found.append(name)
    return found[:3]


def recognised_terms(session: Session, question: str) -> list[str]:
    """Display strings for every recognised entity - the ONLY material a Wikipedia search is
    built from (never the raw sentence)."""
    terms = [t["name"] for t in find_teams(session, question)]
    terms += [COMPETITION_NAMES[c] for c in find_competitions(question)]
    terms += find_players(session, question)
    terms += find_years(question)
    return list(dict.fromkeys(terms))
