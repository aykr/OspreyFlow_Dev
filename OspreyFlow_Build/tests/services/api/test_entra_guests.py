"""ADR-148 Amendment 17 (the ADR-148 audit's finding 5; the owner's ruling "4b: guests behind a setting"): a guest
(B2B) account on Entra ID signs in only while the deployment admits guests, a setting off by default that an
administrator of people switches in Admin › People. Admitted, a guest is any person: the same mapping, the same
clearance, unit and codes from their token, never more. Not admitted, the refusal says so in true words, and nothing
is recorded of them. Switched off again, a guest already recorded is refused everywhere a person is read without a
token: an open socket's standing and a run acting as them.

The store is `FakePeople` (`test_auth_entra_claims.py`), which refuses as `EntraPeopleStore` does (rule 15): the
setting off when never set, a failure raised. `test_entra_people_live.py` holds the real store to the same.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from services.api.auth import PrincipalResolutionError, PrincipalResolver

from principal_auth import (
    GUESTS_NOT_ADMITTED_WORDS,
    OwnerNotHeld,
    PrincipalLookupUnavailable,
    PrincipalRevoked,
    StoredOwner,
)
from tests.conftest import sign_token
from tests.services.api.test_auth_entra_claims import (
    _GOOD,
    BY_EXTENSION,
    BY_GROUPS,
    G_CODE_R,
    G_OFFICIAL,
    G_UNIT_1,
    OID,
    OTHER_TENANT,
    TENANT,
    FakePeople,
    _entra_config,
    _key,
    entra_claims,
)

#: The two shapes a guest's token takes (Microsoft's documentation; not yet tried against a real guest, Am 17).
GUEST_SHAPES = [{"acct": 1}, {"acct": "1"}, {"idp": f"https://sts.windows.net/{OTHER_TENANT}/"}]
GUEST_IDS = ["acct", "acct-text", "idp-other"]


def _resolver(jwks_url: str, people: FakePeople, mapping=BY_EXTENSION) -> PrincipalResolver:  # type: ignore[no-untyped-def]
    return PrincipalResolver(_entra_config(jwks_url), claim_mapping=mapping, role_source=people,
                             role_lookup_timeout_seconds=0.2)  # fmt: skip


def _resolve(resolver: PrincipalResolver, token: str):  # type: ignore[no-untyped-def]
    return asyncio.run(resolver.resolve_principal(token))


@pytest.mark.parametrize("guest", GUEST_SHAPES, ids=GUEST_IDS)
def test_a_guest_is_refused_in_true_words_while_guests_are_not_admitted_and_nothing_is_recorded(
    keypair, jwks_url, guest
) -> None:
    people = FakePeople()
    with pytest.raises(PrincipalResolutionError) as refused:
        _resolve(_resolver(jwks_url, people), sign_token(_key(keypair), entra_claims(**_GOOD, **guest)))
    assert str(refused.value) == GUESTS_NOT_ADMITTED_WORDS
    assert "guest" in str(refused.value) and "Admin › People" in str(refused.value)
    assert people.rows == {}  # never recorded


@pytest.mark.parametrize("guest", GUEST_SHAPES, ids=GUEST_IDS)
def test_an_admitted_guest_signs_in_as_a_member_with_the_same_claims_does(keypair, jwks_url, guest) -> None:
    """Rule 3 both ways: the guest's principal is the member's with the same token claims, field for field."""
    people = FakePeople()
    people.admit_guests = True
    member = _resolve(_resolver(jwks_url, people), sign_token(_key(keypair), entra_claims(**_GOOD)))
    people.rows.clear()
    admitted = _resolve(_resolver(jwks_url, people),
                        sign_token(_key(keypair), entra_claims(**_GOOD, **guest)))  # fmt: skip
    assert admitted.model_dump() == member.model_dump()
    assert people.seen.guest is True


def test_an_admitted_guest_is_mapped_by_groups_as_a_member_is_and_given_no_group_the_token_lacks(
    keypair, jwks_url
) -> None:
    people = FakePeople()
    people.admit_guests = True
    claims = {"groups": [G_OFFICIAL, G_UNIT_1, G_CODE_R]}
    member = _resolve(_resolver(jwks_url, people, BY_GROUPS), sign_token(_key(keypair), entra_claims(**claims)))
    guest = _resolve(_resolver(jwks_url, people, BY_GROUPS),
                     sign_token(_key(keypair), entra_claims(**claims, acct=1)))  # fmt: skip
    assert (guest.clearance, guest.org_unit, guest.receivable_handling_codes) == (
        member.clearance, member.org_unit, member.receivable_handling_codes)  # fmt: skip
    with pytest.raises(PrincipalResolutionError, match="clearance"):
        _resolve(_resolver(jwks_url, people, BY_GROUPS),
                 sign_token(_key(keypair), entra_claims(groups=[G_UNIT_1], acct=1)))  # fmt: skip


def test_a_member_is_never_asked_about_the_setting(keypair, jwks_url) -> None:
    people = FakePeople()
    people.guest_fail = RuntimeError("the setting cannot be read")
    assert _resolve(_resolver(jwks_url, people), sign_token(_key(keypair), entra_claims(**_GOOD))).id == OID


def test_a_setting_that_cannot_be_read_is_unavailable_never_admitted(keypair, jwks_url) -> None:
    people = FakePeople()
    people.admit_guests = True
    people.guest_fail = ConnectionError("down")
    with pytest.raises(PrincipalLookupUnavailable):
        _resolve(_resolver(jwks_url, people), sign_token(_key(keypair), entra_claims(**_GOOD, acct=1)))
    assert people.rows == {}


def test_a_setting_too_slow_to_answer_is_unavailable_within_the_bound(keypair, jwks_url) -> None:
    people = FakePeople()
    people.admit_guests = True
    people.guest_delay = 1.0
    with pytest.raises(PrincipalLookupUnavailable):
        _resolve(_resolver(jwks_url, people), sign_token(_key(keypair), entra_claims(**_GOOD, acct=1)))


def test_a_guest_already_recorded_is_refused_again_once_guests_are_no_longer_admitted(keypair, jwks_url) -> None:
    people = FakePeople()
    people.admit_guests = True
    resolver = _resolver(jwks_url, people)
    token = sign_token(_key(keypair), entra_claims(**_GOOD, acct=1))
    assert _resolve(resolver, token).id == OID
    people.admit_guests = False
    with pytest.raises(PrincipalResolutionError, match="guest"):
        _resolve(resolver, token)


# --- read without a token: a run as its owner (Amendment 16) -------------------------------------


def _owner(guest: bool) -> StoredOwner:
    return StoredOwner(roles=("analyst",), disabled=False, clearance="OFFICIAL", org_unit="unit-1",
                       receivable_handling_codes=(), access_read_at=datetime.now(UTC) - timedelta(hours=1),
                       guest=guest)  # fmt: skip


def test_a_run_as_a_guest_owner_is_refused_once_guests_are_no_longer_admitted(jwks_url) -> None:
    people = FakePeople()
    people.owners[(TENANT, OID)] = _owner(guest=True)
    people.admit_guests = True
    resolver = _resolver(jwks_url, people)
    assert asyncio.run(resolver.resolve_for_owner_detailed(OID)).id == OID
    people.admit_guests = False
    with pytest.raises(PrincipalRevoked) as refused:
        asyncio.run(resolver.resolve_for_owner_detailed(OID))
    assert not isinstance(refused.value, OwnerNotHeld)


def test_a_run_as_a_member_owner_never_asks_the_setting(jwks_url) -> None:
    people = FakePeople()
    people.owners[(TENANT, OID)] = _owner(guest=False)
    people.guest_fail = RuntimeError("never asked")
    assert asyncio.run(_resolver(jwks_url, people).resolve_for_owner_detailed(OID)).id == OID
