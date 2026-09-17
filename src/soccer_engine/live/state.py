"""Idempotent event storage and deterministic live-state reconstruction."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from soccer_engine.live.schemas import (
    FeedMode,
    LiveEvent,
    LiveEventType,
    LiveMatchRegistration,
    LiveMatchState,
    TeamLiveStats,
)

MEANINGFUL_ATTACKS = {
    LiveEventType.GOAL,
    LiveEventType.SHOT,
    LiveEventType.SHOT_ON_TARGET,
    LiveEventType.CORNER,
    LiveEventType.DANGEROUS_ATTACK,
    LiveEventType.PENALTY,
}


class LiveStateStore:
    """Persist registrations/events and rebuild state to support out-of-order corrections."""

    def __init__(self, root: Path = Path("data/predictions/live")) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, fixture_id: str) -> Path:
        safe = hashlib.sha256(fixture_id.encode()).hexdigest()
        return self.root / f"{safe}.json"

    def register(self, registration: LiveMatchRegistration) -> LiveMatchState:
        path = self._path(registration.fixture_id)
        if path.exists():
            return self.get(registration.fixture_id)
        state = LiveMatchState(
            **registration.model_dump(),
            estimated_latency_seconds=self._latency(registration.feed_timestamp),
        )
        self._save(state)
        return state

    def list_matches(self) -> list[LiveMatchState]:
        return [
            LiveMatchState.model_validate_json(path.read_text())
            for path in self.root.glob("*.json")
        ]

    def get(self, fixture_id: str) -> LiveMatchState:
        path = self._path(fixture_id)
        if not path.exists():
            raise KeyError(fixture_id)
        return LiveMatchState.model_validate_json(path.read_text())

    def reset(self, fixture_id: str) -> None:
        """Remove only one replay/live state file; source data and predictions remain untouched."""

        path = self._path(fixture_id)
        if path.exists():
            path.unlink()

    def ingest(self, event: LiveEvent) -> tuple[LiveMatchState, bool]:
        state = self.get(event.fixture_id)
        if event.parser_confidence < 0.75:
            return state, False
        if not event.event_id:
            payload = event.model_dump(mode="json", exclude={"event_id"})
            event.event_id = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest()[:24]
        if any(item.event_id == event.event_id for item in state.events):
            return state, False
        events = [*state.events, event]
        if event.correction_for_event_id:
            for previous in events:
                if previous.event_id == event.correction_for_event_id:
                    previous.overturned = True
        elif event.event_type == LiveEventType.DISALLOWED_GOAL:
            candidates = [
                item
                for item in events
                if item.event_type == LiveEventType.GOAL
                and not item.overturned
                and (event.team_id is None or item.team_id == event.team_id)
                and item.minute <= event.minute
            ]
            if candidates:
                max(
                    candidates, key=lambda item: (item.minute, item.stoppage_time)
                ).overturned = True
        rebuilt = self._rebuild(state, events)
        self._save(rebuilt)
        return rebuilt, True

    def _rebuild(self, previous: LiveMatchState, events: list[LiveEvent]) -> LiveMatchState:
        ordered = sorted(
            events,
            key=lambda item: (
                item.minute,
                item.stoppage_time,
                item.provider_timestamp,
                item.event_id or "",
            ),
        )
        home = TeamLiveStats()
        away = TeamLiveStats()
        home_score = away_score = 0
        last_attack = None
        for event in ordered:
            if event.overturned:
                continue
            target = home if event.team_id == previous.home_team_id else away
            if event.event_type == LiveEventType.GOAL:
                if event.team_id == previous.home_team_id:
                    home_score += 1
                elif event.team_id == previous.away_team_id:
                    away_score += 1
                target.shots += 1
                target.shots_on_target += 1
            elif event.event_type == LiveEventType.SHOT:
                target.shots += 1
            elif event.event_type == LiveEventType.SHOT_ON_TARGET:
                target.shots += 1
                target.shots_on_target += 1
            elif event.event_type == LiveEventType.CORNER:
                target.corners += 1
            elif event.event_type == LiveEventType.FOUL:
                target.fouls += 1
            elif event.event_type == LiveEventType.YELLOW_CARD:
                target.yellow_cards += 1
            elif event.event_type == LiveEventType.RED_CARD:
                target.red_cards += 1
            elif event.event_type == LiveEventType.PENALTY:
                target.penalties += 1
            elif event.event_type == LiveEventType.SUBSTITUTION:
                target.substitutions += 1
            elif event.event_type == LiveEventType.INJURY:
                target.injuries += 1
            elif event.event_type == LiveEventType.SAVE:
                target.saves += 1
            elif event.event_type == LiveEventType.DANGEROUS_ATTACK:
                target.dangerous_attacks += 1
            elif event.event_type == LiveEventType.POSSESSION and event.value is not None:
                target.possession = event.value
            if event.xg is not None and event.event_type in {
                LiveEventType.GOAL,
                LiveEventType.SHOT,
                LiveEventType.SHOT_ON_TARGET,
            }:
                target.supplied_xg += event.xg
            if event.event_type in MEANINGFUL_ATTACKS:
                last_attack = event.minute
        latest = max(ordered, key=lambda item: item.provider_timestamp) if ordered else None
        clock = (
            max(ordered, key=lambda item: (item.minute, item.stoppage_time)) if ordered else None
        )
        feed_timestamp = latest.provider_timestamp if latest else previous.feed_timestamp
        warnings = list(previous.warnings)
        latency = self._latency(feed_timestamp)
        if previous.feed_mode == FeedMode.LIVE and latency > 120:
            warnings.append("Feed is stale; live status has been downgraded to delayed.")
        mode = (
            FeedMode.DELAYED
            if previous.feed_mode == FeedMode.LIVE and latency > 120
            else previous.feed_mode
        )
        return previous.model_copy(
            update={
                "events": ordered,
                "minute": clock.minute if clock else 0,
                "stoppage_time": clock.stoppage_time if clock else 0,
                "home_score": home_score,
                "away_score": away_score,
                "home_stats": home,
                "away_stats": away,
                "feed_timestamp": feed_timestamp,
                "estimated_latency_seconds": latency,
                "feed_mode": mode,
                "last_meaningful_attack_minute": last_attack,
                "warnings": sorted(set(warnings)),
            }
        )

    def _save(self, state: LiveMatchState) -> None:
        target = self._path(state.fixture_id)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(state.model_dump_json(indent=2))
        temporary.replace(target)

    @staticmethod
    def _latency(timestamp: datetime) -> float:
        value = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
        return max(0.0, (datetime.now(UTC) - value).total_seconds())
