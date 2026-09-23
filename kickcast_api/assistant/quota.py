"""Daily call-count tracking so the assistant stops calling Gemini/YouTube before
hitting the free-tier limit and falls back to the DB-only path instead of erroring."""

from __future__ import annotations

import os
from datetime import datetime as _dt
from datetime import timezone

from sqlalchemy.orm import Session

from ..models import AssistantQuota

DEFAULT_GEMINI_DAILY_QUOTA = 20  # REAL limit, not a guess: a live 429 from generate_content
# (2026-09-23) reported "GenerateRequestsPerDayPerProjectPerModel-FreeTier... quotaValue: 20"
# for gemini-3.6-flash specifically - the free tier's per-day cap is per (project, model),
# and it is much smaller than this file previously assumed (250, an unverified guess made
# before any real key existed). GEMINI_DAILY_QUOTA in .env can raise this if a paid plan or
# a different model with a higher quota is used later - don't raise the default without a
# new real 429 message confirming the new number.
DEFAULT_YOUTUBE_DAILY_QUOTA = 90  # YouTube Data API v3 free quota is 10,000 units/day; search.list costs 100 units


def _today() -> str:
    return _dt.now(timezone.utc).date().isoformat()


def _row(session: Session) -> AssistantQuota:
    today = _today()
    row = session.get(AssistantQuota, today)
    if row is None:
        row = AssistantQuota(day=today, gemini_calls=0, youtube_calls=0)
        session.add(row)
        session.commit()
    return row


def gemini_quota_remaining(session: Session) -> int:
    limit = int(os.environ.get("GEMINI_DAILY_QUOTA", DEFAULT_GEMINI_DAILY_QUOTA))
    return max(0, limit - _row(session).gemini_calls)


def youtube_quota_remaining(session: Session) -> int:
    limit = int(os.environ.get("YOUTUBE_DAILY_QUOTA", DEFAULT_YOUTUBE_DAILY_QUOTA))
    return max(0, limit - _row(session).youtube_calls)


def record_gemini_call(session: Session) -> None:
    row = _row(session)
    row.gemini_calls += 1
    session.commit()


def record_youtube_call(session: Session) -> None:
    row = _row(session)
    row.youtube_calls += 1
    session.commit()
