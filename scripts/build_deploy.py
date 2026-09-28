"""Build step for the public deployment (Render): produce a database that SHIPS with the deploy, so a
cold start serves immediately instead of ingesting/fitting first.

    pip install -r requirements.txt && python scripts/build_deploy.py

Steps (each timed; total printed at the end):
  1. fetch the open data       scripts/fetch_open_data.sh   (openfootball, martj42)
  2. fetch football-data.co.uk scripts/fetch_footballdata_uk.py
  3. ingest                    scripts/ingest.py            (also 1 football-data.org call for the Champions League if enabled)
  4. artifacts                 models (pickled), trophy odds, Golden Boot projections, match predictions

The build fails loudly if any of the data steps fails (an empty site is worse than a failed deploy)
and if the finished database is missing the tables the site needs.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

timings: dict[str, float] = {}


def run(name: str, cmd: list[str]) -> None:
    print(f"\n=== {name} ===", flush=True)
    started = time.monotonic()
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    timings[name] = time.monotonic() - started


def main() -> None:
    total = time.monotonic()
    run("fetch open data", ["bash", "scripts/fetch_open_data.sh"])
    run("fetch football-data.co.uk", [sys.executable, "scripts/fetch_footballdata_uk.py"])
    run("ingest", [sys.executable, "scripts/ingest.py"])

    print("\n=== build artifacts (models, trophy odds, Golden Boot, predictions) ===", flush=True)
    started = time.monotonic()
    from kickcast_api import build
    from kickcast_api.db import SessionLocal
    from kickcast_api.models import Match

    session = SessionLocal()
    try:
        report = build.build_everything(session, network=True)
        matches = session.query(Match).count()
    finally:
        session.close()
    timings["build artifacts"] = time.monotonic() - started
    print("artifact steps (seconds):", report)
    failed = [k for k, v in report.items() if v < 0]
    if matches < 1000 or failed:
        raise SystemExit(f"build incomplete: {matches} matches, failed artifact steps: {failed}")

    print("\n=== build timing ===")
    for name, seconds in timings.items():
        print(f"  {name:32s} {seconds:7.1f}s")
    print(f"  {'TOTAL':32s} {time.monotonic() - total:7.1f}s  ({matches} matches in the database)")


if __name__ == "__main__":
    main()
