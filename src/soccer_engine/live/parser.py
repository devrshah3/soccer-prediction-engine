"""Auditable deterministic commentary parser."""

import hashlib
import re
from datetime import UTC

from soccer_engine.live.schemas import CommentaryInput, LiveEvent, LiveEventType

TIME_PATTERN = re.compile(r"(?<!\d)(\d{1,3})(?:\+(\d{1,2}))?['’]?")


class CommentaryParser:
    """Convert high-confidence commentary patterns into normalized events."""

    def parse(self, item: CommentaryInput) -> LiveEvent | None:
        text = " ".join(item.text.split())
        lowered = text.casefold()
        clock = TIME_PATTERN.search(text)
        if not clock:
            return None
        minute = int(clock.group(1))
        stoppage = int(clock.group(2) or 0)
        if any(phrase in lowered for phrase in ("no penalty", "not a penalty")):
            return None
        event_type, confidence = self._event_type(lowered)
        if event_type is None or confidence < 0.75:
            return None
        team_id, team_name = self._team(item, lowered)
        if event_type not in {LiveEventType.VAR, LiveEventType.CORRECTION} and team_id is None:
            return None
        player = self._player(text, team_name)
        fingerprint = (
            f"{item.provider}|{item.fixture_id}|{minute}|{stoppage}|{event_type}|{team_id}|{player}"
        )
        return LiveEvent(
            fixture_id=item.fixture_id,
            event_id=hashlib.sha256(fingerprint.encode()).hexdigest()[:24],
            provider=item.provider,
            provider_timestamp=item.provider_timestamp.astimezone(UTC),
            minute=minute,
            stoppage_time=stoppage,
            event_type=event_type,
            team_id=team_id,
            team_name=team_name,
            player_name=player,
            parser_confidence=confidence,
            original_text=item.text,
        )

    @staticmethod
    def _event_type(text: str) -> tuple[LiveEventType | None, float]:
        if any(word in text for word in ("might", "could", "perhaps", "appears to")):
            return None, 0.4
        if "goal disallowed" in text or "goal ruled out" in text or "no goal" in text:
            return LiveEventType.DISALLOWED_GOAL, 0.98
        patterns = (
            (("goal!", "scores!", "scores for"), LiveEventType.GOAL, 0.97),
            (("red card", "sent off"), LiveEventType.RED_CARD, 0.96),
            (("yellow card", "booked"), LiveEventType.YELLOW_CARD, 0.94),
            (("penalty awarded", "penalty to"), LiveEventType.PENALTY, 0.96),
            (("shot on target", "forces a save"), LiveEventType.SHOT_ON_TARGET, 0.91),
            (("shot", "attempt"), LiveEventType.SHOT, 0.82),
            (("corner",), LiveEventType.CORNER, 0.92),
            (("substitution", "comes on for", "replaces"), LiveEventType.SUBSTITUTION, 0.9),
            (("var check", "var review", "var decision"), LiveEventType.VAR, 0.9),
            (("injury", "receiving treatment"), LiveEventType.INJURY, 0.82),
            (("save by", "goalkeeper saves"), LiveEventType.SAVE, 0.9),
            (("foul",), LiveEventType.FOUL, 0.85),
        )
        for phrases, event_type, confidence in patterns:
            if any(phrase in text for phrase in phrases):
                return event_type, confidence
        return None, 0.0

    @staticmethod
    def _team(item: CommentaryInput, lowered: str) -> tuple[str | None, str | None]:
        home = item.home_team_name.casefold()
        away = item.away_team_name.casefold()
        if home in lowered and away in lowered:
            return None, None
        if home in lowered:
            return item.home_team_id, item.home_team_name
        if away in lowered:
            return item.away_team_id, item.away_team_name
        return None, None

    @staticmethod
    def _player(text: str, team_name: str | None) -> str | None:
        cleaned = TIME_PATTERN.sub("", text)
        cleaned = re.sub(
            r"(?i)goal!?|scores!?|yellow card|red card|shot on target|shot|corner|foul|for|by",
            " ",
            cleaned,
        )
        if team_name:
            cleaned = re.sub(re.escape(team_name), " ", cleaned, flags=re.IGNORECASE)
        value = " ".join(cleaned.split()).strip(" .,:;!-")
        return value[:100] or None
