from __future__ import annotations

import pytest
from requests.structures import CaseInsensitiveDict

from kickcast_api import football_data_org as fdo


@pytest.fixture(autouse=True)
def _reset_throttle_state():
    fdo._state["available_minute"] = None
    fdo._state["reset_at"] = None
    yield
    fdo._state["available_minute"] = None
    fdo._state["reset_at"] = None


def test_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("FOOTBALL_DATA_ORG_API_KEY", raising=False)
    assert fdo.available() is False
    assert fdo.get("/competitions/CL") is None


def test_records_real_header_names_and_values(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_ORG_API_KEY", "fake-key")

    class FakeResponse:
        status_code = 200
        headers = CaseInsensitiveDict({"X-RequestCounter-Reset": "42", "x-requests-available-minute": "7"})

        def raise_for_status(self):
            pass

        def json(self):
            return {"code": "CL"}

    monkeypatch.setattr(fdo.requests, "get", lambda *a, **kw: FakeResponse())
    body = fdo.get("/competitions/CL")
    assert body == {"code": "CL"}
    assert fdo._state["available_minute"] == 7
    assert fdo._state["reset_at"] is not None


def test_throttles_before_call_when_budget_was_exhausted(monkeypatch):
    """If the last real response said 0 remaining and N seconds to reset, the next call
    must sleep roughly N seconds BEFORE firing, not fire and get rejected."""
    monkeypatch.setenv("FOOTBALL_DATA_ORG_API_KEY", "fake-key")

    fake_now = [1000.0]
    monkeypatch.setattr(fdo.time, "monotonic", lambda: fake_now[0])
    slept = []
    monkeypatch.setattr(fdo.time, "sleep", lambda s: slept.append(s))

    fdo._state["available_minute"] = 0
    fdo._state["reset_at"] = 1005.0  # 5s from "now"

    class FakeResponse:
        status_code = 200
        headers = CaseInsensitiveDict({"X-RequestCounter-Reset": "60", "x-requests-available-minute": "9"})

        def raise_for_status(self):
            pass

        def json(self):
            return {}

    monkeypatch.setattr(fdo.requests, "get", lambda *a, **kw: FakeResponse())
    fdo.get("/competitions/CL")
    assert slept == [5.0]


def test_does_not_sleep_when_budget_remains(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_ORG_API_KEY", "fake-key")
    slept = []
    monkeypatch.setattr(fdo.time, "sleep", lambda s: slept.append(s))
    fdo._state["available_minute"] = 3
    fdo._state["reset_at"] = None

    class FakeResponse:
        status_code = 200
        headers = CaseInsensitiveDict({"X-RequestCounter-Reset": "60", "x-requests-available-minute": "2"})

        def raise_for_status(self):
            pass

        def json(self):
            return {}

    monkeypatch.setattr(fdo.requests, "get", lambda *a, **kw: FakeResponse())
    fdo.get("/competitions/CL")
    assert slept == []


def test_429_forces_a_minute_backoff_without_retrying(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_ORG_API_KEY", "fake-key")
    monkeypatch.setattr(fdo.time, "monotonic", lambda: 2000.0)

    class FakeResponse:
        status_code = 429
        headers = CaseInsensitiveDict()

        def raise_for_status(self):
            raise AssertionError("should not be called on a 429")

        def json(self):
            raise AssertionError("should not be called on a 429")

    monkeypatch.setattr(fdo.requests, "get", lambda *a, **kw: FakeResponse())
    assert fdo.get("/competitions/CL") is None
    assert fdo._state["available_minute"] == 0
    assert fdo._state["reset_at"] == 2060.0


def test_network_error_returns_none(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_ORG_API_KEY", "fake-key")

    def raising_get(*a, **kw):
        raise fdo.requests.RequestException("boom")

    monkeypatch.setattr(fdo.requests, "get", raising_get)
    assert fdo.get("/competitions/CL") is None
