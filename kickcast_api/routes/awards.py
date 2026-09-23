from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..awards import get_awards
from ..db import get_session

router = APIRouter(prefix="/awards", tags=["awards"])


@router.get("")
def awards(session: Session = Depends(get_session)) -> dict:
    return get_awards(session)
