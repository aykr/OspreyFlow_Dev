"""A sign-in refused with words the person can act on carries a stable tag beside them in its 401 (`error`):
access_not_set (ADR-148 Amendment 15), guest_not_admitted (Amendment 17) and token_version (Amendment 18), so the
Glass shows those words and no others (`apps/workspace/src/auth/refusalWords.ts`). Every other refusal keeps
FastAPI's plain `{"detail": …}`; the disabled account's 401 is unchanged (the Glass matches its words exactly).

Each refusal is the real resolver's, from a real signed token, through the real app's `GET /v1/me`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.app import app
from services.api.auth import PrincipalResolver

from principal_auth import GUESTS_NOT_ADMITTED_WORDS, PrincipalResolutionError, StoredPerson
from tests.conftest import sign_token
from tests.services.api.test_auth import _config
from tests.services.api.test_auth_entra_administrator_access import ADMIN_SET
from tests.services.api.test_auth_entra_claims import _GOOD, BY_EXTENSION, CLIENT_ID, OID, TENANT, FakePeople, entra_claims
from tests.services.api.test_auth_entra_token_version import V2, _v1_claims

DISABLED = "this account is disabled in this deployment: ask an administrator"


def _through_the_app(resolver: PrincipalResolver, token: str) -> Any:
    held = getattr(app.state, "principal_resolver", None)
    app.state.principal_resolver = resolver
    try:
        return TestClient(app).get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.state.principal_resolver = held


def _resolver(jwks_url: str, mapping: Any = BY_EXTENSION, people: FakePeople | None = None) -> PrincipalResolver:
    return PrincipalResolver(_config(jwks_url, oidc_issuer=V2, oidc_audience=CLIENT_ID), claim_mapping=mapping,
                             role_source=people or FakePeople(), role_lookup_timeout_seconds=0.2)  # fmt: skip


def test_a_value_the_administrator_has_not_set_is_tagged_access_not_set(keypair, jwks_url) -> None:  # type: ignore[no-untyped-def]
    people = FakePeople()
    people.rows[(TENANT, OID)] = StoredPerson(roles=("analyst",), disabled=False, clearance=None, org_unit="unit-2",
                                              receivable_handling_codes=("P",))  # fmt: skip
    answer = _through_the_app(_resolver(jwks_url, ADMIN_SET, people), sign_token(keypair[0], entra_claims()))
    assert answer.status_code == 401 and answer.json()["error"] == "access_not_set"
    assert answer.json()["detail"].startswith("your clearance has not been set in this deployment")


def test_a_guest_while_guests_are_not_admitted_is_tagged_guest_not_admitted(keypair, jwks_url) -> None:  # type: ignore[no-untyped-def]
    answer = _through_the_app(_resolver(jwks_url), sign_token(keypair[0], entra_claims(**_GOOD, acct=1)))
    assert answer.status_code == 401 and answer.json() == {"detail": GUESTS_NOT_ADMITTED_WORDS, "error": "guest_not_admitted"}


def test_a_token_of_the_other_version_is_tagged_token_version(keypair, jwks_url) -> None:  # type: ignore[no-untyped-def]
    answer = _through_the_app(_resolver(jwks_url), sign_token(keypair[0], _v1_claims()))
    assert answer.status_code == 401 and answer.json()["error"] == "token_version"
    assert "requestedAccessTokenVersion to 2" in answer.json()["detail"]


@pytest.mark.parametrize("which", ["another-key", "disabled"])
def test_every_other_refusal_carries_no_tag(keypair, jwks_url, which: str) -> None:  # type: ignore[no-untyped-def]
    """A refusal with no words to act on, and the disabled account (whose words the Glass already matches
    exactly), answer as before: `{"detail": …}` alone."""
    people = FakePeople()
    if which == "another-key":
        token = sign_token(rsa.generate_private_key(public_exponent=65537, key_size=2048), entra_claims(**_GOOD))
    else:
        people.rows[(TENANT, OID)] = StoredPerson(roles=("analyst",), disabled=True)
        token = sign_token(keypair[0], entra_claims(**_GOOD))
    answer = _through_the_app(_resolver(jwks_url, BY_EXTENSION, people), token)
    assert answer.status_code == 401 and "error" not in answer.json()
    if which == "disabled":
        assert answer.json() == {"detail": DISABLED}


def _tags_raised() -> set[str]:
    def every(cls: type) -> list[type]:
        return [cls, *(c for sub in cls.__subclasses__() for c in every(sub))]

    return {c.error for c in every(PrincipalResolutionError) if c.error is not None}


def test_the_glass_shows_exactly_the_tags_the_conduit_sends() -> None:
    """A tag spelt one way here and another in the Glass would pass both tiers' own tests and show the general
    words: the Glass's list (`apps/workspace/src/auth/refusalWords.ts`) is held to the Conduit's tags."""
    source = (Path(__file__).resolve().parents[4] / "OspreyFlow_Core/apps/workspace/src/auth/refusalWords.ts").read_text()
    listed = re.search(r"ACTIONABLE_REFUSALS[^=]*=\s*\[([^\]]*)\]", source)
    assert listed is not None
    assert set(re.findall(r'"([a-z_]+)"', listed.group(1))) == _tags_raised() == {
        "access_not_set", "token_version", "guest_not_admitted"}
