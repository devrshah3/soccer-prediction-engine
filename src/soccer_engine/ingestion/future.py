"""Honest interfaces for legitimate providers not enabled in the offline distribution."""

from collections.abc import Sequence

from soccer_engine.ingestion.base import DataProvider, ProviderUnavailableError
from soccer_engine.schemas import MatchRecord


class CredentialedProvider(DataProvider):
    """Base capability declaration; concrete licensed adapters can implement transport later."""

    requires_credentials = True

    def fetch_matches(self, competition_id: str, season_id: str) -> Sequence[MatchRecord]:
        raise ProviderUnavailableError(
            f"{self.name} is adapter-ready but requires a licensed account and implementation"
        )

    def status(self) -> dict[str, str | bool]:
        value = super().status()
        value["available"] = False
        return value


class APIFootballProvider(CredentialedProvider):
    name = "api_football"
    attribution_url = "https://www.api-football.com/"


class SportmonksProvider(CredentialedProvider):
    name = "sportmonks"
    attribution_url = "https://www.sportmonks.com/football-api/"


class OpenLigaDBProvider(CredentialedProvider):
    name = "openligadb"
    requires_credentials = False
    attribution_url = "https://www.openligadb.de/"
