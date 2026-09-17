import pytest

from soccer_engine.identity import IdentityResolver


def test_team_aliases_resolve_to_same_identity() -> None:
    resolver = IdentityResolver()
    assert resolver.resolve_team("Man United") == resolver.resolve_team("Manchester United FC")


def test_alias_conflicts_are_rejected() -> None:
    resolver = IdentityResolver()
    with pytest.raises(ValueError):
        resolver.add_alias("Man United", "Manchester City")
