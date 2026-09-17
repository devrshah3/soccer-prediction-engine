"""Provider adapters."""

from soccer_engine.ingestion.base import DataProvider, ProviderUnavailableError
from soccer_engine.ingestion.football_data_org import FootballDataOrgProvider
from soccer_engine.ingestion.football_data_uk import FootballDataUKProvider
from soccer_engine.ingestion.future import (
    APIFootballProvider,
    OpenLigaDBProvider,
    SportmonksProvider,
)
from soccer_engine.ingestion.statsbomb import StatsBombOpenDataProvider

__all__ = [
    "APIFootballProvider",
    "DataProvider",
    "FootballDataOrgProvider",
    "FootballDataUKProvider",
    "OpenLigaDBProvider",
    "ProviderUnavailableError",
    "SportmonksProvider",
    "StatsBombOpenDataProvider",
]
