"""Time-safe award ranking interface without fabricated quality scores."""

from datetime import datetime
from typing import Protocol

import pandas as pd


class AwardRanker(Protocol):
    """Contract for statistical and separately weighted media rankers."""

    def rank(self, award: str, as_of: datetime, candidates: pd.DataFrame) -> pd.DataFrame:
        """Rank candidates using inputs published no later than ``as_of``."""
        ...


class AwardModuleNotTrainedError(RuntimeError):
    """Raised instead of inventing award rankings without data and labels."""
