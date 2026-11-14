"""The administrator fallback on Entra ID (`06_DECISIONS.md` ADR-148 Amendment 15; the audit's ruling 4c):
a value the claim mapping sources from the administrator (`{administrator: true}`) is the one Admin ›
People set for the person, never the token's, and a person with none set is refused in words.

At the resolver, through `resolve_principal` with the people store's stand-in (`FakePeople`, keyed by
tenant and object id as the real store is): the token cannot raise an administrator-sourced value by
carrying a claim for it, and an administrator cannot override a value the mapping reads from the token.
Synthetic values only (rule 9).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from services.api.auth import PrincipalResolutionError

from principal_auth import ClaimMapping, CodesSource, StoredPerson, ValueSource
from tests.conftest import sign_token
from tests.services.api.test_auth_entra_claims import (
    _GOOD,
    BY_EXTENSION,
    EXT,
    GLASS,
    OID,
    OTHER_TENANT,
    TENANT,
    _key,
    _resolver,
    entra_claims,
)

ADMIN_SET = ClaimMapping.model_validate(
    BY_EXTENSION.model_dump()
    | {"clearance": {"administrator": True}, "org_unit": {"administrator": True},
       "handling_codes": {"administrator": True}}  # fmt: skip
)


def _as(jwks_url: str, keypair, stored: StoredPerson | None, mapping: ClaimMapping = ADMIN_SET, *,
        tenant: str = TENANT, **claims: object):  # type: ignore[no-untyped-def]
    resolver = _resolver(jwks_url, mapping)
    if stored is not None:
        resolver.people.rows[(tenant, OID)] = stored
    return resolver, resolver.resolve(sign_token(_key(keypair), entra_claims(**claims)))


def test_the_values_are_the_ones_the_administrator_set(keypair, jwks_url) -> None:
    stored = StoredPerson(roles=("analyst",), disabled=False, clearance="OFFICIAL", org_unit="unit-2",
                          receivable_handling_codes=("P",))  # fmt: skip
    resolver, principal = _as(jwks_url, keypair, stored)
    assert (principal.clearance, principal.org_unit, principal.receivable_handling_codes) == ("OFFICIAL", "unit-2", ["P"])
    assert principal.roles == ["analyst"]
    # The token was not read for them, so Admin › People's record of what the token said holds nothing.
    seen = resolver.people.seen
    assert (seen.clearance, seen.org_unit, seen.receivable_handling_codes) == (None, None, None)


def test_a_token_cannot_raise_an_administrator_set_value_by_carrying_a_claim(keypair, jwks_url) -> None:
    stored = StoredPerson(roles=(), disabled=False, clearance="OFFICIAL", org_unit="unit-2", receivable_handling_codes=())
    # The mapping's own extension claims and the fixed names alike (`clearance`, Keycloak's): none is read.
    _, principal = _as(jwks_url, keypair, stored, **{f"{EXT}_clearance": "SECRET", f"{EXT}_orgUnit": "unit-1",
                                                      f"{EXT}_handlingCodes": ["R", "S"], "clearance": "SECRET",
                                                      "org_unit": "unit-1", "receivable_handling_codes": ["R"]})  # fmt: skip
    assert (principal.clearance, principal.org_unit, principal.receivable_handling_codes) == ("OFFICIAL", "unit-2", [])


def test_an_administrator_cannot_override_a_value_the_mapping_reads_from_the_token(keypair, jwks_url) -> None:
    stored = StoredPerson(roles=(), disabled=False, clearance="SECRET", org_unit="unit-9", receivable_handling_codes=("R",))
    _, principal = _as(jwks_url, keypair, stored, BY_EXTENSION, **_GOOD)
    assert (principal.clearance, principal.org_unit) == ("OFFICIAL", "unit-1")
    assert "R" not in principal.receivable_handling_codes


@pytest.mark.parametrize(
    ("unset", "words"),
    [("clearance", "clearance"), ("org_unit", "organisational unit"), ("receivable_handling_codes", "handling codes")],
)
def test_a_value_never_set_is_refused_in_words(keypair, jwks_url, unset: str, words: str) -> None:
    held = {"clearance": "OFFICIAL", "org_unit": "unit-2", "receivable_handling_codes": ("P",)} | {unset: None}
    with pytest.raises(PrincipalResolutionError, match=f"your {words} has not been set in this deployment"):
        _as(jwks_url, keypair, StoredPerson(roles=("analyst",), disabled=False, **held))  # type: ignore[arg-type]


def test_a_person_first_seen_has_nothing_set_and_is_refused(keypair, jwks_url) -> None:
    with pytest.raises(PrincipalResolutionError, match="has not been set"):
        _as(jwks_url, keypair, None)


def test_an_empty_set_of_codes_is_a_value_an_empty_clearance_is_not(keypair, jwks_url) -> None:
    _, principal = _as(jwks_url, keypair, StoredPerson((), False, "OFFICIAL", "unit-2", ()))
    assert principal.receivable_handling_codes == []
    with pytest.raises(PrincipalResolutionError, match="your clearance has not been set"):
        _as(jwks_url, keypair, StoredPerson((), False, "", "unit-2", ()))


def test_another_tenant_s_row_grants_nothing(keypair, jwks_url) -> None:
    """The store is keyed by tenant and object id: values set for the same object id in another
    tenant are never this person's."""
    with pytest.raises(PrincipalResolutionError, match="has not been set"):
        _as(jwks_url, keypair, StoredPerson(("osprey-admin",), False, "SECRET", "unit-1", ("R",)), tenant=OTHER_TENANT)


def test_a_disabled_person_is_refused_whatever_was_set(keypair, jwks_url) -> None:
    with pytest.raises(PrincipalResolutionError, match="disabled"):
        _as(jwks_url, keypair, StoredPerson((), True, "OFFICIAL", "unit-2", ()))


@pytest.mark.parametrize(
    "source",
    [{"administrator": True, "claim": "c"}, {"administrator": True, "groups": {"10000000-0000-4000-8000-000000000001": "OFFICIAL"}}, {}],
    ids=["administrator-and-claim", "administrator-and-groups", "none"],
)
def test_a_value_has_exactly_one_source(source: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="exactly one of"):
        ValueSource.model_validate(source)
    with pytest.raises(ValidationError, match="exactly one of"):
        CodesSource.model_validate({**source, **({"groups": {"10000000-0000-4000-8000-000000000001": ["P"]}} if "groups" in source else {})})


def test_the_administrator_source_is_an_entra_mapping_s_alone() -> None:
    """Keycloak's mapping names the fixed claims; an administrator's value there would be set where
    nothing reads it."""
    with pytest.raises(ValidationError):
        ClaimMapping(clearance=ValueSource(administrator=True))
    assert ClaimMapping(tenant_id=TENANT, client_id=GLASS, clearance=ValueSource(administrator=True)).clearance.administrator
