"""Provider adapters."""

from soccer_engine.ingestion.base import DataProvider
from soccer_engine.ingestion.football_data_org import FootballDataOrgProvider
from soccer_engine.ingestion.statsbomb import StatsBombOpenDataProvider

__all__ = ["DataProvider", "FootballDataOrgProvider", "StatsBombOpenDataProvider"]
