"""Sign-in claims from Entra ID, mapped by settings — `06_DECISIONS.md` ADR-148 decision 9 (P10).

ADR-148 decision 9: "The claims `principal_auth` needs are **mapped, not assumed**: the profile
names, for each of clearance, organisational unit and handling codes, the Entra claim that carries
it (a directory extension attribute) or a table from Entra group to value. One claims-construction
path stays (`principal_auth`'s own rule); only its source names become settings."

**Every case runs through the real `PrincipalResolver.resolve`** — a real RS256 signature, a real
JWKS document served over loopback HTTP (`tests/conftest.py`), PyJWT's own issuer, audience and
expiry checks — never through the mapping function alone, so an access check that lives in the
resolver (CLAUDE.md rules 3 and 4) is what each refusal exercises.

**The tokens are shaped as Entra ID v2.0 issues them**, and every value in them is synthetic (rule
9): the tenant, client, object and group ids below are made-up GUIDs, and the directory extension
attribute names follow Entra's `extension_<application id without hyphens>_<name>` form for a
made-up application. **The stand-in refuses what Entra's tokens are refused for** (CLAUDE.md rule
15's second worked example): a token with no `oid` or no `tid`, another tenant's `tid`, the wrong
issuer or audience, an expired token or one with no expiry, and a group overage (Entra omits
`groups` and points to Graph instead, past 200 groups in a JWT) — each refused, never read as "no
groups" — and an app-only token (no delegated `scp`).

**Shaped from Microsoft's documentation, not measured.** No real tenant's token has been through
this code (rule 15): the claim names, the v2.0 issuer, a multi-valued extension attribute arriving
as a JSON list and the overage forms are as documented, and are assumptions until the client's
tenant issues a token in their development namespace (P10 part 2's live check).

**Decided here (logged in `process/lanes/admin/SERVER_LOG.md`):** groups granting more than one
clearance, or more than one organisational unit, are **refused**, not resolved to the lowest —
`principal_auth` holds no marking scheme to order clearances by, and a person in two clearance
groups is a directory error for the operator to see, not one to guess past.
"""

from __future__ import annotations

import ast
import asyncio
import re
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError
from services.api.auth import (
    PrincipalExchangeUnavailable,
    PrincipalResolutionError,
    PrincipalResolver,
)
from services.api.config import ApiConfig

from principal_auth import (
    ClaimMapping,
    CodesSource,
    PrincipalLookupUnavailable,
    SeenPerson,
    StoredPerson,
    ValueSource,
)
from tests.conftest import (
    TOKEN_EXCHANGE_CLIENT_ID,
    TOKEN_EXCHANGE_CLIENT_SECRET,
    TokenExchangeRegistry,
    default_claims,
    sign_token,
)
from tests.services.api.test_auth import _config

# --- synthetic Entra identifiers (rule 9: none of these is a real tenant, app, person or group) ---

TENANT = "00000000-1111-4222-8333-444444444444"
OTHER_TENANT = "99999999-8888-4777-8666-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"  # this API's app registration (the audience)
GLASS = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"  # the Glass's app registration (`azp`)
OTHER_APP = "cccccccc-dddd-4eee-8fff-000000000000"
OID = "50000000-0000-4000-8000-000000000001"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
EXT = "extension_0123456789abcdef0123456789abcdef"  # an app's id without hyphens, made up

G_OFFICIAL = "10000000-0000-4000-8000-000000000001"
G_SENSITIVE = "10000000-0000-4000-8000-000000000002"
G_UNIT_1 = "20000000-0000-4000-8000-000000000001"
G_UNIT_2 = "20000000-0000-4000-8000-000000000002"
G_CODE_R = "30000000-0000-4000-8000-000000000001"
G_CODES_ST = "30000000-0000-4000-8000-000000000002"
G_UNMAPPED = "40000000-0000-4000-8000-000000000001"


def entra_claims(**overrides: object) -> dict[str, object]:
    """An Entra ID v2.0 access token's claims for a person, as Entra shapes them."""
    now = int(time.time())
    base: dict[str, object] = {
        "aud": CLIENT_ID,
        "iss": ISSUER,
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
        "ver": "2.0",
        "tid": TENANT,
        "oid": OID,
        "azp": GLASS,
        "sub": "pairwise-subject-AbCdEf0123456789",
        "name": "Synthetic Analyst",
        "preferred_username": "synthetic.analyst@example.test",
        "scp": "openid access_as_user",
        "roles": ["analyst"],
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not _ABSENT}


_ABSENT = object()

#: Each principal claim from a directory extension attribute.
BY_EXTENSION = ClaimMapping(
    tenant_id=TENANT,
    client_id=GLASS,
    clearance=ValueSource(claim=f"{EXT}_clearance"),
    org_unit=ValueSource(claim=f"{EXT}_orgUnit"),
    handling_codes=CodesSource(claim=f"{EXT}_handlingCodes"),
)

#: Each principal claim from a table of Entra groups.
BY_GROUPS = ClaimMapping(
    tenant_id=TENANT,
    client_id=GLASS,
    clearance=ValueSource(groups={G_OFFICIAL: "OFFICIAL", G_SENSITIVE: "OFFICIAL-SENSITIVE"}),
    org_unit=ValueSource(groups={G_UNIT_1: "unit-1", G_UNIT_2: "unit-2"}),
    handling_codes=CodesSource(groups={G_CODE_R: ["R"], G_CODES_ST: ["S", "T"]}),
)

#: A named claim and a group table in one mapping.
MIXED = ClaimMapping(
    tenant_id=TENANT,
    client_id=GLASS,
    clearance=ValueSource(claim=f"{EXT}_clearance"),
    org_unit=ValueSource(groups={G_UNIT_1: "unit-1", G_UNIT_2: "unit-2"}),
    handling_codes=CodesSource(groups={G_CODE_R: ["R"]}),
)


def _entra_config(jwks_url: str) -> ApiConfig:
    return _config(jwks_url, oidc_issuer=ISSUER, oidc_audience=CLIENT_ID)


