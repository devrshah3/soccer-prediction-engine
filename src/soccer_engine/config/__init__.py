"""Runtime configuration."""

from soccer_engine.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
from soccer_engine.config.registry import CompetitionRegistry, CoverageStatus, coverage_report

__all__ = ["CompetitionRegistry", "CoverageStatus", "Settings", "coverage_report", "get_settings"]
