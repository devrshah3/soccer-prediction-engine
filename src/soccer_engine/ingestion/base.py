"""Provider contract."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from soccer_engine.schemas import MatchRecord


class DataProvider(ABC):
    """Interface implemented by historical and fixture providers."""

    name: str

    @abstractmethod
    def fetch_matches(self, competition_id: str, season_id: str) -> Sequence[MatchRecord]:
        """Fetch and normalize matches for a provider competition/season."""

    def fetch_upcoming_fixtures(self, competition_id: str) -> Sequence[MatchRecord]:
        """Fetch scheduled fixtures when the provider supports them."""

        return []
