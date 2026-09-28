from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..awards import get_awards
from ..db import get_session
from ..serialize import seasons

router = APIRouter(prefix="/awards", tags=["awards"])

METHOD_REPORT_PATH = Path(__file__).resolve().parents[2] / "reports" / "golden_boot_backtest.json"


@router.get("")
def awards(season: str | None = None, session: Session = Depends(get_session)) -> dict:
    result = get_awards(session, season)
    result["available_seasons"] = seasons(session, "en.1")
    return result


@router.get("/method")
def awards_method() -> dict:
    """The Golden Boot projection's internal backtest against real StatsBomb 2015/16
    data - see scripts/backtest_golden_boot_projection.py. 404s (not a fabricated empty
    report) if the report hasn't been generated."""
    if not METHOD_REPORT_PATH.exists():
        raise HTTPException(404, "backtest report not generated - run "
                                  "scripts/backtest_golden_boot_projection.py")
    return json.loads(METHOD_REPORT_PATH.read_text())
