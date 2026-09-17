"""Deterministic team aliases with ambiguity safeguards."""

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum


def normalize_name(value: str) -> str:
    """Normalize spelling noise without applying unsafe fuzzy matching."""

    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    tokens = re.sub(r"[^a-z0-9]+", " ", ascii_name.lower()).strip().split()
    stop = {"fc", "cf", "afc", "sc", "club", "de", "the"}
    return " ".join(token for token in tokens if token not in stop)


DEFAULT_TEAM_ALIASES = {
    "man united": "manchester united",
    "man utd": "manchester united",
    "inter milan": "internazionale",
    "psg": "paris saint germain",
    "bayern munich": "bayern munchen",
}


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


@dataclass(frozen=True)
class IdentityCandidate:
    internal_id: str
    canonical_name: str
    provider_ids: dict[str, str] = field(default_factory=dict)
    context: str | None = None


@dataclass(frozen=True)
class Resolution:
    status: ResolutionStatus
    internal_id: str | None
    candidates: tuple[str, ...] = ()
    reason: str = ""


@dataclass
class IdentityResolver:
    """Resolve names through an auditable exact alias map."""

    aliases: dict[str, str] = field(default_factory=lambda: DEFAULT_TEAM_ALIASES.copy())
    candidates: list[IdentityCandidate] = field(default_factory=list)

    def resolve_team(self, name: str) -> str:
        normalized = normalize_name(name)
        return self.aliases.get(normalized, normalized)

    def add_alias(self, alias: str, canonical: str) -> None:
        alias_key = normalize_name(alias)
        canonical_key = normalize_name(canonical)
        existing = self.aliases.get(alias_key)
        if existing is not None and existing != canonical_key:
            raise ValueError(f"alias {alias!r} already maps to {existing!r}")
        self.aliases[alias_key] = canonical_key

    def register(self, candidate: IdentityCandidate) -> None:
        """Register an entity while rejecting provider-ID collisions."""

        for existing in self.candidates:
            for provider, identifier in candidate.provider_ids.items():
                if existing.provider_ids.get(provider) == identifier:
                    if existing.internal_id != candidate.internal_id:
                        raise ValueError(f"provider identity collision: {provider}:{identifier}")
                    return
        self.candidates.append(candidate)

    def resolve(
        self,
        name: str,
        *,
        provider: str | None = None,
        provider_id: str | None = None,
        context: str | None = None,
    ) -> Resolution:
        """Resolve by provider ID first, then conservative exact name and context."""

        if provider and provider_id:
            matches = [c for c in self.candidates if c.provider_ids.get(provider) == provider_id]
            if len(matches) == 1:
                return Resolution(
                    ResolutionStatus.RESOLVED, matches[0].internal_id, reason="provider-id"
                )
        canonical = self.resolve_team(name)
        matches = [c for c in self.candidates if self.resolve_team(c.canonical_name) == canonical]
        if context is not None:
            contextual = [c for c in matches if c.context in {None, context}]
            matches = contextual or matches
        if len(matches) == 1:
            return Resolution(
                ResolutionStatus.RESOLVED, matches[0].internal_id, reason="exact-name"
            )
        if len(matches) > 1:
            return Resolution(
                ResolutionStatus.AMBIGUOUS,
                None,
                tuple(item.internal_id for item in matches),
                "multiple conservative matches; manual review required",
            )
        return Resolution(ResolutionStatus.UNMATCHED, None, reason="no conservative match")
