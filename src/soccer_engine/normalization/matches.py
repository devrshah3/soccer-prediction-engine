"""Match normalization helpers."""

from collections.abc import Iterable

import pandas as pd

from soccer_engine.identity import IdentityResolver
from soccer_engine.schemas import MatchRecord, MatchStatus


def deduplicate_matches(records: Iterable[MatchRecord]) -> list[MatchRecord]:
    """Deduplicate by provider ID, rejecting conflicting duplicates."""

    unique: dict[tuple[str, str], MatchRecord] = {}
    for record in records:
        key = (record.provider, record.provider_match_id)
        existing = unique.get(key)
        if existing is not None and existing.model_dump() != record.model_dump():
            raise ValueError(f"conflicting match records for {key}")
        unique[key] = record
    return list(unique.values())


def deduplicate_cross_provider_matches(
    records: Iterable[MatchRecord], resolver: IdentityResolver | None = None
) -> tuple[list[MatchRecord], list[tuple[str, str]]]:
    """Flag same-day/team overlaps for review; never silently merge ambiguous sources."""

    resolver = resolver or IdentityResolver()
    unique: list[MatchRecord] = []
    fingerprints: dict[tuple[str, str, str], MatchRecord] = {}
    review: list[tuple[str, str]] = []
    for record in deduplicate_matches(records):
        key = (
            record.kickoff.date().isoformat(),
            resolver.resolve_team(record.home_team_name),
            resolver.resolve_team(record.away_team_name),
        )
        previous = fingerprints.get(key)
        if previous is not None and previous.provider != record.provider:
            review.append((previous.match_id, record.match_id))
            continue
        fingerprints[key] = record
        unique.append(record)
    return unique, review


def records_to_frame(records: Iterable[MatchRecord], finished_only: bool = False) -> pd.DataFrame:
    """Convert validated records into a typed, chronologically ordered frame."""

    values = list(records)
    if finished_only:
        values = [record for record in values if record.status == MatchStatus.FINISHED]
    frame = pd.DataFrame([record.model_dump(mode="json") for record in values])
    if frame.empty:
        return frame
    frame["kickoff"] = pd.to_datetime(frame["kickoff"], utc=True)
    frame = frame.sort_values(["kickoff", "match_id"]).drop_duplicates("match_id", keep="last")
    return frame.reset_index(drop=True)
