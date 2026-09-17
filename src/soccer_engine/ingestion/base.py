"""Provider contract."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from soccer_engine.schemas import MatchRecord


class ProviderUnavailableError(RuntimeError):
    """Provider cannot be used without a credential or configured source."""


class DataProvider(ABC):
    """Interface implemented by historical and fixture providers."""

    name: str
    requires_credentials: bool = False
    attribution_url: str = ""

    @abstractmethod
    def fetch_matches(self, competition_id: str, season_id: str) -> Sequence[MatchRecord]:
        """Fetch and normalize matches for a provider competition/season."""

    def fetch_upcoming_fixtures(self, competition_id: str) -> Sequence[MatchRecord]:
        """Fetch scheduled fixtures when the provider supports them."""

        return []

    def status(self) -> dict[str, str | bool]:
        """Return machine-readable capability information without making a request."""

        return {
            "provider": self.name,
            "available": True,
            "credential_required": self.requires_credentials,
            "attribution_url": self.attribution_url,
        }
