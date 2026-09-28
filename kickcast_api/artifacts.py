"""Build artifacts: everything expensive is computed at build time or by the nightly job and only
LOADED while serving.

  - fitted models (goals + cards) are pickled to MODELS_DIR (default data/models/), one file each;
  - trophy odds and Golden Boot projections are JSON rows in the `payloads` table.

Render's free instance loses runtime filesystem changes on every restart, but whatever the build step
wrote ships with the deploy - so a cold start serves immediately from these, no fitting.
"""

from __future__ import annotations

import json
import os
import pickle
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .models import Payload

REPO_ROOT = Path(__file__).resolve().parents[1]


def models_dir() -> Path:
    return Path(os.environ.get("MODELS_DIR", REPO_ROOT / "data" / "models"))


def _model_path(kind: str, league_code: str) -> Path:
    return models_dir() / f"{kind}__{league_code.replace('.', '_')}.pkl"


def save_model(kind: str, league_code: str, bundle: Any) -> None:
    path = _model_path(kind, league_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(bundle, protocol=pickle.HIGHEST_PROTOCOL))
    tmp.replace(path)  # atomic: a request never sees a half-written file


def load_model(kind: str, league_code: str) -> Any | None:
    path = _model_path(kind, league_code)
    if not path.exists():
        return None
    try:
        return pickle.loads(path.read_bytes())  # our own build output, never user input
    except Exception:  # noqa: BLE001 - a corrupt/incompatible artifact must not take the API down
        return None


def put_payload(session: Session, key: str, data: Any) -> None:
    row = session.get(Payload, key)
    now = datetime.now(UTC).isoformat()
    if row is None:
        session.add(Payload(key=key, json=json.dumps(data), computed_at=now))
    else:
        row.json, row.computed_at = json.dumps(data), now
    session.commit()


def get_payload(session: Session, key: str) -> Any | None:
    row = session.get(Payload, key)
    return json.loads(row.json) if row else None
