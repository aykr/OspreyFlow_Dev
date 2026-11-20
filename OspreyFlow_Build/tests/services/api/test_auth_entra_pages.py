"""The `pages` service's own sign-in reaches the Conduit (`06_DECISIONS.md` ADR-152 decision 11, row X1).

ADR-152 puts a server-rendered `pages` service beside the React workspace. It signs a person in as a
confidential OIDC client of its own and calls the Conduit with that person's bearer. On Entra ID the
Conduit admitted a token issued to the Glass's client (and Superset's, on two routes) and refused every
other client; so `pages` has its own registration, `ClaimMapping.pages_client_id`, and a token issued to
it is the person it names **on every route their rights allow** (`routes=None`, as the Glass's), held to
every check a Glass token is held to. On Keycloak nothing changes: any realm client whose token carries
the configured audience passes, and one without it is refused.

Rule 15: every case runs through the real `PrincipalResolver` with a real RS256 signature verified
against a JWKS served over loopback, the tokens shaped as Entra puts them (`azp`/`appid`, `tid`, `oid`,
`scp`); the refusals come from the claims, not from a fake. The Keycloak control is shown red by planting
the fault in `PrincipalResolver._verified_claims` (`verify_aud` forced off): a token without the audience
is then accepted and the control fails.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from services.api.auth import PrincipalResolutionError, PrincipalResolver

from principal_auth import SUPERSET_ROUTES, ClaimMapping, StoredPerson
from tests.conftest import default_claims, sign_token
from tests.services.api.test_auth import _config
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
PAGES = "77777777-aaaa-4bbb-8ccc-dddddddddddd"  # the `pages` service's own app registration


def _mapping(**registrations: str) -> ClaimMapping:
    """Validated, not `model_copy`'d: the validators are the safety (ClaimMapping's own docstring).
    Built per test, so one test's red does not hide the others."""
    return ClaimMapping.model_validate(BY_EXTENSION.model_dump() | registrations)


def _as(jwks_url: str, keypair, claims: dict[str, object], mapping: ClaimMapping | None = None):  # type: ignore[no-untyped-def]
    resolver = _resolver(jwks_url, mapping or _mapping(pages_client_id=PAGES))
    resolver.people.rows[(TENANT, OID)] = StoredPerson(roles=("analyst",), disabled=False)
    return resolver.resolve(sign_token(_key(keypair), claims))


# --- Keycloak: nothing changes in the Conduit, and the audience is what admits a realm client ---


@pytest.mark.parametrize(
    "claims",
    [
        default_claims(aud="account", azp="osprey-pages"),
        default_claims(azp="osprey-pages"),
    ],
    ids=["the-realm-default-audience", "no-audience-at-all"],
)
def test_a_token_from_a_realm_client_without_the_audience_mapper_is_refused(
    claims: dict[str, object], keypair, jwks_url
) -> None:
    """A realm client with no audience mapper (a token whose `aud` is the realm's default, or absent)
    is refused: the Conduit's audience check is what stops a token another client obtained. Sets
    `oidc_audience` itself, or the test would be vacuous (`verify_aud` is off when it is unset); the
    same token with the audience mapper resolves, so the refusal is the audience's."""
    resolver = PrincipalResolver(_config(jwks_url, oidc_audience="osprey-conduit"))
    with pytest.raises(PrincipalResolutionError):
        resolver.resolve(sign_token(_key(keypair), claims))
    mapped = {**claims, "aud": ["account", "osprey-conduit"]}
    assert resolver.resolve(sign_token(_key(keypair), mapped)).id == "analyst-1"


# --- Entra: the pages client's token ---


def test_a_token_issued_to_the_pages_client_is_the_person_on_every_route(keypair, jwks_url) -> None:
    principal = _as(jwks_url, keypair, entra_claims(**_GOOD, azp=PAGES))
    assert principal.id == OID and principal.roles == ["analyst"]
    assert (principal.clearance, principal.org_unit) == ("OFFICIAL", "unit-1")
    assert principal.routes is None  # every route their rights allow, as the Glass's


def test_a_v1_token_naming_the_pages_client_in_appid_is_the_same(keypair, jwks_url) -> None:
    claims = entra_claims(**_GOOD, appid=PAGES)
    claims.pop("azp")  # v1.0 names the client in `appid` alone
    assert _as(jwks_url, keypair, claims).routes is None


