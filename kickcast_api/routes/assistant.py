from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..assistant.service import ask
from ..db import get_session

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AskRequest(BaseModel):
    question: str


@router.post("/ask")
def assistant_ask(body: AskRequest, session: Session = Depends(get_session)) -> dict:
    return ask(session, body.question)
