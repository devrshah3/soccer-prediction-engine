"""Leakage-safe accelerated StatsBomb event replay."""

import hashlib
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from soccer_engine.ingestion import StatsBombOpenDataProvider
from soccer_engine.live.engine import LiveEngine
from soccer_engine.live.schemas import (
    FeedMode,
    LiveEvent,
    LiveEventType,
    ReplayResult,
    ReplaySnapshot,
)

MEANINGFUL = {
    LiveEventType.GOAL,
    LiveEventType.SHOT,
    LiveEventType.SHOT_ON_TARGET,
    LiveEventType.RED_CARD,
    LiveEventType.PENALTY,
    LiveEventType.DISALLOWED_GOAL,
}


class StatsBombReplay:
    """Reveal cached events in time order without reading future events into model state."""

    def __init__(
        self,
        engine: LiveEngine | None = None,
        provider: StatsBombOpenDataProvider | None = None,
        output_dir: Path = Path("data/predictions/replays"),
    ) -> None:
        self.engine = engine or LiveEngine()
        self.provider = provider or StatsBombOpenDataProvider()
        self.output_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

    def normalize(self, fixture_id: str, provider_match_id: str) -> list[LiveEvent]:
        raw_events = self.provider.fetch_events(provider_match_id)
        fixture = self.engine.service.matches()
        row = fixture[fixture["match_id"] == fixture_id].iloc[0]
        kickoff = pd.Timestamp(row["kickoff"]).to_pydatetime()
        events: list[LiveEvent] = []
        for raw in raw_events:
            event = self._normalize_event(
                fixture_id,
                raw,
                kickoff,
                str(row["home_team_id"]),
                str(row["away_team_id"]),
            )
            if event is not None:
                events.append(event)
        return sorted(
            events, key=lambda item: (item.minute, item.stoppage_time, item.event_id or "")
        )

    def _normalize_event(
        self,
        fixture_id: str,
        raw: dict[str, Any],
        kickoff: Any,
        home_team_id: str,
        away_team_id: str,
    ) -> LiveEvent | None:
        event_name = (raw.get("type") or {}).get("name")
        event_type = None
        xg = None
        if event_name == "Shot":
            shot = raw.get("shot") or {}
            outcome = (shot.get("outcome") or {}).get("name")
            event_type = (
                LiveEventType.GOAL
                if outcome == "Goal"
                else LiveEventType.SHOT_ON_TARGET
                if outcome in {"Saved", "Saved To Post"}
                else LiveEventType.SHOT
            )
            xg = float(shot.get("statsbomb_xg") or 0)
        elif event_name == "Foul Committed":
            card = ((raw.get("foul_committed") or {}).get("card") or {}).get("name")
            event_type = (
                LiveEventType.RED_CARD
                if card in {"Red Card", "Second Yellow"}
                else LiveEventType.YELLOW_CARD
                if card == "Yellow Card"
                else LiveEventType.FOUL
            )
        elif event_name == "Substitution":
            event_type = LiveEventType.SUBSTITUTION
        elif event_name == "Injury Stoppage":
            event_type = LiveEventType.INJURY
        elif event_name == "Goal Keeper":
            outcome = ((raw.get("goalkeeper") or {}).get("outcome") or {}).get("name", "")
            if "Saved" in outcome:
                event_type = LiveEventType.SAVE
        elif event_name == "Own Goal Against":
            event_type = LiveEventType.GOAL
        if event_type is None:
            return None
        team = raw.get("team") or {}
        team_id = f"statsbomb:{team['id']}" if team.get("id") is not None else None
        team_name = team.get("name")
        if event_name == "Own Goal Against":
            team_id = away_team_id if team_id == home_team_id else home_team_id
            team_name = None
        player = raw.get("player") or {}
        minute = int(raw.get("minute", 0))
        timestamp = str(raw.get("timestamp") or "00:00:00")
        parts = timestamp.split(":")
        seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        feed_timestamp = kickoff + timedelta(seconds=seconds)
        raw_id = str(raw.get("id") or hashlib.sha256(str(raw).encode()).hexdigest()[:24])
        return LiveEvent(
            fixture_id=fixture_id,
            event_id=f"statsbomb:{raw_id}",
            provider="statsbomb_open_data_replay",
            provider_timestamp=feed_timestamp,
            minute=minute,
            event_type=event_type,
            team_id=team_id,
            team_name=team_name,
            player_id=f"statsbomb:{player['id']}" if player.get("id") is not None else None,
            player_name=player.get("name"),
            xg=xg,
        )

    def run(self, match_id: str, interval_minutes: int = 5) -> ReplayResult:
        matches = self.engine.service.matches()
        selected = matches[matches["match_id"] == match_id]
        if selected.empty:
            raise KeyError(match_id)
        fixture = selected.iloc[0]
        self.engine.store.reset(match_id)
        state = self.engine.register_fixture(
            match_id,
            provider="StatsBomb Open Data replay",
            mode=FeedMode.REPLAY,
            feed_timestamp=fixture["kickoff"],
            confirmed_lineups=True,
        )
        events = self.normalize(match_id, str(fixture["provider_match_id"]))
        snapshots: list[ReplaySnapshot] = []
        last_snapshot = -interval_minutes
        for event in events:
            state, created, prediction = self.engine.ingest_event(event)
            if created and (
                event.event_type in MEANINGFUL or event.minute - last_snapshot >= interval_minutes
            ):
                snapshots.append(
                    ReplaySnapshot(
                        minute=state.minute, event_id=event.event_id, prediction=prediction
                    )
                )
                last_snapshot = event.minute
        result = ReplayResult(
            match_id=match_id,
            snapshots=snapshots,
            revealed_events=len(state.events),
            source="StatsBomb Open Data cached historical events; replay is not live",
        )
        target = self.output_dir / f"{hashlib.sha256(match_id.encode()).hexdigest()}.json"
        target.write_text(result.model_dump_json(indent=2))
        return result