def test_the_glass_s_token_is_unchanged_and_superset_s_still_reaches_its_two_routes_only(
    keypair, jwks_url
) -> None:
    both = _mapping(pages_client_id=PAGES, superset_client_id=SUPERSET)
    glass = _as(jwks_url, keypair, entra_claims(**_GOOD), both)
    assert glass.routes is None and glass.id == OID
    superset = _as(jwks_url, keypair, entra_claims(**_GOOD, azp=SUPERSET), both)
    assert set(superset.routes or ()) == SUPERSET_ROUTES
    pages = _as(jwks_url, keypair, entra_claims(**_GOOD, azp=PAGES), both)
    assert pages.routes is None


@pytest.mark.parametrize(
    ("claims", "why"),
    [
        (entra_claims(**_GOOD, azp=PAGES, appid=GLASS), "Glass's client"),
        (entra_claims(**_GOOD, azp=PAGES, appid=SUPERSET), "Glass's client"),
        (entra_claims(**_GOOD, azp=PAGES, tid=OTHER_TENANT), "tenant"),
        (entra_claims(**_GOOD, azp=PAGES, scp="User.Read"), "scope"),
        (entra_claims(**_GOOD, azp=PAGES, scp=None, idtyp="app"), "app-only"),
        (entra_claims(**_GOOD, azp=PAGES, acct=1), "guest"),
        (entra_claims(**_GOOD, azp=PAGES, aud=OTHER_APP), "token rejected"),
    ],
    ids=["two-clients", "pages-and-superset", "another-tenant", "not-this-api-s-scope", "app-only", "guest",
         "another-audience"],
)  # fmt: skip
def test_the_pages_client_s_token_is_held_to_every_check_a_glass_token_is(
    claims: dict[str, object], why: str, keypair, jwks_url
) -> None:
    with pytest.raises(PrincipalResolutionError, match=why):
        _as(jwks_url, keypair, claims)


def test_without_the_pages_client_named_its_token_is_refused(keypair, jwks_url) -> None:
    with pytest.raises(PrincipalResolutionError, match="Glass's client"):
        _as(jwks_url, keypair, entra_claims(**_GOOD, azp=PAGES), BY_EXTENSION)
    # Naming Superset's registration does not admit it either: one token, one registration.
    only_superset = _mapping(superset_client_id=SUPERSET)
    with pytest.raises(PrincipalResolutionError, match="Glass's client"):
        _as(jwks_url, keypair, entra_claims(**_GOOD, azp=PAGES), only_superset)


@pytest.mark.parametrize("with_superset", [False, True], ids=["pages-named", "pages-and-superset-named"])
def test_a_third_client_is_still_refused(with_superset: bool, keypair, jwks_url) -> None:
    mapping = _mapping(pages_client_id=PAGES, **({"superset_client_id": SUPERSET} if with_superset else {}))
    with pytest.raises(PrincipalResolutionError, match="Glass's client"):
        _as(jwks_url, keypair, entra_claims(**_GOOD, azp=OTHER_APP), mapping)


# --- the pages client's registration is its own, as Superset's is ---


@pytest.mark.parametrize(
    "pages",
    [GLASS, CLIENT_ID, SUPERSET, "not-a-guid"],
    ids=["the-glass", "the-api", "superset", "not-a-guid"],
)
def test_the_pages_client_s_registration_is_its_own(pages: str) -> None:
    """Named as the Glass's, every Glass token would be read as the pages service's; as the API's, it
    would be the audience itself; as Superset's, one token would mean two route sets. The control: a
    distinct GUID in the same mapping is valid, so the refusal is the validator's, not the field's absence."""
    assert _mapping(api_client_id=CLIENT_ID, superset_client_id=SUPERSET, pages_client_id=PAGES)
    raw = BY_EXTENSION.model_dump() | {
        "api_client_id": CLIENT_ID,
        "superset_client_id": SUPERSET,
        "pages_client_id": pages,
    }
    with pytest.raises(ValidationError, match="pages_client_id"):
        ClaimMapping.model_validate(raw)


def test_the_pages_client_s_registration_needs_an_entra_mapping() -> None:
    assert _mapping(pages_client_id=PAGES).pages_client_id == PAGES  # control: valid with the tenant
    with pytest.raises(ValidationError, match="pages_client_id"):
        ClaimMapping(pages_client_id=PAGES)


def test_an_unset_pages_client_leaves_every_existing_mapping_valid() -> None:
    assert BY_EXTENSION.pages_client_id is None
    assert ClaimMapping().pages_client_id is None
