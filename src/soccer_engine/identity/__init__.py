"""Cross-provider identity resolution."""

from soccer_engine.identity.resolver import (
    IdentityCandidate,
    IdentityResolver,
    Resolution,
    ResolutionStatus,
    normalize_name,
)

__all__ = [
    "IdentityCandidate",
    "IdentityResolver",
    "Resolution",
    "ResolutionStatus",
    "normalize_name",
]
