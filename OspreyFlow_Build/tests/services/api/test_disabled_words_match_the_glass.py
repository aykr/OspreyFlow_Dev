"""The Glass tells a person disabled in this deployment so only when the Conduit's 401 carries
`principal_auth`'s own words, compared exactly (`apps/workspace/src/auth/disabledAccount.ts`;
ADR-148 Amendment 8). The two are in two languages: this holds them equal, so a change of words
on either side turns it red rather than quietly sending a disabled person to the misconfiguration
message."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from principal_auth import PrincipalResolutionError, StoredPerson, principal_from_claims
from tests.services.api.test_auth_entra_claims import _GOOD, BY_EXTENSION, entra_claims

GLASS = (
    Path(__file__).resolve().parents[4]
    / "OspreyFlow_Core/apps/workspace/src/auth/disabledAccount.ts"
)


def test_the_glass_names_the_conduits_disabled_words_exactly() -> None:
    found = re.search(r'CONDUIT_DISABLED_DETAIL = "([^"]+)"', GLASS.read_text(encoding="utf-8"))
    assert found
    with pytest.raises(PrincipalResolutionError) as refused:
        principal_from_claims(
            {**entra_claims(**_GOOD)}, BY_EXTENSION, StoredPerson(roles=(), disabled=True)
        )
    assert str(refused.value) == found.group(1)
