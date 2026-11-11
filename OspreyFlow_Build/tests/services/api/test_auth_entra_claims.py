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
groups".

**Decided here (logged in `process/lanes/admin/SERVER_LOG.md`):** groups granting more than one
clearance, or more than one organisational unit, are **refused**, not resolved to the lowest —
`principal_auth` holds no marking scheme to order clearances by, and a person in two clearance
groups is a directory error for the operator to see, not one to guess past.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError
from services.api.auth import PrincipalResolutionError, PrincipalResolver
from services.api.config import ApiConfig

from principal_auth import ClaimMapping, CodesSource, ValueSource
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
CLIENT_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
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
        "oid": "50000000-0000-4000-8000-000000000001",
        "sub": "pairwise-subject-AbCdEf0123456789",
        "name": "Synthetic Analyst",
        "preferred_username": "synthetic.analyst@example.test",
        "roles": ["analyst"],
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not _ABSENT}


_ABSENT = object()

#: Each principal claim from a directory extension attribute.
BY_EXTENSION = ClaimMapping(
    tenant_id=TENANT,
    clearance=ValueSource(claim=f"{EXT}_clearance"),
    org_unit=ValueSource(claim=f"{EXT}_orgUnit"),
    handling_codes=CodesSource(claim=f"{EXT}_handlingCodes"),
)

#: Each principal claim from a table of Entra groups.
BY_GROUPS = ClaimMapping(
    tenant_id=TENANT,
    clearance=ValueSource(groups={G_OFFICIAL: "OFFICIAL", G_SENSITIVE: "OFFICIAL-SENSITIVE"}),
    org_unit=ValueSource(groups={G_UNIT_1: "unit-1", G_UNIT_2: "unit-2"}),
    handling_codes=CodesSource(groups={G_CODE_R: ["R"], G_CODES_ST: ["S", "T"]}),
)

#: A named claim and a group table in one mapping.
MIXED = ClaimMapping(
    tenant_id=TENANT,
    clearance=ValueSource(claim=f"{EXT}_clearance"),
    org_unit=ValueSource(groups={G_UNIT_1: "unit-1", G_UNIT_2: "unit-2"}),
    handling_codes=CodesSource(groups={G_CODE_R: ["R"]}),
)


def _entra_config(jwks_url: str) -> ApiConfig:
    return _config(jwks_url, oidc_issuer=ISSUER, oidc_audience=CLIENT_ID)


def _resolver(jwks_url: str, mapping: ClaimMapping) -> PrincipalResolver:
    return PrincipalResolver(_entra_config(jwks_url), claim_mapping=mapping)


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
    assert principal.id == "pairwise-subject-AbCdEf0123456789"
    assert principal.clearance == "OFFICIAL-SENSITIVE"
    assert principal.org_unit == "unit-2"
    assert principal.receivable_handling_codes == ["R", "S"]
    assert principal.roles == ["analyst"]


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
                "src1": {"endpoint": "https://graph.microsoft.com/v1.0/users/x/getMemberObjects"}
            },
        ),
    )
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


def test_the_settings_refuse_an_unknown_key() -> None:
    """A misspelt setting (`clearence`) must fail the install, not leave the default in place."""
    with pytest.raises(ValidationError):
        ClaimMapping.model_validate({"clearence": {"claim": f"{EXT}_clearance"}})


def test_the_settings_load_from_a_plain_mapping() -> None:
    """The shape a profile's settings will render (after P7): plain data, validated."""
    mapping = ClaimMapping.model_validate(
        {
            "tenant_id": TENANT,
            "clearance": {"claim": f"{EXT}_clearance"},
            "org_unit": {"groups": {G_UNIT_1: "unit-1"}},
            "handling_codes": {"groups": {G_CODE_R: ["R"]}},
        }
    )
    assert mapping.org_unit.groups == {G_UNIT_1: "unit-1"}


# --- the default mapping is today's fixed names, and the one construction path ---


def test_the_default_mapping_is_the_fixed_claim_names(keypair, jwks_url) -> None:
    """No mapping given: today's behaviour exactly (`test_auth.py`'s cases, unchanged)."""
    assert ClaimMapping() == ClaimMapping(
        clearance=ValueSource(claim="clearance"),
        org_unit=ValueSource(claim="org_unit"),
        handling_codes=CodesSource(claim="receivable_handling_codes"),
    )
    principal = PrincipalResolver(_config(jwks_url)).resolve(
        sign_token(_key(keypair), default_claims(receivable_handling_codes=["R"]))
    )
    assert (principal.clearance, principal.org_unit, principal.receivable_handling_codes) == (
        "OFFICIAL",
        "unit-1",
        ["R"],
    )


def test_the_default_mapping_does_not_read_entra_attributes(keypair, jwks_url) -> None:
    claims = default_claims(**{f"{EXT}_clearance": "OFFICIAL"})
    del claims["clearance"]
    with pytest.raises(PrincipalResolutionError):
        PrincipalResolver(_config(jwks_url)).resolve(sign_token(_key(keypair), claims))


async def test_the_owner_exchange_maps_claims_through_the_same_path(
    keypair, jwks_url, token_exchange_url: str, token_exchange_registry: TokenExchangeRegistry
) -> None:
    """ADR-043's one claims-construction path: a token got by exchange is mapped as a session's
    is, so two clearances are refused there too, never resolved by a second path."""
    token_exchange_registry.register(
        "owner-ok", entra_claims(sub="owner-ok", groups=[G_OFFICIAL, G_UNIT_1, G_CODE_R])
    )
    token_exchange_registry.register(
        "owner-two", entra_claims(sub="owner-two", groups=[G_OFFICIAL, G_SENSITIVE, G_UNIT_1])
    )
    config = _config(
        jwks_url,
        oidc_issuer=ISSUER,
        oidc_audience=CLIENT_ID,
        oidc_token_exchange_url=token_exchange_url,
        oidc_token_exchange_client_id=TOKEN_EXCHANGE_CLIENT_ID,
        oidc_token_exchange_client_secret=TOKEN_EXCHANGE_CLIENT_SECRET,
    )
    resolver = PrincipalResolver(config, claim_mapping=BY_GROUPS)
    try:
        ok = await resolver.resolve_for_owner("owner-ok")
        assert ok is not None
        assert (ok.clearance, ok.org_unit, ok.receivable_handling_codes) == (
            "OFFICIAL",
            "unit-1",
            ["R"],
        )
        assert await resolver.resolve_for_owner("owner-two") is None
    finally:
        await resolver.aclose()


def test_one_principal_construction_in_principal_auth() -> None:
    """`Principal(` is called in exactly one place in `principal_auth`, `principal_from_claims`."""
    source = (
        Path(__file__).resolve().parents[4] / "OspreyFlow_Core/packages/principal_auth/__init__.py"
    )
    tree = ast.parse(source.read_text())
    calls: list[str] = []
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Principal":
                    calls.append(fn.name)
    assert calls == ["principal_from_claims"]