class FakePeople:
    """Stands in for `services/api/entra_people.py`'s store, and refuses as it does (rule 15): keyed
    by tenant **and** object id, a person not yet seen recorded with no roles, and a failure raised,
    never answered as "no roles". `test_entra_people_live.py` holds the real store to the same."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], StoredPerson] = {}
        self.calls: list[tuple[str, str]] = []
        self.fail: Exception | None = None
        self.delay = 0.0

    async def person(self, tenant_id: str, oid: str, seen: SeenPerson) -> StoredPerson:
        self.calls.append((tenant_id, oid))
        self.seen = seen
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        return self.rows.setdefault((tenant_id, oid), StoredPerson(roles=(), disabled=False))


class _EntraResolver:
    """The resolver as the Conduit calls it on Entra (`resolve_principal`, its stored person read
    from `people`), driven from a plain test."""

    def __init__(self, jwks_url: str, mapping: ClaimMapping, people: FakePeople | None = None):
        self.people = people or FakePeople()
        self.real = PrincipalResolver(
            _entra_config(jwks_url),
            claim_mapping=mapping,
            role_source=self.people,
            role_lookup_timeout_seconds=0.2,
        )

    def resolve(self, token: str):  # type: ignore[no-untyped-def]
        return asyncio.run(self.real.resolve_principal(token))


def _resolver(jwks_url: str, mapping: ClaimMapping) -> _EntraResolver:
    return _EntraResolver(jwks_url, mapping)


def _key(keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]) -> rsa.RSAPrivateKey:
    return keypair[0]


# --- the mapping builds the principal ---


def test_extension_attributes_build_the_principal(keypair, jwks_url) -> None:
    token = sign_token(
        _key(keypair),
        entra_claims(
            **{
                f"{EXT}_clearance": "OFFICIAL-SENSITIVE",
                f"{EXT}_orgUnit": "unit-2",
                f"{EXT}_handlingCodes": ["R", "S"],
            }
        ),
    )
    principal = _resolver(jwks_url, BY_EXTENSION).resolve(token)
    assert principal.id == OID
    assert principal.clearance == "OFFICIAL-SENSITIVE"
    assert principal.org_unit == "unit-2"
    assert principal.receivable_handling_codes == ["R", "S"]
    assert principal.roles == []


def test_an_entra_app_role_grants_no_ospreyflow_role(keypair, jwks_url) -> None:
    """An Entra token's `roles` are app roles an Entra administrator assigns; OspreyFlow's roles
    stay assigned in Admin › People (ADR-148 decision 9), so `admin` there makes nobody an
    administrator here."""
    token = sign_token(_key(keypair), entra_claims(**_GOOD, roles=["admin", "analyst"]))
    assert _resolver(jwks_url, BY_EXTENSION).resolve(token).roles == []


def test_a_single_valued_handling_code_attribute_is_one_code_not_its_letters(
    keypair, jwks_url
) -> None:
    """An extension attribute is a string unless declared multi-valued. `list("RS")` would grant
    codes `R` and `S` from a value naming one code `RS`."""
    token = sign_token(
        _key(keypair),
        entra_claims(
            **{
                f"{EXT}_clearance": "OFFICIAL",
                f"{EXT}_orgUnit": "unit-1",
                f"{EXT}_handlingCodes": "RS",
            }
        ),
    )
    principal = _resolver(jwks_url, BY_EXTENSION).resolve(token)
    assert principal.receivable_handling_codes == ["RS"]


def test_group_ids_build_the_principal_and_handling_codes_are_the_union(keypair, jwks_url) -> None:
    token = sign_token(
        _key(keypair), entra_claims(groups=[G_SENSITIVE, G_UNIT_1, G_CODE_R, G_CODES_ST])
    )
    principal = _resolver(jwks_url, BY_GROUPS).resolve(token)
    assert principal.clearance == "OFFICIAL-SENSITIVE"
    assert principal.org_unit == "unit-1"
    assert sorted(principal.receivable_handling_codes) == ["R", "S", "T"]


def test_a_named_claim_and_a_group_table_in_one_mapping(keypair, jwks_url) -> None:
    token = sign_token(
        _key(keypair),
        entra_claims(**{f"{EXT}_clearance": "OFFICIAL"}, groups=[G_UNIT_2, G_CODE_R]),
    )
    principal = _resolver(jwks_url, MIXED).resolve(token)
    assert (principal.clearance, principal.org_unit) == ("OFFICIAL", "unit-2")
    assert principal.receivable_handling_codes == ["R"]


# --- missing → refused, never defaulted to cleared ---


@pytest.mark.parametrize(
    "mapping", [BY_EXTENSION, BY_GROUPS, MIXED], ids=["extension", "groups", "mixed"]
)
def test_both_missing_is_refused_never_defaulted_to_cleared(keypair, jwks_url, mapping) -> None:
    """Neither the extension attributes nor a `groups` claim: no principal at all."""
    token = sign_token(_key(keypair), entra_claims())
    with pytest.raises(PrincipalResolutionError, match="clearance"):
        _resolver(jwks_url, mapping).resolve(token)


def test_a_missing_clearance_attribute_with_the_unit_group_present_is_refused(
    keypair, jwks_url
) -> None:
    """The mixed mapping with everything but the clearance attribute: were a missing attribute
    defaulted, this token would resolve, so the case fails for the reason it names (rule 15)."""
    token = sign_token(_key(keypair), entra_claims(groups=[G_UNIT_1, G_CODE_R]))
    with pytest.raises(PrincipalResolutionError, match="clearance"):
        _resolver(jwks_url, MIXED).resolve(token)


def test_a_missing_clearance_with_a_unit_present_is_refused(keypair, jwks_url) -> None:
    token = sign_token(_key(keypair), entra_claims(groups=[G_UNIT_1, G_CODE_R]))
    with pytest.raises(PrincipalResolutionError, match="clearance"):
        _resolver(jwks_url, BY_GROUPS).resolve(token)


def test_a_missing_unit_with_a_clearance_present_is_refused(keypair, jwks_url) -> None:
    token = sign_token(_key(keypair), entra_claims(**{f"{EXT}_clearance": "OFFICIAL"}, groups=[]))
    with pytest.raises(PrincipalResolutionError, match="organisational unit"):
        _resolver(jwks_url, MIXED).resolve(token)


def test_an_empty_clearance_attribute_is_refused(keypair, jwks_url) -> None:
    token = sign_token(
        _key(keypair), entra_claims(**{f"{EXT}_clearance": "", f"{EXT}_orgUnit": "unit-1"})
    )
    with pytest.raises(PrincipalResolutionError, match="clearance"):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


def test_a_clearance_attribute_that_is_not_a_string_is_refused(keypair, jwks_url) -> None:
    token = sign_token(
        _key(keypair),
        entra_claims(**{f"{EXT}_clearance": ["OFFICIAL", "SECRET"], f"{EXT}_orgUnit": "unit-1"}),
    )
    with pytest.raises(PrincipalResolutionError, match="clearance"):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


def test_a_numeric_clearance_attribute_is_refused_not_turned_into_text(keypair, jwks_url) -> None:
    token = sign_token(
        _key(keypair), entra_claims(**{f"{EXT}_clearance": 2, f"{EXT}_orgUnit": "unit-1"})
    )
    with pytest.raises(PrincipalResolutionError, match="clearance"):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


def test_handling_codes_of_the_wrong_type_are_refused(keypair, jwks_url) -> None:
    token = sign_token(
        _key(keypair),
        entra_claims(
            **{
                f"{EXT}_clearance": "OFFICIAL",
                f"{EXT}_orgUnit": "unit-1",
                f"{EXT}_handlingCodes": 7,
            }
        ),
    )
    with pytest.raises(PrincipalResolutionError, match="handling codes"):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


# --- groups: unmapped grants nothing, two clearances refused, overage refused ---


def test_an_unmapped_group_grants_nothing(keypair, jwks_url) -> None:
    """An unmapped group neither satisfies a required claim nor adds a handling code."""
    resolver = _resolver(jwks_url, BY_GROUPS)
    granted = resolver.resolve(
        sign_token(_key(keypair), entra_claims(groups=[G_OFFICIAL, G_UNIT_1, G_UNMAPPED]))
    )
    assert granted.receivable_handling_codes == []
    with pytest.raises(PrincipalResolutionError, match="clearance"):
        resolver.resolve(sign_token(_key(keypair), entra_claims(groups=[G_UNMAPPED, G_UNIT_1])))


def test_groups_granting_two_clearances_are_refused_not_resolved(keypair, jwks_url) -> None:
    token = sign_token(_key(keypair), entra_claims(groups=[G_OFFICIAL, G_SENSITIVE, G_UNIT_1]))
    with pytest.raises(PrincipalResolutionError, match="more than one clearance"):
        _resolver(jwks_url, BY_GROUPS).resolve(token)


def test_groups_granting_two_units_are_refused(keypair, jwks_url) -> None:
    token = sign_token(_key(keypair), entra_claims(groups=[G_OFFICIAL, G_UNIT_1, G_UNIT_2]))
    with pytest.raises(PrincipalResolutionError, match="more than one organisational unit"):
        _resolver(jwks_url, BY_GROUPS).resolve(token)


def test_two_groups_granting_the_same_clearance_resolve(keypair, jwks_url) -> None:
    mapping = BY_GROUPS.model_copy(
        update={"clearance": ValueSource(groups={G_OFFICIAL: "OFFICIAL", G_UNMAPPED: "OFFICIAL"})}
    )
    token = sign_token(_key(keypair), entra_claims(groups=[G_OFFICIAL, G_UNMAPPED, G_UNIT_1]))
    assert _resolver(jwks_url, mapping).resolve(token).clearance == "OFFICIAL"


def test_a_group_overage_is_refused_not_read_as_no_groups(keypair, jwks_url) -> None:
    """Past 200 groups Entra leaves `groups` out of a JWT and names a Graph source instead.

    The mapping takes clearance and unit from attributes and only the handling codes from groups,
    so without the overage check this token would resolve (with no codes) rather than be refused
    by some other missing claim: the case fails for the reason it names (rule 15)."""
    codes_by_group = BY_EXTENSION.model_copy(
        update={"handling_codes": CodesSource(groups={G_CODE_R: ["R"]})}
    )
    token = sign_token(
        _key(keypair),
        entra_claims(
            **_GOOD,
            _claim_names={"groups": "src1"},
            _claim_sources={
                "src1": {
                    "endpoint": f"https://graph.windows.net/{TENANT}/users/"
                    "50000000-0000-4000-8000-000000000001/getMemberObjects"
                }
            },
        ),
    )
    with pytest.raises(PrincipalResolutionError, match="overage"):
        _resolver(jwks_url, codes_by_group).resolve(token)


def test_the_implicit_flows_overage_signal_is_refused(keypair, jwks_url) -> None:
    """In the implicit flow Entra marks the overage with `hasgroups: true` instead."""
    codes_by_group = BY_EXTENSION.model_copy(
        update={"handling_codes": CodesSource(groups={G_CODE_R: ["R"]})}
    )
    token = sign_token(_key(keypair), entra_claims(**_GOOD, hasgroups=True))
    with pytest.raises(PrincipalResolutionError, match="overage"):
        _resolver(jwks_url, codes_by_group).resolve(token)


def test_a_groups_claim_that_is_not_a_list_of_ids_is_refused(keypair, jwks_url) -> None:
    """Codes alone from groups, so an unchecked string would resolve (no code matches a letter)
    rather than be refused for a missing clearance."""
    codes_by_group = BY_EXTENSION.model_copy(
        update={"handling_codes": CodesSource(groups={G_CODE_R: ["R"]})}
    )
    token = sign_token(_key(keypair), entra_claims(**_GOOD, groups=G_CODE_R))
    with pytest.raises(PrincipalResolutionError, match="groups"):
        _resolver(jwks_url, codes_by_group).resolve(token)


# --- the stand-in refuses what Entra's tokens are refused for (rule 15) ---

_GOOD = {f"{EXT}_clearance": "OFFICIAL", f"{EXT}_orgUnit": "unit-1"}


def test_the_well_formed_entra_token_resolves(keypair, jwks_url) -> None:
    """The control for every refusal below: the same token, unaltered, resolves."""
    principal = _resolver(jwks_url, BY_EXTENSION).resolve(
        sign_token(_key(keypair), entra_claims(**_GOOD))
    )
    assert principal.clearance == "OFFICIAL"


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"oid": _ABSENT}, "oid"),
        ({"tid": _ABSENT}, "tid"),
        ({"tid": OTHER_TENANT}, "tenant"),
        ({"iss": f"https://login.microsoftonline.com/{OTHER_TENANT}/v2.0"}, "issuer"),
        ({"aud": "ffffffff-ffff-4fff-8fff-ffffffffffff"}, "(?i)audience"),
        (
            {
                "iat": int(time.time()) - 7200,
                "nbf": int(time.time()) - 7200,
                "exp": int(time.time()) - 3600,
            },
            "expired",
        ),
        ({"exp": _ABSENT}, "exp"),
    ],
    ids=["no-oid", "no-tid", "other-tenant", "wrong-issuer", "wrong-audience", "expired", "no-exp"],
)
def test_a_token_entra_would_not_accept_is_refused(keypair, jwks_url, overrides, why) -> None:
    token = sign_token(_key(keypair), entra_claims(**_GOOD, **overrides))
    with pytest.raises(PrincipalResolutionError, match=why):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


@pytest.mark.parametrize(
    "overrides",
    [{"idtyp": "app", "scp": _ABSENT}, {"scp": _ABSENT}, {"idtyp": "app"}],
    ids=["app-token", "no-scp", "idtyp-app"],
)
def test_an_app_only_token_is_no_person(keypair, jwks_url, overrides) -> None:
    """A daemon's client-credentials token for this API carries no `scp` (and, asked for, `idtyp:
    app`); in a mapped group it would otherwise resolve as a person."""
    token = sign_token(_key(keypair), entra_claims(**_GOOD, **overrides))
    with pytest.raises(PrincipalResolutionError, match="app-only"):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


def test_an_oid_that_is_not_an_object_id_is_refused(keypair, jwks_url) -> None:
    token = sign_token(_key(keypair), entra_claims(**_GOOD, oid="synthetic.analyst"))
    with pytest.raises(PrincipalResolutionError, match="oid"):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


def test_another_tenants_whole_token_is_refused(keypair, jwks_url) -> None:
    """The shape Entra really issues for another tenant: its issuer and its `tid` together. Every
    tenant's tokens are signed by the same published keys, so the signature alone proves nothing."""
    token = sign_token(
        _key(keypair),
        entra_claims(
            **_GOOD, tid=OTHER_TENANT, iss=f"https://login.microsoftonline.com/{OTHER_TENANT}/v2.0"
        ),
    )
    with pytest.raises(PrincipalResolutionError):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


def test_an_entra_mapping_without_issuer_and_audience_checks_is_refused_at_construction(
    jwks_url,
) -> None:
    """A tenant-bound mapping on a resolver that would not check `iss` and `aud` accepts any
    tenant's token signed by a key it trusts — refused before a single token is read."""
    with pytest.raises(ValueError, match="issuer"):
        PrincipalResolver(_config(jwks_url, oidc_audience=CLIENT_ID), claim_mapping=BY_EXTENSION)
    with pytest.raises(ValueError, match="audience"):
        PrincipalResolver(_config(jwks_url, oidc_issuer=ISSUER), claim_mapping=BY_EXTENSION)


# --- the settings model ---


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"claim": "x", "groups": {G_OFFICIAL: "OFFICIAL"}}, {"claim": ""}, {"groups": {}}],
    ids=["neither", "both", "empty-claim", "empty-table"],
)
def test_a_source_names_exactly_one_of_a_claim_or_a_group_table(kwargs) -> None:
    with pytest.raises(ValidationError):
        ValueSource(**kwargs)
    with pytest.raises(ValidationError):
        CodesSource(
            **{
                k: ({g: [v] for g, v in t.items()} if k == "groups" else t)
                for k, t in kwargs.items()
            }
        )


@pytest.mark.parametrize(
    "groups", [{G_OFFICIAL: ""}, {"": "OFFICIAL"}], ids=["empty-value", "empty-group"]
)
def test_a_group_table_entry_must_grant_a_value(groups) -> None:
    with pytest.raises(ValidationError):
        ValueSource(groups=groups)
    with pytest.raises(ValidationError):
        CodesSource(groups={g: [v] for g, v in groups.items()})


def test_a_mapping_other_than_the_fixed_names_needs_its_tenant() -> None:
    """Without `tenant_id` an Entra mapping would demand no `oid`, `tid` or `exp` and no issuer or
    audience check: refused when the settings load."""
    with pytest.raises(ValidationError, match="tenant_id"):
        ClaimMapping(clearance=ValueSource(claim=f"{EXT}_clearance"))
    with pytest.raises(ValidationError, match="tenant_id"):
        ClaimMapping(handling_codes=CodesSource(groups={G_CODE_R: ["R"]}))


@pytest.mark.parametrize(
    "tenant", ["", "contoso", TENANT.upper() + "x"], ids=["empty", "name", "bad"]
)
def test_the_tenant_id_must_be_a_guid(tenant) -> None:
    with pytest.raises(ValidationError, match="tenant_id"):
        ClaimMapping(
            tenant_id=tenant, client_id=GLASS, clearance=ValueSource(claim=f"{EXT}_clearance")
        )


def test_a_group_table_key_must_be_a_group_id() -> None:
    """A mistyped group id matches no token's group, so its grant would vanish without a word."""
    with pytest.raises(ValidationError, match="group id"):
        ValueSource(groups={"Clearance-Official": "OFFICIAL"})
    with pytest.raises(ValidationError, match="group id"):
        CodesSource(groups={G_CODE_R[:-1]: ["R"]})  # one digit short


def test_the_groups_claim_must_be_named() -> None:
    with pytest.raises(ValidationError, match="groups_claim"):
        ClaimMapping(
            tenant_id=TENANT,
            client_id=GLASS,
            groups_claim="",
            clearance=ValueSource(groups=_G_OFF),
        )


_G_OFF = {G_OFFICIAL: "OFFICIAL"}


@pytest.mark.parametrize("how", ["copy", "construct"])
def test_a_mapping_that_skipped_its_validators_is_validated_by_the_resolver(jwks_url, how) -> None:
    """`model_copy` and `model_construct` skip the validators. A copy of the default with a group
    source and no tenant would otherwise be Keycloak-handled: no tenant check, the token's roles."""
    if how == "copy":
        mapping = ClaimMapping().model_copy(update={"clearance": ValueSource(groups=_G_OFF)})
    else:
        mapping = ClaimMapping.model_construct(
            clearance=ValueSource(groups=_G_OFF),
            org_unit=ValueSource(claim="org_unit"),
            handling_codes=CodesSource(claim="receivable_handling_codes"),
            groups_claim="groups",
            tenant_id=None,
        )
    with pytest.raises(ValidationError, match="tenant_id"):
        PrincipalResolver(_entra_config(jwks_url), claim_mapping=mapping, role_source=FakePeople())


def test_the_settings_refuse_an_unknown_key() -> None:
    """A misspelt setting (`clearence`) must fail the install, not leave the default in place."""
    with pytest.raises(ValidationError):
        ClaimMapping.model_validate({"clearence": {"claim": f"{EXT}_clearance"}})


def test_the_settings_load_from_a_plain_mapping() -> None:
    """The shape a profile's settings will render (after P7): plain data, validated."""
    mapping = ClaimMapping.model_validate(
        {
            "tenant_id": TENANT,
            "client_id": GLASS,
            "clearance": {"claim": f"{EXT}_clearance"},
            "org_unit": {"groups": {G_UNIT_1: "unit-1"}},
            "handling_codes": {"groups": {G_CODE_R: ["R"]}},
        }
    )
    assert mapping.org_unit.groups == {G_UNIT_1: "unit-1"}


# --- the default mapping is today's fixed names, and the one construction path ---


def test_the_default_mapping_is_the_fixed_claim_names(keypair, jwks_url) -> None:
    """No mapping given: today's behaviour exactly (`test_auth.py`'s cases, unchanged)."""
    default = ClaimMapping()
    assert (default.clearance.claim, default.org_unit.claim, default.handling_codes.claim) == (
        "clearance",
        "org_unit",
        "receivable_handling_codes",
    )
    assert default.tenant_id is None
    principal = PrincipalResolver(_config(jwks_url)).resolve(
        sign_token(_key(keypair), default_claims(receivable_handling_codes=["R"]))
    )
    assert (principal.clearance, principal.org_unit, principal.receivable_handling_codes) == (
        "OFFICIAL",
        "unit-1",
        ["R"],
    )
    assert principal.roles == ["analyst"]


def test_the_default_mapping_reads_one_code_or_role_as_one_not_its_letters(
    keypair, jwks_url
) -> None:
    """Two old behaviours tightened for every deployment: `list("RS")` granted codes `R` and `S`,
    and a role given as a string was split the same way."""
    principal = PrincipalResolver(_config(jwks_url)).resolve(
        sign_token(_key(keypair), default_claims(receivable_handling_codes="RS", roles="analyst"))
    )
    assert principal.receivable_handling_codes == ["RS"]
    assert principal.roles == ["analyst"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"clearance": ["OFFICIAL"]},
        {"clearance": ""},
        {"org_unit": 3},
        {"receivable_handling_codes": {"R": True}},
        {"roles": 1},
        {"sub": 5},
    ],
    ids=[
        "list-clearance",
        "empty-clearance",
        "numeric-unit",
        "object-codes",
        "numeric-roles",
        "numeric-sub",
    ],
)
def test_the_default_mapping_refuses_a_claim_of_the_wrong_type(
    keypair, jwks_url, overrides
) -> None:
    """Formerly `str()`-ed or `list()`-ed (or a 500); now a 401, as a missing claim is."""
    with pytest.raises(PrincipalResolutionError):
        PrincipalResolver(_config(jwks_url)).resolve(
            sign_token(_key(keypair), default_claims(**overrides))
        )


def test_the_default_mapping_does_not_read_entra_attributes(keypair, jwks_url) -> None:
    claims = default_claims(**{f"{EXT}_clearance": "OFFICIAL"})
    del claims["clearance"]
    with pytest.raises(PrincipalResolutionError):
        PrincipalResolver(_config(jwks_url)).resolve(sign_token(_key(keypair), claims))


async def test_owner_resolution_is_unavailable_on_entra_even_with_an_exchange_configured(
    keypair, jwks_url, token_exchange_url: str, token_exchange_registry: TokenExchangeRegistry
) -> None:
    """Entra has no impersonation exchange, so a scheduled run cannot act as its owner (the
    orchestrator's ruling, 11 November 2026): `resolve_for_owner` answers None (ADR-044's
    unreachable path, the run marked stopped) and the detailed form says why, even where an
    exchange endpoint is configured and would grant. Red with the Entra refusal removed: the
    exchange's token resolves. The one-path proof for owners stays `test_auth.py`'s (Keycloak)."""
    token_exchange_registry.register(
        "owner-ok", entra_claims(sub="owner-ok", groups=[G_OFFICIAL, G_UNIT_1, G_CODE_R])
    )
    config = _config(
        jwks_url,
        oidc_issuer=ISSUER,
        oidc_audience=CLIENT_ID,
        oidc_token_exchange_url=token_exchange_url,
        oidc_token_exchange_client_id=TOKEN_EXCHANGE_CLIENT_ID,
        oidc_token_exchange_client_secret=TOKEN_EXCHANGE_CLIENT_SECRET,
    )
    resolver = PrincipalResolver(config, claim_mapping=BY_GROUPS, role_source=FakePeople())
    try:
        assert await resolver.resolve_for_owner("owner-ok") is None
        with pytest.raises(PrincipalExchangeUnavailable, match="unavailable with Entra ID"):
            await resolver.resolve_for_owner_detailed("owner-ok")
    finally:
        await resolver.aclose()


_PRINCIPAL_CALL = re.compile(r"(^|\.)Principal(\.|$)")


def test_one_principal_construction_in_principal_auth() -> None:
    """A `Principal` is built in exactly one place in `principal_auth`, `principal_from_claims`:
    any call naming the class (`Principal(…)`, `domain.Principal(…)`, `Principal.model_validate`,
    `Principal.model_construct`), in a function or at module level."""
    source = (
        Path(__file__).resolve().parents[4] / "OspreyFlow_Core/packages/principal_auth/__init__.py"
    )
    tree = ast.parse(source.read_text())
    owner: dict[ast.AST, str] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                owner.setdefault(node, fn.name)
    calls = [
        owner.get(node, "<module>")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _PRINCIPAL_CALL.search(ast.unparse(node.func))
    ]
    assert calls == ["principal_from_claims"]


@pytest.mark.parametrize(
    "plant",
    [
        "def _p(c):\n    return domain.Principal(id='x', clearance='x', org_unit='x')\n",
        "def _p(c):\n    return Principal.model_validate(c)\n",
        "_P = Principal.model_construct()\n",
    ],
    ids=["qualified", "model-validate", "module-level"],
)
def test_the_construction_check_sees_each_other_way_to_build_one(plant) -> None:
    """The check above, shown red on the shapes a second path could take (rule 15)."""
    tree = ast.parse(plant)
    assert any(
        isinstance(n, ast.Call) and _PRINCIPAL_CALL.search(ast.unparse(n.func))
        for n in ast.walk(tree)
    )


# --- review round 1 (the orchestrator, 11 November 2026): the id, the Keycloak side, the client ---


def test_an_entra_principal_is_keyed_by_oid_not_its_pairwise_sub(keypair, jwks_url) -> None:
    """Entra's `sub` is pairwise per application: keyed by it, one person signing in through a
    second client id would be two principals, and Admin › People could never name a person before
    their first sign-in (Graph gives `oid`). Two `sub`s, one `oid`: one principal, keyed by
    `oid`."""
    resolver = _resolver(jwks_url, BY_EXTENSION)
    first = resolver.resolve(sign_token(_key(keypair), entra_claims(**_GOOD, sub="pairwise-app-1")))
    second = resolver.resolve(
        sign_token(_key(keypair), entra_claims(**_GOOD, sub="pairwise-app-2"))
    )
    assert first.id == second.id == OID


def test_a_keycloak_principal_is_still_keyed_by_sub(keypair, jwks_url) -> None:
    principal = PrincipalResolver(_config(jwks_url)).resolve(
        sign_token(_key(keypair), default_claims(oid=OID))
    )
    assert principal.id == "analyst-1"


@pytest.mark.parametrize("tenant", [TENANT, OTHER_TENANT], ids=["our-tenant", "other-tenant"])
def test_an_entra_token_under_the_keycloak_handling_is_refused(keypair, jwks_url, tenant) -> None:
    """With the fixed names an Entra token would skip the tenant, `oid` and scope checks, and its
    app role `osprey-admin` would be read as OspreyFlow's administrator. Keycloak never emits
    `tid`, so a token carrying one is refused there, whichever tenant it names."""
    claims = default_claims(roles=["osprey-admin"], tid=tenant, oid=OID, azp=GLASS)
    with pytest.raises(PrincipalResolutionError, match="carries tid"):
        PrincipalResolver(_config(jwks_url)).resolve(sign_token(_key(keypair), claims))


def test_a_v1_token_naming_the_glass_by_appid_resolves(keypair, jwks_url) -> None:
    """The control for the client pin: a v1.0 token names its client in `appid`, not `azp`."""
    token = sign_token(_key(keypair), entra_claims(**_GOOD, azp=_ABSENT, appid=GLASS, ver="1.0"))
    assert _resolver(jwks_url, BY_EXTENSION).resolve(token).id == OID


@pytest.mark.parametrize(
    "overrides",
    [
        {"azp": OTHER_APP},
        {"azp": _ABSENT},
        {"azp": _ABSENT, "appid": OTHER_APP},
        {"appid": OTHER_APP},
    ],
    ids=["other-azp", "no-client", "v1-other-appid", "azp-and-other-appid"],
)
def test_a_token_issued_to_another_client_is_refused(keypair, jwks_url, overrides) -> None:
    """Another application in the tenant can obtain a token for this API; it is no Glass session."""
    token = sign_token(_key(keypair), entra_claims(**_GOOD, **overrides))
    with pytest.raises(PrincipalResolutionError, match="Glass's client"):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


@pytest.mark.parametrize(
    "scp",
    ["User.Read", "openid access_as_user_extra", "openid"],
    ids=["other-scope", "longer-name", "openid-only"],
)
def test_a_token_without_this_apis_scope_is_refused(keypair, jwks_url, scp) -> None:
    token = sign_token(_key(keypair), entra_claims(**_GOOD, scp=scp))
    with pytest.raises(PrincipalResolutionError, match="scope"):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


@pytest.mark.parametrize(
    "overrides",
    [{"acct": 1}, {"acct": "1"}, {"idp": f"https://sts.windows.net/{OTHER_TENANT}/"}],
    ids=["acct", "acct-text", "idp-other"],
)
def test_a_guest_account_is_refused(keypair, jwks_url, overrides) -> None:
    token = sign_token(_key(keypair), entra_claims(**_GOOD, **overrides))
    with pytest.raises(PrincipalResolutionError, match="guest"):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


def test_a_member_account_resolves(keypair, jwks_url) -> None:
    """The control for the guest refusal: `acct` 0, and an `idp` equal to the issuer."""
    token = sign_token(_key(keypair), entra_claims(**_GOOD, acct=0, idp=ISSUER))
    assert _resolver(jwks_url, BY_EXTENSION).resolve(token).id == OID


@pytest.mark.parametrize("client", [None, "", "glass"], ids=["none", "empty", "not-a-guid"])
def test_an_entra_mapping_needs_the_glass_client_id(client) -> None:
    with pytest.raises(ValidationError, match="client_id"):
        ClaimMapping(
            tenant_id=TENANT, client_id=client, clearance=ValueSource(claim=f"{EXT}_clearance")
        )


@pytest.mark.parametrize("scope", ["", "openid access_as_user"], ids=["empty", "two"])
def test_the_scope_setting_names_one_scope(scope) -> None:
    with pytest.raises(ValidationError, match="scope"):
        ClaimMapping(tenant_id=TENANT, client_id=GLASS, scope=scope)


# --- bounds on what a token's lists may hold ---

_CODES_BY_GROUP = CodesSource(groups={G_CODE_R: ["R"]})


def test_a_groups_list_past_entras_cap_is_refused(keypair, jwks_url) -> None:
    """Entra puts at most 200 groups in a JWT and sends an overage past that; a longer list is no
    token Entra issued. 200 resolve; 201 are refused."""
    mapping = BY_EXTENSION.model_copy(update={"handling_codes": _CODES_BY_GROUP})
    resolver = _resolver(jwks_url, mapping)
    many = [G_CODE_R] + [f"60000000-0000-4000-8000-{i:012d}" for i in range(199)]
    granted = resolver.resolve(sign_token(_key(keypair), entra_claims(**_GOOD, groups=many)))
    assert granted.receivable_handling_codes == ["R"]
    with pytest.raises(PrincipalResolutionError, match="more than 200"):
        resolver.resolve(
            sign_token(_key(keypair), entra_claims(**_GOOD, groups=[*many, G_UNMAPPED]))
        )


@pytest.mark.parametrize("codes", ["", ["R", ""]], ids=["empty-string", "empty-in-list"])
def test_an_empty_handling_code_is_refused(keypair, jwks_url, codes) -> None:
    token = sign_token(_key(keypair), entra_claims(**_GOOD, **{f"{EXT}_handlingCodes": codes}))
    with pytest.raises(PrincipalResolutionError, match="empty name"):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


def test_a_handling_code_given_twice_is_kept_once(keypair, jwks_url) -> None:
    """As the group path keeps once a code two groups grant."""
    token = sign_token(
        _key(keypair), entra_claims(**_GOOD, **{f"{EXT}_handlingCodes": ["R", "S", "R"]})
    )
    assert _resolver(jwks_url, BY_EXTENSION).resolve(token).receivable_handling_codes == ["R", "S"]


@pytest.mark.parametrize("field", ["clearance", "org_unit"])
def test_one_group_cannot_grant_two_clearances_or_units(field) -> None:
    """A clearance or unit table maps a group to one value; a list of two is refused when the
    settings load, so a single group can never be read as two grants."""
    two = {"groups": {G_OFFICIAL: ["OFFICIAL", "SECRET"]}}
    with pytest.raises(ValidationError):
        ValueSource.model_validate(two)
    with pytest.raises(ValidationError):
        ClaimMapping.model_validate({"tenant_id": TENANT, "client_id": GLASS, field: two})


# --- P10 part 2: the guest check by tenant (CARRIES, P10 round 2) ---

V1_ISSUER = f"https://sts.windows.net/{TENANT}/"


@pytest.mark.parametrize("idp", [ISSUER, V1_ISSUER], ids=["member-v2-form", "member-v1-form"])
def test_a_member_whose_idp_names_our_tenant_in_either_form_resolves(
    keypair, jwks_url, idp
) -> None:
    """Entra may send `idp` in the v1.0 form on a v2.0 token, or the reverse: a member's `idp` names
    our tenant whichever form it takes. Red against the string comparison with `iss`: the v1 form
    on a v2.0 token was refused as a guest."""
    token = sign_token(_key(keypair), entra_claims(**_GOOD, idp=idp))
    assert _resolver(jwks_url, BY_EXTENSION).resolve(token).id == OID


@pytest.mark.parametrize(
    "idp",
    [
        f"https://login.microsoftonline.com/{OTHER_TENANT}/v2.0",
        f"https://sts.windows.net/{OTHER_TENANT}/",
        "live.com",
        "https://adfs.example.test/adfs/services/trust",
        f"https://sts.windows.net/{TENANT}/extra",
        f"https://login.microsoftonline.com/{TENANT}/",
        ["https://sts.windows.net/" + TENANT + "/"],
    ],
    ids=[
        "other-v2",
        "other-v1",
        "msa",
        "federated",
        "trailing-path",
        "v2-without-version",
        "not-text",
    ],
)
def test_an_idp_naming_no_entra_issuer_of_our_tenant_is_a_guest(keypair, jwks_url, idp) -> None:
    """Strict: an `idp` that names another tenant, a Microsoft account, a federation's own issuer
    (a federated member, should Entra send one; unmeasured, Amendment 6's assumption list) or
    anything malformed is refused as a guest's. Admitting a federated member is a later setting."""
    token = sign_token(_key(keypair), entra_claims(**_GOOD, idp=idp))
    with pytest.raises(PrincipalResolutionError, match="guest"):
        _resolver(jwks_url, BY_EXTENSION).resolve(token)


# --- P10 part 2: a client or scope with no tenant (CARRIES, P10 round 2) ---


@pytest.mark.parametrize(
    "kwargs", [{"client_id": GLASS}, {"scope": "other_scope"}], ids=["client", "scope"]
)
def test_a_client_or_scope_without_a_tenant_is_refused(kwargs) -> None:
    """Checked only for an Entra mapping, so set without a tenant they would be ignored."""
    with pytest.raises(ValidationError, match="tenant_id"):
        ClaimMapping(**kwargs)


def test_the_default_mapping_still_loads_after_a_dump() -> None:
    """The control: the default scope, dumped and re-read by the resolver, is not taken as set."""
    assert ClaimMapping.model_validate(ClaimMapping().model_dump()) == ClaimMapping()


# --- P10 part 2: the stored person (the orchestrator's ruling, 11 November 2026) ---


def test_an_entra_principals_roles_are_the_stored_ones_never_the_tokens(keypair, jwks_url) -> None:
    resolver = _resolver(jwks_url, BY_EXTENSION)
    resolver.people.rows[(TENANT, OID)] = StoredPerson(roles=("osprey-admin",), disabled=False)
    token = sign_token(_key(keypair), entra_claims(**_GOOD, roles=["analyst", "role:x"]))
    assert resolver.resolve(token).roles == ["osprey-admin"]
    assert resolver.people.calls == [(TENANT, OID)]


def test_the_store_is_given_the_resolved_access_never_the_tokens_roles(keypair, jwks_url) -> None:
    resolver = _resolver(jwks_url, BY_EXTENSION)
    resolver.resolve(sign_token(_key(keypair), entra_claims(**_GOOD, email=["not", "text"])))
    assert resolver.people.seen == SeenPerson(
        name="Synthetic Analyst",
        username="synthetic.analyst@example.test",
        email=None,
        clearance="OFFICIAL",
        org_unit="unit-1",
        receivable_handling_codes=(),
    )


def test_a_first_sign_in_records_the_person_with_no_roles(keypair, jwks_url) -> None:
    resolver = _resolver(jwks_url, BY_EXTENSION)
    assert resolver.resolve(sign_token(_key(keypair), entra_claims(**_GOOD))).roles == []
    assert (TENANT, OID) in resolver.people.rows


def test_another_tenants_row_for_the_same_oid_grants_nothing(keypair, jwks_url) -> None:
    """Rule 3 at the resolver: the store is read by our tenant and the oid together."""
    resolver = _resolver(jwks_url, BY_EXTENSION)
    resolver.people.rows[(OTHER_TENANT, OID)] = StoredPerson(
        roles=("osprey-admin",), disabled=False
    )
    assert resolver.resolve(sign_token(_key(keypair), entra_claims(**_GOOD))).roles == []


def test_a_person_disabled_here_is_refused(keypair, jwks_url) -> None:
    resolver = _resolver(jwks_url, BY_EXTENSION)
    resolver.people.rows[(TENANT, OID)] = StoredPerson(roles=("osprey-admin",), disabled=True)
    with pytest.raises(PrincipalResolutionError, match="disabled"):
        resolver.resolve(sign_token(_key(keypair), entra_claims(**_GOOD)))


@pytest.mark.parametrize("how", ["raises", "slow"])
def test_a_failed_or_slow_lookup_is_unavailable_never_a_principal(keypair, jwks_url, how) -> None:
    """A 503, never a principal with no roles (the ruling's words)."""
    resolver = _resolver(jwks_url, BY_EXTENSION)
    resolver.people.rows[(TENANT, OID)] = StoredPerson(roles=("osprey-admin",), disabled=False)
    if how == "raises":
        resolver.people.fail = ConnectionError("store down")
    else:
        resolver.people.delay = 1.0
    with pytest.raises(PrincipalLookupUnavailable):
        resolver.resolve(sign_token(_key(keypair), entra_claims(**_GOOD)))


@pytest.mark.parametrize(
    "stored",
    [StoredPerson(roles=("",), disabled=False), StoredPerson(roles=["x"], disabled=False), None],  # type: ignore[arg-type]
    ids=["empty-role", "a-list", "not-a-person"],
)
def test_a_malformed_stored_person_is_unavailable(keypair, jwks_url, stored) -> None:
    resolver = _resolver(jwks_url, BY_EXTENSION)

    async def answer(tenant_id: str, oid: str, seen: object) -> object:
        return stored

    resolver.people.person = answer  # type: ignore[method-assign]
    with pytest.raises(PrincipalLookupUnavailable):
        resolver.resolve(sign_token(_key(keypair), entra_claims(**_GOOD)))


def test_a_refused_token_records_nobody(keypair, jwks_url) -> None:
    """Every token refusal comes before the store is touched."""
    resolver = _resolver(jwks_url, BY_EXTENSION)
    for overrides in ({"azp": OTHER_APP}, {"scp": "User.Read"}, {"acct": 1}):
        with pytest.raises(PrincipalResolutionError):
            resolver.resolve(sign_token(_key(keypair), entra_claims(**_GOOD, **overrides)))
    with pytest.raises(PrincipalResolutionError):
        # no clearance: refused by the mapping, before the store
        resolver.resolve(sign_token(_key(keypair), entra_claims(**{f"{EXT}_orgUnit": "unit-1"})))
    assert resolver.people.calls == []


def test_the_synchronous_path_refuses_an_entra_mapping(keypair, jwks_url) -> None:
    """Only `resolve_principal` reads the stored roles; `resolve` would build one without them."""
    real = _resolver(jwks_url, BY_EXTENSION).real
    with pytest.raises(PrincipalLookupUnavailable):
        real.resolve(sign_token(_key(keypair), entra_claims(**_GOOD)))


def test_the_construction_path_refuses_an_entra_principal_without_its_stored_person() -> None:
    """The second guard behind `resolve`'s: built from claims alone, an Entra principal would have
    no roles read for it; refused, never built with none (rule 15: `resolve`'s case alone passes with
    either guard removed)."""
    from principal_auth import principal_from_claims

    claims = {**entra_claims(**_GOOD), "sub": "s"}
    with pytest.raises(PrincipalLookupUnavailable):
        principal_from_claims(claims, BY_EXTENSION)


def test_an_entra_mapping_needs_a_people_store_and_keycloak_refuses_one(jwks_url) -> None:
    with pytest.raises(ValueError, match="people store"):
        PrincipalResolver(_entra_config(jwks_url), claim_mapping=BY_EXTENSION)
    with pytest.raises(ValueError, match="only for an Entra"):
        PrincipalResolver(_config(jwks_url), role_source=FakePeople())


async def test_the_keycloak_path_is_unchanged_through_resolve_principal(keypair, jwks_url) -> None:
    principal = await PrincipalResolver(_config(jwks_url)).resolve_principal(
        sign_token(_key(keypair), default_claims(roles=["osprey-admin"]))
    )
    assert principal.roles == ["osprey-admin"]


# --- P10 part 2: the mapping from the environment the profile renders ---


def test_the_mapping_is_read_from_the_environment(monkeypatch) -> None:
    import json

    monkeypatch.setenv(
        "OSPREY_CLAIM_MAPPING",
        json.dumps({"tenant_id": TENANT, "client_id": GLASS, "clearance": {"claim": "c"}}),
    )
    assert ClaimMapping.from_env().tenant_id == TENANT
    monkeypatch.delenv("OSPREY_CLAIM_MAPPING")
    assert ClaimMapping.from_env() == ClaimMapping()


@pytest.mark.parametrize(
    "raw",
    ["{not json", '{"clearence": {"claim": "c"}}', f'{{"tenant_id": "{TENANT}"}}'],
    ids=["not-json", "unknown-key", "no-client"],
)
def test_a_mapping_in_the_environment_that_does_not_load_stops_the_start(monkeypatch, raw) -> None:
    """Never a silent fall back to the fixed names, which would be Keycloak-handled."""
    monkeypatch.setenv("OSPREY_CLAIM_MAPPING", raw)
    with pytest.raises(ValueError):
        ClaimMapping.from_env()
