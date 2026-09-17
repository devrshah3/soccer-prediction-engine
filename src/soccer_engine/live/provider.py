"""Live-feed provider boundary with throttling and circuit-breaker semantics."""

import os
import time
from abc import ABC, abstractmethod
from datetime import datetime

from tenacity import retry, stop_after_attempt, wait_exponential

from soccer_engine.live.schemas import LiveEvent


class LiveProviderUnavailable(RuntimeError):
    """A legitimate live feed is not configured or its circuit is open."""


class LiveEventProvider(ABC):
    name: str
    requires_credentials: bool = True

    def __init__(
        self,
        requests_per_second: float = 1.0,
        failure_threshold: int = 3,
        request_timeout_seconds: float = 10.0,
    ) -> None:
        if requests_per_second <= 0 or request_timeout_seconds <= 0:
            raise ValueError("rate and timeout must be positive")
        self.requests_per_second = requests_per_second
        self.failure_threshold = failure_threshold
        # Concrete HTTP transports must pass this value to their client request.
        self.request_timeout_seconds = request_timeout_seconds
        self.failures = 0
        self.circuit_opened_at: float | None = None
        self._last_request = 0.0

    def _throttle(self) -> None:
        delay = 1 / self.requests_per_second
        elapsed = time.monotonic() - self._last_request
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request = time.monotonic()

    def _check_circuit(self) -> None:
        if self.circuit_opened_at is not None and time.monotonic() - self.circuit_opened_at < 60:
            raise LiveProviderUnavailable(f"{self.name} circuit is open after repeated failures")
        if self.circuit_opened_at is not None:
            self.failures = 0
            self.circuit_opened_at = None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def fetch(self, fixture_id: str, since: datetime | None = None) -> list[LiveEvent]:
        self._check_circuit()
        self._throttle()
        try:
            events = self._fetch(fixture_id, since)
            self.failures = 0
            return events
        except Exception:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.circuit_opened_at = time.monotonic()
            raise

    @abstractmethod
    def _fetch(self, fixture_id: str, since: datetime | None) -> list[LiveEvent]:
        """Return legally obtained normalized events newer than the cursor."""


class CredentialedLiveProvider(LiveEventProvider):
    """Explicit placeholder for a user-licensed live feed; no site scraping is performed."""

    name = "licensed_live_provider"

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__()
        self.api_key = api_key or os.getenv("LIVE_SOCCER_API_KEY")

    def _fetch(self, fixture_id: str, since: datetime | None) -> list[LiveEvent]:
        if not self.api_key:
            raise LiveProviderUnavailable(
                "LIVE_SOCCER_API_KEY is required; configure a licensed provider transport"
            )
        raise LiveProviderUnavailable(
            "credential detected but no vendor transport is selected; replay remains available"
        )
