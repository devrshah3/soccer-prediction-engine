"""SQLAlchemy ORM schema for the KickCast site database.

Every match row carries `source`/`source_id` provenance (ground rule: never lose track of
where a fact came from). Natural-key uniqueness (league_code, date, home_team_id,
away_team_id) makes ingestion idempotent: re-running scripts/ingest.py updates rows in
place instead of duplicating them.
"""

from __future__ import annotations

from datetime import date as Date

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Date as SADate
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class League(Base):
    __tablename__ = "leagues"

    code: Mapped[str] = mapped_column(String, primary_key=True)  # "en.1", "international", ...
    name: Mapped[str] = mapped_column(String)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String)  # "domestic_league" | "international" | "continental_cup"


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # canonical id, see team_aliases.py
    name: Mapped[str] = mapped_column(String)
    country: Mapped[str | None] = mapped_column(String, nullable=True)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("league_code", "date", "home_team_id", "away_team_id", name="uq_match_natural_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_code: Mapped[str] = mapped_column(ForeignKey("leagues.code"), index=True)
    season: Mapped[str] = mapped_column(String, index=True)
    date: Mapped[Date] = mapped_column(SADate, index=True)
    kickoff: Mapped[str | None] = mapped_column(String, nullable=True)
    home_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    home_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_goals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String)  # "scheduled" | "finished"
    round: Mapped[str | None] = mapped_column(String, nullable=True)  # "Matchday 3" or tournament name
    neutral: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String)
    source_id: Mapped[str] = mapped_column(String)


class MatchStats(Base):
    """Optional per-match extras from football-data.co.uk. Nullable: not every match has them."""

    __tablename__ = "match_stats"

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    home_shots: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_shots: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_shots_on_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_shots_on_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_corners: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_corners: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_fouls: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_fouls: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_yellow: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_yellow: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_red: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_red: Mapped[float | None] = mapped_column(Float, nullable=True)
    closing_odds_home: Mapped[float | None] = mapped_column(Float, nullable=True)
    closing_odds_draw: Mapped[float | None] = mapped_column(Float, nullable=True)
    closing_odds_away: Mapped[float | None] = mapped_column(Float, nullable=True)
    odds_source: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String)


class Goalscorer(Base):
    __tablename__ = "goalscorers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True, index=True)
    date: Mapped[Date] = mapped_column(SADate)
    team_id: Mapped[str] = mapped_column(String, index=True)
    scorer_name: Mapped[str] = mapped_column(String, index=True)
    minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    own_goal: Mapped[bool] = mapped_column(Boolean, default=False)
    penalty: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String)


class Meta(Base):
    """Small key/value table; `data_version` lets the API know when to refit cached models."""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class AssistantCache(Base):
    """Cached assistant answers, keyed by a hash of the normalized question, so repeat
    questions don't cost Gemini/YouTube quota twice."""

    __tablename__ = "assistant_cache"

    question_hash: Mapped[str] = mapped_column(String, primary_key=True)
    question: Mapped[str] = mapped_column(String)
    answer_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


class YoutubeSearchCache(Base):
    """Cached YouTube search results, keyed by a hash of (query, channel restriction), so
    a repeated highlight-link lookup never costs quota twice. search.list costs 100 of
    the free tier's 10,000 units/day (~90 searches/day once real key usage is verified -
    see kickcast_api/assistant/youtube.py), so caching here matters a lot more than it
    would for a cheap endpoint. `result_json` is "null" (not absent) when a search
    genuinely found nothing, so we don't re-search a query we already know fails."""

    __tablename__ = "youtube_search_cache"

    query_hash: Mapped[str] = mapped_column(String, primary_key=True)
    query: Mapped[str] = mapped_column(String)
    channel: Mapped[str | None] = mapped_column(String, nullable=True)
    result_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


class WikipediaCache(Base):
    """Cached Wikipedia lookups (search + extract), keyed by a hash of the normalized
    query, so a repeated question never re-hits the MediaWiki API. Free/keyless, but
    Wikimedia's User-Agent policy asks courteous clients not to hammer it needlessly -
    see kickcast_api/assistant/wikipedia.py. `extract` is empty string (not absent) when
    a search genuinely found nothing, so we don't re-search a known-empty query."""

    __tablename__ = "wikipedia_cache"

    query_hash: Mapped[str] = mapped_column(String, primary_key=True)
    query: Mapped[str] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    extract: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


class LiveMatchState(Base):
    """Polled (never on-page-load) from API-Football, key-gated - see
    kickcast_api/live/api_football.py. `last_updated_at` is what lets the frontend show
    "based on score at X', updated Y min ago" rather than pretending to be truly live."""

    __tablename__ = "live_match_state"

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), primary_key=True)
    minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_status: Mapped[str] = mapped_column(String)  # e.g. "1H"/"HT"/"2H"/"FT" (API-Football's codes)
    last_updated_at: Mapped[str] = mapped_column(String)  # ISO8601 UTC
    source: Mapped[str] = mapped_column(String)


class LiveEvent(Base):
    __tablename__ = "live_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    minute: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String)  # "goal" | "card" | "substitution" | ...
    team_id: Mapped[str | None] = mapped_column(String, nullable=True)
    player: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String)


class ExternalApiQuota(Base):
    """Same day-row pattern as AssistantQuota, for API-Football's separate 100-call/day
    free tier - kept as its own table since it's a different budget entirely."""

    __tablename__ = "external_api_quota"

    day: Mapped[str] = mapped_column(String, primary_key=True)
    api_football_calls: Mapped[int] = mapped_column(Integer, default=0)


class AssistantQuota(Base):
    """One row per UTC calendar day: how many Gemini calls the assistant has made, so we
    can stop before hitting the free-tier daily limit and fall back to the DB-only path."""

    __tablename__ = "assistant_quota"

    day: Mapped[str] = mapped_column(String, primary_key=True)  # "YYYY-MM-DD"
    gemini_calls: Mapped[int] = mapped_column(Integer, default=0)
    youtube_calls: Mapped[int] = mapped_column(Integer, default=0)
