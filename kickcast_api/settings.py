"""All configuration comes from environment variables (documented in .env.example). Read on each
call, not cached at import, so tests and hosts can change them without reloading modules.

APP_ENV=production turns on the public-deployment behaviour: heavy work (model fits, Monte Carlo,
provider calls) happens only at build time or in the nightly/background jobs and never per request;
/docs is off; CORS is limited to FRONTEND_ORIGIN; provider data whose public-display terms are
unconfirmed stays off unless explicitly enabled.
"""

from __future__ import annotations

import os


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None or raw.strip() == "" else raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def is_production() -> bool:
    return os.environ.get("APP_ENV", "development").strip().lower() == "production"


def frontend_origins() -> list[str]:
    raw = os.environ.get("FRONTEND_ORIGIN", "")
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    if not is_production():
        origins += ["http://localhost:3000", "http://127.0.0.1:3000"]
    return list(dict.fromkeys(origins))


def enable_docs() -> bool:
    return _bool("ENABLE_DOCS", not is_production())


def admin_token() -> str | None:
    return os.environ.get("ADMIN_TOKEN", "").strip() or None


def precomputed_only() -> bool:
    """True: never fit a model, run the Monte Carlo or call a provider inside a request."""
    return _bool("PRECOMPUTED_ONLY", is_production())


def startup_catchup() -> bool:
    return _bool("STARTUP_CATCHUP", is_production())


def enable_api_football() -> bool:
    """API-Football's terms give no licence to publish its data on a public site (see DEPLOY.md), so
    it stays off in production unless explicitly enabled."""
    return _bool("ENABLE_API_FOOTBALL", not is_production())


def enable_football_data_org() -> bool:
    return _bool("ENABLE_FOOTBALL_DATA_ORG", True)


def rate_limit_per_minute() -> int:
    return _int("RATE_LIMIT_PER_MINUTE", 120)


def assistant_rate_limit_per_minute() -> int:
    return _int("ASSISTANT_RATE_LIMIT_PER_MINUTE", 6)


def assistant_rate_limit_per_hour() -> int:
    return _int("ASSISTANT_RATE_LIMIT_PER_HOUR", 40)


def max_question_chars() -> int:
    return _int("MAX_QUESTION_CHARS", 300)


def trusted_proxy_hops() -> int:
    """How many reverse proxies sit in front of the app (they append to X-Forwarded-For)."""
    return _int("TRUSTED_PROXY_HOPS", 1 if is_production() else 0)


def gemini_per_visitor_daily() -> int:
    return _int("GEMINI_PER_VISITOR_DAILY", 5)


def ip_hash_salt() -> str:
    return os.environ.get("IP_HASH_SALT", "").strip()
