"""Replay = yesterday (item 6). The viewer's local "yesterday" is derived at request time
from the real clock plus the viewer's UTC offset (`tz`, minutes east of UTC, i.e. the
negation of JavaScript's Date.getTimezoneOffset()) - never a stored or hardcoded date.
`date` exists only so the "most recent day that had matches" link has somewhere to go; it
can never be today or later.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from datetime import date as date_module

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..replay import day_replay

router = APIRouter(prefix="/replay", tags=["replay"])

MAX_TZ_OFFSET_MINUTES = 14 * 60


def local_yesterday(offset_minutes: int, now: datetime | None = None) -> date_module:
    now = now or datetime.now(UTC)
    return (now + timedelta(minutes=offset_minutes)).date() - timedelta(days=1)


@router.get("/day")
def replay_day(date: str | None = None, tz: int = 0, session: Session = Depends(get_session)) -> dict:
    if abs(tz) > MAX_TZ_OFFSET_MINUTES:
        raise HTTPException(400, "tz must be minutes east of UTC, within +/-840")
    yesterday = local_yesterday(tz)
    if date is None:
        target = yesterday
    else:
        try:
            target = date_module.fromisoformat(date)
        except ValueError:
            raise HTTPException(400, "date must be YYYY-MM-DD") from None
        if target > yesterday:
            raise HTTPException(400, "replay only covers days before today")
    return day_replay(session, target, tz)
