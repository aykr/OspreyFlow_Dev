"""The page service's own client in the realm, its secrets, and the fake provider's refusals
(`06_DECISIONS.md` ADR-152 decision 5 and ADR-050 Amendment 4; slice PL9a).

`osprey-pages` is the **confidential** client the `apps/pages` service signs people in with: the
authorisation-code flow with PKCE (S256), the standard flow alone, a refresh token kept on the server,
the exact redirect address `<origin>/session/callback`, the same claim mappers as the Glass's client and
the audience mapper that names the Conduit (without which the Conduit's `verify_aud` refuses every call
the service makes for the person). Its secret, and the secret that signs the service's session cookie,
are minted once by `apply` and kept across a re-apply in `deployment.env`, written nowhere else.

What a mistake would do, and the case that goes red (`CLAUDE.md` rules 12 and 15: each planted fault is
shown to the same check that passes the real client, so the check cannot be one that passes anything):

- a public client, or a second grant switched on, or a plain challenge allowed —
  `test_the_check_names_each_planted_fault` (and `test_the_pages_client_has_no_fault` for the real one);
- the audience mapper missing or naming something else —
  `test_the_check_names_each_planted_fault["the audience mapper removed"]`;
- a wildcard or another address among the redirects —
  `test_the_check_names_each_planted_fault["a wildcard redirect"]`;
- a client secret written into the realm document (it is set after import, through the admin API) —
  `test_the_check_names_each_planted_fault["a secret in the document"]`;
- the client added to the realm every deployment imports, which would change the GOV.UK demo's rendered
  realm and restart its identity provider — `test_an_existing_deployments_realm_document_is_unchanged`;
- registration that does not register it, or registers it twice, or prints its secret —
  `test_registration_registers_the_pages_client_on_an_existing_realm`,
  `test_registering_again_changes_nothing`, `test_a_deployment_without_the_secret_gets_no_pages_client`;
- an `apply` that mints no secret, or mints each time (so the client and the service disagree after the
  next apply), or writes one beside `deployment.env` —
  `test_apply_mints_both_secrets_once_and_keeps_them`, `test_a_reapply_that_re_mints_is_caught`,
  `test_no_secret_is_written_anywhere_but_deployment_env`;
- the fake provider that grants what Keycloak refuses (rule 15) —
  `test_the_fake_provider_refuses_what_keycloak_refuses`.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import stat
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import jwt
import pytest
import yaml
from harness import apply, keycloak_admin, register_sign_in
from harness.apply import stage_deployment
from harness.realm import (
    CONDUIT_CLIENT_ID,
    GLASS_CLIENT_ID,
    HARNESS_CLIENT_ID,
    PAGES_CLIENT_ID,
    PAGES_CLIENT_SECRET_KEY,
    PAGES_SESSION_SECRET_KEY,
    glass_client,
    pages_client,
    render_realm,
)

from schemas.deployment import OspreyConfig
from tools.layout import CORE
from tests.harness.fake_idp import FakeIdentityProvider
from tests.harness.test_named_render import _named_config
from tests.harness.test_register_sign_in import (
    ADMIN_PASSWORD,
    ISSUER,
    FakeKeycloak,
    _config,
    _env,
)

ORIGIN = "http://localhost:9999"  # `_config()`'s public origin
CALLBACK = f"{ORIGIN}/session/callback"


@pytest.fixture
def keycloak(monkeypatch: pytest.MonkeyPatch) -> FakeKeycloak:
    fake = FakeKeycloak()
    monkeypatch.setattr(keycloak_admin, "_call", fake.call)
    return fake


def _secret() -> str:
    """Made when the test runs: never a value anyone could use, written nowhere."""
    import secrets

    return secrets.token_urlsafe(32)


# --- the client as the realm describes it ---


def faults(client: dict[str, Any], origin: str = ORIGIN) -> list[str]:
    """What is wrong with a rendering of the page service's client, in words; empty when nothing."""
    found: list[str] = []
    attributes = client.get("attributes", {})
    if client.get("clientId") != PAGES_CLIENT_ID:
        found.append("the client is not named osprey-pages")
    if client.get("publicClient") is not False:
        found.append("the client is not confidential")
    if client.get("standardFlowEnabled") is not True:
        found.append("the standard flow is not on")
    for grant in ("implicitFlowEnabled", "directAccessGrantsEnabled", "serviceAccountsEnabled"):
        if client.get(grant):
            found.append(f"{grant} is on: the standard flow alone")
    if attributes.get("pkce.code.challenge.method") != "S256":
        found.append("PKCE S256 is not required")
    if attributes.get("use.refresh.tokens") != "true":
        found.append("refresh tokens are not on (the server renews with one)")
    if client.get("redirectUris") != [f"{origin}/session/callback"]:
        found.append("the redirect addresses are not exactly <origin>/session/callback")
    if any("*" in uri for uri in client.get("redirectUris", [])):
        found.append("a redirect address holds a wildcard")
    if attributes.get("post.logout.redirect.uris") != f"{origin}/":
        found.append("the post-logout address is not <origin>/")
    if "secret" in client:
        found.append("a secret is in the document (it is set through the admin API)")
    mappers = {m["name"]: m for m in client.get("protocolMappers", [])}
    audience = [m for m in mappers.values() if m["protocolMapper"] == "oidc-audience-mapper"]
    if not any(
        m["config"].get("included.custom.audience") == CONDUIT_CLIENT_ID
        and m["config"].get("access.token.claim") == "true"
        for m in audience
    ):
        found.append("no audience mapper names the Conduit in the access token")
    glass_claims = {
        m["name"]: m
        for m in glass_client(_config())["protocolMappers"]
        if m["protocolMapper"] == "oidc-usermodel-attribute-mapper"
    }
    for name in glass_claims:
        if name not in mappers:
            found.append(f"the claim mapper {name} is missing")
        elif mappers[name] != glass_claims[name]:
            found.append(f"the claim mapper {name} differs from the Glass's")
    return found


