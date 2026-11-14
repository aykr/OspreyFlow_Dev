"""Superset's sign-in reads who signed in from the Conduit (`06_DECISIONS.md` ADR-148 Amendment 9).

A person signs in to Superset, Superset's own app registration in the client's tenant; Entra gives
Superset a delegated token for this API's scope, issued to Superset's client (`azp`). The Conduit
admits that token as the person, with their stored roles, to `GET /v1/me` and `/v1/me/rights` alone
(`SUPERSET_ROUTES`, held on the principal and refused elsewhere by the gate, `test_route_gate.py`),
so Superset gives them its role from their rights and can do nothing else as them.

Rule 15: the tokens are shaped as Entra issues a delegated v2.0 token for this API to another
client (the person's `oid`, `scp`, `azp` Superset's); every check a Glass token is held to holds for
Superset's (tenant, person, scope, guest); a client neither the Glass's nor Superset's is refused as
before.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from services.api.auth import PrincipalResolutionError

from principal_auth import SUPERSET_ROUTES, ClaimMapping, StoredPerson
from tests.conftest import sign_token
from tests.services.api.test_auth_entra_claims import (
    _GOOD,
    BY_EXTENSION,
    CLIENT_ID,
    GLASS,
    OID,
    OTHER_APP,
    OTHER_TENANT,
    TENANT,
    _key,
    _resolver,
    entra_claims,
)

SUPERSET = "99999999-aaaa-4bbb-8ccc-dddddddddddd"  # Superset's own app registration
#: Validated, not `model_copy`'d: the validators are the safety (ClaimMapping's own docstring).
WITH_SUPERSET = ClaimMapping.model_validate(BY_EXTENSION.model_dump() | {"superset_client_id": SUPERSET})


def _as(jwks_url: str, keypair, claims: dict[str, object], mapping: ClaimMapping = WITH_SUPERSET):  # type: ignore[no-untyped-def]
    resolver = _resolver(jwks_url, mapping)
    resolver.people.rows[(TENANT, OID)] = StoredPerson(roles=("analyst",), disabled=False)
    return resolver.resolve(sign_token(_key(keypair), claims))


def test_a_person_s_token_issued_to_superset_is_them_on_superset_s_two_routes_alone(keypair, jwks_url) -> None:
    principal = _as(jwks_url, keypair, entra_claims(**_GOOD, azp=SUPERSET))
    assert principal.id == OID and principal.roles == ["analyst"]
    assert (principal.clearance, principal.org_unit) == ("OFFICIAL", "unit-1")
    assert set(principal.routes or ()) == SUPERSET_ROUTES == {"GET /v1/me", "GET /v1/me/rights"}


def test_the_glass_s_token_is_still_every_route_its_rights_allow(keypair, jwks_url) -> None:
    principal = _as(jwks_url, keypair, entra_claims(**_GOOD))
    assert principal.routes is None and principal.id == OID


@pytest.mark.parametrize(
    ("claims", "why"),
    [
        (entra_claims(**_GOOD, azp=OTHER_APP), "Glass's client"),
        (entra_claims(**_GOOD, azp=SUPERSET, appid=GLASS), "Glass's client"),
        (entra_claims(**_GOOD, azp=SUPERSET, tid=OTHER_TENANT), "tenant"),
        (entra_claims(**_GOOD, azp=SUPERSET, scp="User.Read"), "scope"),
        (entra_claims(**_GOOD, azp=SUPERSET, scp=None, idtyp="app"), "app-only"),
        (entra_claims(**_GOOD, azp=SUPERSET, acct=1), "guest"),
    ],
    ids=["another-client", "two-clients", "another-tenant", "not-this-api-s-scope", "app-only", "guest"],
)  # fmt: skip
def test_superset_s_token_is_held_to_every_check_a_glass_token_is(
    claims: dict[str, object], why: str, keypair, jwks_url
) -> None:
    with pytest.raises(PrincipalResolutionError, match=why):
        _as(jwks_url, keypair, claims)


def test_without_superset_s_registration_named_its_token_is_another_client_s(keypair, jwks_url) -> None:
    with pytest.raises(PrincipalResolutionError, match="Glass's client"):
        _as(jwks_url, keypair, entra_claims(**_GOOD, azp=SUPERSET), BY_EXTENSION)


@pytest.mark.parametrize("superset", [GLASS, CLIENT_ID, "not-a-guid"], ids=["the-glass", "the-api", "not-a-guid"])
def test_superset_s_registration_is_its_own(superset: str) -> None:
    """Named as the Glass's, every Glass token would be held to Superset's two routes; as the API's,
    it would be a client that is the audience itself."""
    raw = BY_EXTENSION.model_dump() | {"api_client_id": CLIENT_ID, "superset_client_id": superset}
    with pytest.raises(ValidationError, match="superset_client_id"):
        ClaimMapping.model_validate(raw)


def test_superset_s_registration_needs_an_entra_mapping() -> None:
    with pytest.raises(ValidationError, match="superset_client_id"):
        ClaimMapping(superset_client_id=SUPERSET)
