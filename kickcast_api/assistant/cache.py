from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import AssistantCache


def _key(question: str) -> str:
    normalized = " ".join(question.strip().lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def get_cached(session: Session, question: str) -> dict | None:
    row = session.get(AssistantCache, _key(question))
    return json.loads(row.answer_json) if row else None


def set_cached(session: Session, question: str, answer: dict) -> None:
    key = _key(question)
    row = session.get(AssistantCache, key)
    payload = json.dumps(answer)
    now = datetime.now(timezone.utc).isoformat()
    if row is None:
        session.add(AssistantCache(question_hash=key, question=question, answer_json=payload, created_at=now))
    else:
        row.answer_json = payload
        row.created_at = now
    session.commit()
