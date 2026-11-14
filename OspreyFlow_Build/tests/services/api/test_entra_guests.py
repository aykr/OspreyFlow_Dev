"""ADR-148 Amendment 17 (the ADR-148 audit's finding 5; the owner's ruling "4b: guests behind a setting"): a guest
(B2B) account on Entra ID signs in only while the deployment admits guests, a setting off by default that an
administrator of people switches in Admin › People. Admitted, a guest is any person: the same mapping, the same
clearance, unit and codes from their token, or set in People where the deployment sets them
(Amendment 15), never more. Not admitted, the refusal says so in true words, and nothing
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
    EXT,
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


def test_an_admitted_guest_through_superset_s_client_is_held_to_superset_s_routes(keypair, jwks_url) -> None:
    """Never more (the lane review, should 11): admitted, a guest's Superset token is still Superset's two routes."""
    from principal_auth import SUPERSET_ROUTES, ClaimMapping

    from tests.services.api.test_auth_entra_superset import SUPERSET

    mapping = ClaimMapping.model_validate(BY_EXTENSION.model_dump() | {"superset_client_id": SUPERSET})
    people = FakePeople()
    people.admit_guests = True
    principal = _resolve(_resolver(jwks_url, people, mapping),
                         sign_token(_key(keypair), entra_claims(**_GOOD, azp=SUPERSET, acct=1)))  # fmt: skip
    assert set(principal.routes or ()) == SUPERSET_ROUTES


def test_a_run_as_a_guest_owner_whose_setting_cannot_be_read_is_the_store_unread_never_admitted(jwks_url) -> None:
    """The lane review, should 8: the owner path's unread is `OwnerRecordUnavailable`, which every run caller words."""
    from principal_auth import OwnerRecordUnavailable

    people = FakePeople()
    people.owners[(TENANT, OID)] = _owner(guest=True)
    people.admit_guests = True
    people.guest_fail = ConnectionError("down")
    with pytest.raises(OwnerRecordUnavailable):
        asyncio.run(_resolver(jwks_url, people).resolve_for_owner_detailed(OID))


def test_the_one_construction_path_refuses_a_guest_s_claims_unless_told_they_were_admitted() -> None:
    """ADR-148 decision 9 (the lane review, should 5): `principal_from_claims` itself refuses a guest's claims, so a
    caller that never asked the setting cannot let one in; told they were admitted, the principal is a member's."""
    from principal_auth import StoredPerson, principal_from_claims

    stored = StoredPerson(roles=("analyst",), disabled=False)
    with pytest.raises(PrincipalResolutionError) as refused:
        principal_from_claims(entra_claims(**_GOOD, acct=1), BY_EXTENSION, stored)
    assert str(refused.value) == GUESTS_NOT_ADMITTED_WORDS
    guest = principal_from_claims(entra_claims(**_GOOD, acct=1), BY_EXTENSION, stored, guest_admitted=True)
    member = principal_from_claims(entra_claims(**_GOOD), BY_EXTENSION, stored)
    assert guest.model_dump() == member.model_dump()



#: What the token says and what People holds, different in each value, so each principal shows where its value came
#: from. The mapping's field name, the principal's, the token's and People's (ADR-148 Amendment 15).
_SET_HERE = [
    ("clearance", "clearance", {f"{EXT}_clearance": "OFFICIAL-SENSITIVE"}, {"clearance": "OFFICIAL"}),
    ("org_unit", "org_unit", {f"{EXT}_orgUnit": "unit-9"}, {"org_unit": "unit-2"}),
    ("handling_codes", "receivable_handling_codes", {f"{EXT}_handlingCodes": ["R"]},
     {"receivable_handling_codes": ("P",)}),
]  # fmt: skip
_WORDS = {"clearance": "clearance", "org_unit": "organisational unit", "handling_codes": "handling codes"}


@pytest.mark.parametrize(("field", "attr", "token_says", "people_holds"), _SET_HERE, ids=[f for f, *_ in _SET_HERE])
def test_an_admitted_guest_takes_a_value_the_deployment_sets_from_people_never_from_their_token(
    keypair, jwks_url, field, attr, token_says, people_holds
) -> None:
    """ADR-148 Amendment 17 point 3, with Amendment 15: admitted, a guest is any person, so where the mapping sources a
    value from the administrator a guest's is the one set in People (their token's claim is not read), the rest come
    from their token, and with it never set the guest is refused in a member's words. Through `resolve_principal`, the
    path a sign-in takes, for each value the mapping can set here. The Guests form's words rest on this."""
    from principal_auth import ClaimMapping, StoredPerson

    mapping = ClaimMapping.model_validate(BY_EXTENSION.model_dump() | {field: {"administrator": True}})
    claims = {**_GOOD, f"{EXT}_handlingCodes": ["S"], **token_says}
    people = FakePeople()
    people.admit_guests = True
    others = {"clearance": None, "org_unit": None, "receivable_handling_codes": None}
    people.rows[(TENANT, OID)] = StoredPerson(roles=("analyst",), disabled=False, **(others | people_holds))
    guest = _resolve(_resolver(jwks_url, people, mapping), sign_token(_key(keypair), entra_claims(**claims, acct=1)))
    held = people_holds[attr]
    assert getattr(guest, attr) == (list(held) if isinstance(held, tuple) else held)
    # The rest from the token: one of them, against what the token says.
    assert (guest.org_unit if field == "clearance" else guest.clearance) == ("unit-1" if field == "clearance" else "OFFICIAL")
    member = _resolve(_resolver(jwks_url, people, mapping), sign_token(_key(keypair), entra_claims(**claims)))
    assert guest.model_dump() == member.model_dump()

    people.rows[(TENANT, OID)] = StoredPerson(roles=("analyst",), disabled=False)
    with pytest.raises(PrincipalResolutionError) as as_guest:
        _resolve(_resolver(jwks_url, people, mapping), sign_token(_key(keypair), entra_claims(**claims, acct=1)))
    people.rows[(TENANT, OID)] = StoredPerson(roles=("analyst",), disabled=False)
    with pytest.raises(PrincipalResolutionError) as as_member:
        _resolve(_resolver(jwks_url, people, mapping), sign_token(_key(keypair), entra_claims(**claims)))
    assert str(as_guest.value) == str(as_member.value)
    assert _WORDS[field] in str(as_guest.value)
