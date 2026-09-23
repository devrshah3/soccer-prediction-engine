from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import ExternalApiQuota

DEFAULT_API_FOOTBALL_DAILY_QUOTA = 100  # the actual free-tier limit


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _row(session: Session) -> ExternalApiQuota:
    today = _today()
    row = session.get(ExternalApiQuota, today)
    if row is None:
        row = ExternalApiQuota(day=today, api_football_calls=0)
        session.add(row)
        session.commit()
    return row


def api_football_quota_remaining(session: Session) -> int:
    limit = int(os.environ.get("API_FOOTBALL_DAILY_QUOTA", DEFAULT_API_FOOTBALL_DAILY_QUOTA))
    return max(0, limit - _row(session).api_football_calls)


def record_api_football_call(session: Session) -> None:
    row = _row(session)
    row.api_football_calls += 1
    session.commit()