def test_the_pages_client_has_no_fault() -> None:
    client = pages_client(_config())
    assert faults(client) == []
    assert client["publicClient"] is False
    assert client["standardFlowEnabled"] is True
    assert client["redirectUris"] == [CALLBACK]


def test_the_pages_client_is_the_deployments_own_origin_not_a_fixed_one() -> None:
    config = OspreyConfig.model_validate(
        yaml.safe_load("network:\n  public_origin: https://osprey.example.org\n")
    )
    client = pages_client(config)
    assert client["redirectUris"] == ["https://osprey.example.org/session/callback"]
    assert faults(client, "https://osprey.example.org") == []


def _without_audience(client: dict[str, Any]) -> None:
    client["protocolMappers"] = [
        m for m in client["protocolMappers"] if m["protocolMapper"] != "oidc-audience-mapper"
    ]


def _other_audience(client: dict[str, Any]) -> None:
    for m in client["protocolMappers"]:
        if m["protocolMapper"] == "oidc-audience-mapper":
            m["config"]["included.custom.audience"] = "account"


def _audience_in_the_id_token_only(client: dict[str, Any]) -> None:
    for m in client["protocolMappers"]:
        if m["protocolMapper"] == "oidc-audience-mapper":
            m["config"]["access.token.claim"] = "false"


PLANTS: dict[str, Callable[[dict[str, Any]], None]] = {
    "publicClient true": lambda c: c.update(publicClient=True),
    "the standard flow off": lambda c: c.update(standardFlowEnabled=False),
    "direct access grants on": lambda c: c.update(directAccessGrantsEnabled=True),
    "a service account on": lambda c: c.update(serviceAccountsEnabled=True),
    "the implicit flow on": lambda c: c.update(implicitFlowEnabled=True),
    "a plain challenge allowed": lambda c: c["attributes"].pop("pkce.code.challenge.method"),
    "refresh tokens off": lambda c: c["attributes"].update({"use.refresh.tokens": "false"}),
    "a wildcard redirect": lambda c: c.update(redirectUris=[f"{ORIGIN}/*"]),
    "another address beside the callback": lambda c: c["redirectUris"].append("http://evil.test/"),
    "the callback on another origin": lambda c: c.update(
        redirectUris=["http://localhost:1/session/callback"]
    ),
    "a secret in the document": lambda c: c.update(secret="planted-in-the-document"),
    "the audience mapper removed": _without_audience,
    "the audience naming another client": _other_audience,
    "the audience in the ID token only": _audience_in_the_id_token_only,
    "a claim mapper removed": lambda c: c["protocolMappers"].pop(0),
}


@pytest.mark.parametrize("plant", list(PLANTS))
def test_the_check_names_each_planted_fault(plant: str) -> None:
    """The check that passes the real client goes red on each plant, so it is not one that passes
    anything (rule 15). The audience-mapper plant is the one the ADR names."""
    client = copy.deepcopy(pages_client(_config()))
    assert faults(client) == []
    PLANTS[plant](client)
    assert faults(client), f"the check let '{plant}' through"


def test_an_existing_deployments_realm_document_is_unchanged() -> None:
    """The GOV.UK demo is protected: the realm every deployment imports (`realm.json`) gains no
    client, because Keycloak's own container would restart for a changed document. The client is
    registered through the admin API instead (`register_sign_in`), beside the Glass and Superset."""
    clients = {c["clientId"] for c in render_realm(_config(), demo_analyst=True)["clients"]}
    assert PAGES_CLIENT_ID not in clients
    assert clients == {CONDUIT_CLIENT_ID, "osprey-unprivileged", GLASS_CLIENT_ID, HARNESS_CLIENT_ID}


# --- registered on an existing realm ---


def _pages_clients(keycloak: FakeKeycloak) -> list[dict[str, Any]]:
    return [c for c in keycloak.clients.values() if c["clientId"] == PAGES_CLIENT_ID]


def test_registration_registers_the_pages_client_on_an_existing_realm(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    secret = _secret()
    env = _env(tmp_path, f"{PAGES_CLIENT_SECRET_KEY}={secret}")
    lines = register_sign_in.register(
        issuer=ISSUER, realm="osprey", env_path=env, config=_config()
    )
    (client,) = _pages_clients(keycloak)
    assert client["secret"] == secret, "Keycloak holds the secret the deployment's file names"
    stored = {k: v for k, v in client.items() if k not in ("id", "secret")}
    assert stored == pages_client(_config()), "exactly the client the realm module describes"
    assert faults({k: v for k, v in client.items() if k not in ("id", "secret")}) == []
    assert any(line.startswith(f"sign-in client {PAGES_CLIENT_ID}") for line in lines)
    assert secret not in "\n".join(lines), "a secret is never printed"


def test_a_server_without_demo_accounts_gets_it_too(keycloak: FakeKeycloak) -> None:
    """One function for every deployment (`ensure_identity`): Small, and a cluster's install."""
    token = keycloak_admin.admin_token(
        issuer=ISSUER, admin_user="admin", admin_password=ADMIN_PASSWORD
    )
    secret = _secret()
    lines = register_sign_in.ensure_identity(
        issuer=ISSUER, realm="osprey", token=token, config=_config(),
        values={PAGES_CLIENT_SECRET_KEY: secret},
    )  # fmt: skip
    (client,) = _pages_clients(keycloak)
    assert client["publicClient"] is False and client["secret"] == secret
    assert secret not in "\n".join(lines)


def test_registering_again_changes_nothing(keycloak: FakeKeycloak, tmp_path: Path) -> None:
    secret = _secret()
    env = _env(tmp_path, f"{PAGES_CLIENT_SECRET_KEY}={secret}")
    register_sign_in.register(issuer=ISSUER, realm="osprey", env_path=env, config=_config())
    before = copy.deepcopy(_pages_clients(keycloak))
    keycloak.calls.clear()

    lines = register_sign_in.register(
        issuer=ISSUER, realm="osprey", env_path=env, config=_config()
    )
    assert _pages_clients(keycloak) == before, "one client, as it was"
    writes = [
        (verb, path)
        for verb, path in keycloak.calls
        if verb in ("POST", "PUT", "DELETE") and "/clients" in path and "cid-" not in path
    ]
    assert writes == [], "no second registration"
    assert f"sign-in client {PAGES_CLIENT_ID}: already registered" in lines


def test_a_deployment_without_the_secret_gets_no_pages_client(
    keycloak: FakeKeycloak, tmp_path: Path
) -> None:
    """An existing deployment, before its next apply has written the secret: registration leaves it
    as it is (Superset's way), and the demo changes only when apply is run on it."""
    register_sign_in.register(
        issuer=ISSUER, realm="osprey", env_path=_env(tmp_path), config=_config()
    )
    assert _pages_clients(keycloak) == []


# --- minted by apply, kept across a re-apply, written to deployment.env only ---


def _stage(tmp_path: Path, previous_env: str = "") -> tuple[Path, dict[str, str]]:
    config, path = _named_config(tmp_path)
    stage = path.parent.parent / ".alpha.staging"
    stage_deployment(
        config, path, stage, realm="osprey", demo_analyst=True, images_from=None,
        previous_env=previous_env, environ={},
    )  # fmt: skip
    text = (stage / "deployment.env").read_text(encoding="utf-8")
    return stage, apply._env_pairs(text)


def _kept(first: dict[str, str], second: dict[str, str]) -> bool:
    keys = (PAGES_CLIENT_SECRET_KEY, PAGES_SESSION_SECRET_KEY)
    return all(first.get(k) and first.get(k) == second.get(k) for k in keys)


def test_apply_mints_both_secrets_once_and_keeps_them(tmp_path: Path) -> None:
    stage, first = _stage(tmp_path / "one")
    client_secret, session_secret = first[PAGES_CLIENT_SECRET_KEY], first[PAGES_SESSION_SECRET_KEY]
    assert len(client_secret) >= 32 and len(session_secret) >= 32, "the service refuses less"
    assert client_secret != session_secret, "two secrets, two purposes"
    assert client_secret != first["OSPREY_OIDC_CLIENT_SECRET"]
    assert stat.S_IMODE((stage / "deployment.env").stat().st_mode) == 0o600
    env_text = (stage / "deployment.env").read_text(encoding="utf-8")
    assert env_text.count(f"{PAGES_CLIENT_SECRET_KEY}=") == 1
    assert env_text.count(f"{PAGES_SESSION_SECRET_KEY}=") == 1

    _, second = _stage(tmp_path / "two", previous_env=env_text)
    assert _kept(first, second), "a second apply keeps both"
    assert second[PAGES_CLIENT_SECRET_KEY] == client_secret
    assert second[PAGES_SESSION_SECRET_KEY] == session_secret

    _, other = _stage(tmp_path / "three")
    assert not _kept(first, other), "a fresh deployment mints its own: nothing is derived"


def test_a_reapply_that_re_mints_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The planted defect, at the real call site: `apply`'s own keep step does nothing, so a re-apply
    writes new secrets while Keycloak and the running service still hold the old ones."""
    _, first = _stage(tmp_path / "one")
    env_text = "".join(f"{k}={v}\n" for k, v in first.items())
    monkeypatch.setattr(apply, "keep_existing_secrets", lambda new, previous: new)
    _, second = _stage(tmp_path / "two", previous_env=env_text)
    assert not _kept(first, second), "the check sees a re-mint"


def test_an_existing_deployment_gains_exactly_the_two_keys(tmp_path: Path) -> None:
    """What the owner is told about the GOV.UK demo: on its next apply its `deployment.env` gains the
    two keys, once, and nothing it already holds changes."""
    _, fresh = _stage(tmp_path / "fresh")
    before = {
        k: v for k, v in fresh.items() if k not in (PAGES_CLIENT_SECRET_KEY, PAGES_SESSION_SECRET_KEY)
    }
    previous = "".join(f"{k}={v}\n" for k, v in before.items())
    _, after = _stage(tmp_path / "later", previous_env=previous)
    assert set(after) - set(before) == {PAGES_CLIENT_SECRET_KEY, PAGES_SESSION_SECRET_KEY}
    assert {k: after[k] for k in before} == before, "every value it held is kept as it was"


def _files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def test_no_secret_is_written_anywhere_but_deployment_env(tmp_path: Path) -> None:
    stage, values = _stage(tmp_path)
    secrets_ = (values[PAGES_CLIENT_SECRET_KEY], values[PAGES_SESSION_SECRET_KEY])
    holders = []
    for path in _files(stage):
        data = path.read_bytes()
        if any(secret.encode() in data for secret in secrets_):
            holders.append(path.name)
    assert holders == ["deployment.env"], f"a secret is written in {holders}"
    # The realm document names the client without a secret.
    realm_text = (stage / "realm.json").read_text(encoding="utf-8")
    assert PAGES_CLIENT_SECRET_KEY not in realm_text


def test_the_two_names_are_the_services_own_settings() -> None:
    """The service reads `OSPREY_PAGES_CLIENT_SECRET` and `OSPREY_PAGES_SESSION_SECRET` (`apps/pages`
    `config.ts`): a rename on one side would leave the service refusing to start."""
    config = (CORE / "apps" / "pages" / "server" / "config.ts").read_text(encoding="utf-8")
    assert PAGES_CLIENT_SECRET_KEY == "OSPREY_PAGES_CLIENT_SECRET" and PAGES_CLIENT_SECRET_KEY in config
    assert PAGES_SESSION_SECRET_KEY == "OSPREY_PAGES_SESSION_SECRET" and PAGES_SESSION_SECRET_KEY in config
    assert PAGES_CLIENT_ID == "osprey-pages"


# --- the Python fake provider refuses what Keycloak refuses (rule 15) ---


def _s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@pytest.fixture
def confidential() -> Iterator[tuple[FakeIdentityProvider, str]]:
    secret = _secret()
    provider = FakeIdentityProvider(
        client_id=PAGES_CLIENT_ID,
        redirect_uri=CALLBACK,
        users={"alex": ["analyst"]},
        client_secret=secret,
        code_ttl_seconds=30,
        access_token_audience=CONDUIT_CLIENT_ID,
    )
    try:
        yield provider, secret
    finally:
        provider.stop()


def _code(provider: FakeIdentityProvider, verifier: str) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": PAGES_CLIENT_ID,
            "redirect_uri": CALLBACK,
            "scope": "openid",
            "state": "s",
            "nonce": "n",
            "code_challenge": _s256(verifier),
            "code_challenge_method": "S256",
        }
    )
    back = provider.authorise(
        f"{provider.issuer}/protocol/openid-connect/auth?{query}", username="alex"
    )
    return urllib.parse.parse_qs(urllib.parse.urlparse(back).query)["code"][0]


def _exchange(
    provider: FakeIdentityProvider, form: dict[str, str], headers: dict[str, str] | None = None
) -> tuple[int, dict[str, Any]]:
    import json

    request = urllib.request.Request(
        f"{provider.issuer}/protocol/openid-connect/token",
        data=urllib.parse.urlencode(form).encode(),
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310 - the loopback fake
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_the_fake_provider_refuses_what_keycloak_refuses(
    confidential: tuple[FakeIdentityProvider, str],
) -> None:
    provider, secret = confidential
    verifier = "v" * 43
    code = _code(provider, verifier)
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": CALLBACK,
        "code_verifier": verifier,
        "client_id": PAGES_CLIENT_ID,
    }

    # Client authentication, by form and by Basic header: wrong, missing, empty.
    for wrong in (
        {**form, "client_secret": _secret()},
        {**form, "client_secret": ""},
        form,
    ):
        status, body = _exchange(provider, wrong)
        assert (status, body["error"]) == (401, "invalid_client")
    basic = base64.b64encode(f"{PAGES_CLIENT_ID}:{_secret()}".encode()).decode()
    status, body = _exchange(provider, {**form, "client_id": ""}, {"Authorization": f"Basic {basic}"})
    assert (status, body["error"]) == (401, "invalid_client")

    # Authentication failed before the code was looked at, so the code is not spent: a wrong
    # verifier with the right secret now spends it, and the right one after that is refused.
    status, body = _exchange(provider, {**form, "client_secret": secret, "code_verifier": "w" * 43})
    assert (status, body["error"]) == (400, "invalid_grant")
    status, body = _exchange(provider, {**form, "client_secret": secret})
    assert (status, body["error"]) == (400, "invalid_grant"), "single use, even after a wrong try"

    # A wrong redirect address at the token endpoint, a missing verifier, an expired code.
    for change in ({"redirect_uri": f"{ORIGIN}/elsewhere"}, {"code_verifier": ""}):
        status, body = _exchange(
            provider,
            {**form, "code": _code(provider, verifier), "client_secret": secret, **change},
        )
        assert (status, body["error"]) == (400, "invalid_grant")
    stale = _code(provider, verifier)
    provider.advance(31)
    status, body = _exchange(provider, {**form, "code": stale, "client_secret": secret})
    assert (status, body["error"]) == (400, "invalid_grant"), "the code expired"

    # And what it grants: the right secret (either way), a real signed access token for the Conduit.
    fresh = _code(provider, verifier)
    status, body = _exchange(provider, {**form, "code": fresh, "client_secret": secret})
    assert status == 200
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["aud"] == CONDUIT_CLIENT_ID and claims["iss"] == provider.issuer
    assert body["access_token"].count(".") == 2, "a JWT, not an opaque string"
    second = _code(provider, verifier)
    token = base64.b64encode(f"{PAGES_CLIENT_ID}:{secret}".encode()).decode()
    status, _ = _exchange(
        provider, {**form, "code": second, "client_id": ""}, {"Authorization": f"Basic {token}"}
    )
    assert status == 200
    # The provider says what it is (the page service reads the discovery document).
    import json

    with urllib.request.urlopen(  # noqa: S310 - the loopback fake
        f"{provider.issuer}/.well-known/openid-configuration"
    ) as response:
        assert json.loads(response.read())["issuer"] == provider.issuer
