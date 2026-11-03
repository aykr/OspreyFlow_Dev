"""Sign-in through the organisation's identity provider, against real Keycloaks (ADR-114 Amendment
33 decision 4; drop 2, unit 7).

**The organisation is a second real Keycloak** (26.0, the deployment's own pinned image), served over
HTTPS with a certificate from a throwaway organisation CA (`tls_fixtures.py`). Rule 15: a fixture for
an external dependency models its refusals, and a real Keycloak refuses what Entra ID refuses here —
an authorisation request whose `redirect_uri` is not registered **exactly**, and a token request
with the wrong client secret — and the deployment's Keycloak, a real one too, refuses a TLS chain
its truststore does not reach. Entra ID itself is not tested: there is no tenant to test against
(Amendment 33 "Drop 2 as built" says what the client must do).

The deployment's Keycloak runs the rendered realm (`harness.realm.render_realm`), is given the
truststore exactly as the rendered compose file gives it (`KC_TRUSTSTORE_PATHS` and the CA's
mount, read from `render`), and is configured by the product's own registration
(`harness.register_sign_in.ensure_identity`, what `ospreyflow install` and `ospreyflow
repair-sign-in` run). It serves HTTPS itself here, where a deployment's sits behind Caddy; the
broker's behaviour does not depend on which.

The browser is scripted: the Glass's own authorisation request (`osprey-glass`, PKCE S256, and the
`kc_idp_hint` *Continue with organisation sign-in* adds, `apps/workspace/src/auth/userManager.ts`),
each redirect followed, the organisation's own sign-in form posted, the code exchanged as the Glass
exchanges it, and the access token resolved by the Conduit's own `principal_auth.PrincipalResolver`.
Every name resolves to 127.0.0.1 in this process only (`harness.site.answer_the_deployment_here`);
every port is a free high port of 127.0.0.1 — nothing here reaches 80, 443, 8080, 8081 or 2480, nor
any deployment of this machine. Every container and the network are removed afterwards.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import hashlib
import html
import json
import re
import secrets
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from harness import keycloak_admin, site
from harness.keycloak_admin import RealmConfigurationFailed
from harness.realm import (
    CONDUIT_CLIENT_ID,
    GLASS_CLIENT_ID,
    ORGANISATION_ARRIVAL_ATTRIBUTES,
    organisation_redirect_uris,
    render_realm_json,
)
from harness.register_sign_in import ensure_identity
from harness.render import KEYCLOAK_TRUSTSTORE_PATH, render
from principal_auth import OidcResolverSettings, PrincipalResolver

from schemas.deployment import OspreyConfig

from .tls_fixtures import HOST, NAMES, Authority, docker, key_pem, pem

KEYCLOAK_IMAGE = "quay.io/keycloak/keycloak:26.0"
ORG_HOST = "login.example.internal"
ORG_REALM = "org"
ORG_CLIENT = "osprey-broker"
ALIAS = "org"
PERSON = {"username": "pat.example", "password": "a-throwaway-password-1",
          "email": "pat.example@example.internal", "firstName": "Pat", "lastName": "Example"}  # fmt: skip


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass
class Keycloak:
    name: str
    port: int
    host: str
    admin_password: str

    @property
    def origin(self) -> str:
        return f"https://{self.host}:{self.port}"

    def logs(self) -> str:
        done = docker("logs", self.name, check=False)
        return done.stdout + done.stderr


def _write(path: Path, data: bytes, mode: int = 0o644) -> Path:
    path.write_bytes(data)
    # Read by Keycloak's own account inside the container: a throwaway test key, never a real one.
    path.chmod(mode)
    return path


def _start_keycloak(
    network: str, *, host: str, folder: Path, certificate: Path, key: Path,
    extra_args: list[str], environment: dict[str, str], volumes: list[str],
    command: list[str], port: int | None = None,
) -> Keycloak:  # fmt: skip
    name = f"osprey-test-idp-{uuid.uuid4().hex[:8]}"
    port = port or _free_port()
    password = secrets.token_urlsafe(16)
    argv = ["run", "-d", "--name", name, "--network", network, "--network-alias", host,
            "-p", f"127.0.0.1:{port}:{port}",
            "-v", f"{certificate}:/certs/cert.pem:ro", "-v", f"{key}:/certs/key.pem:ro",
            "-e", "KC_BOOTSTRAP_ADMIN_USERNAME=admin", "-e", f"KC_BOOTSTRAP_ADMIN_PASSWORD={password}"]  # fmt: skip
    for variable, value in environment.items():
        argv += ["-e", f"{variable}={value}"]
    for volume in volumes:
        argv += ["-v", volume]
    argv += [KEYCLOAK_IMAGE, *command, f"--https-port={port}", "--http-enabled=false",
             "--https-certificate-file=/certs/cert.pem", "--https-certificate-key-file=/certs/key.pem",
             f"--hostname=https://{host}:{port}", *extra_args]  # fmt: skip
    docker(*argv)
    return Keycloak(name, port, host, password)


def _wait_ready(keycloak: Keycloak, seconds: int = 180) -> None:
    deadline = time.monotonic() + seconds
    url = f"{keycloak.origin}/realms/master/.well-known/openid-configuration"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as answer:
                if answer.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise AssertionError(f"{keycloak.name} never became ready:\n{keycloak.logs()[-3000:]}")


def _admin(keycloak: Keycloak) -> str:
    return keycloak_admin.admin_token(
        issuer=keycloak.origin, admin_user="admin", admin_password=keycloak.admin_password
    )


def _organisation_realm(org: Keycloak, redirect: str, logout: str, secret: str) -> None:
    """The organisation's own provider: a realm, OspreyFlow's application registered with the two
    addresses the install prints, and one person of the test group."""
    token = _admin(org)
    status, body = keycloak_admin._call(
        f"{org.origin}/admin/realms", token=token,
        data={"realm": ORG_REALM, "enabled": True, "sslRequired": "external"},
    )  # fmt: skip
    assert status == 201, (status, body)
    status, body = keycloak_admin._call(
        f"{org.origin}/admin/realms/{ORG_REALM}/clients", token=token,
        data={"clientId": ORG_CLIENT, "enabled": True, "publicClient": False, "secret": secret,
              "standardFlowEnabled": True, "directAccessGrantsEnabled": False,
              "redirectUris": [redirect],
              "attributes": {"post.logout.redirect.uris": logout,
                             "pkce.code.challenge.method": "S256"}},
    )  # fmt: skip
    assert status == 201, (status, body)
    person = {k: v for k, v in PERSON.items() if k != "password"}
    status, body = keycloak_admin._call(
        f"{org.origin}/admin/realms/{ORG_REALM}/users", token=token,
        data={**person, "enabled": True, "emailVerified": True,
              "credentials": [{"type": "password", "value": PERSON["password"], "temporary": False}]},
    )  # fmt: skip
    assert status == 201, (status, body)


def _org_client(org: Keycloak, **changes: Any) -> None:
    """Change OspreyFlow's application as the organisation registered it."""
    token = _admin(org)
    status, found = keycloak_admin._call(
        f"{org.origin}/admin/realms/{ORG_REALM}/clients?clientId={ORG_CLIENT}", token=token
    )
    assert status == 200 and found
    status, body = keycloak_admin._call(
        f"{org.origin}/admin/realms/{ORG_REALM}/clients/{found[0]['id']}", token=token,
        data={**found[0], **changes}, method="PUT",
    )  # fmt: skip
    assert status in (200, 204), (status, body)


@dataclass
class Stack:
    org: Keycloak
    deployment: Keycloak
    #: A second deployment Keycloak whose truststore holds another CA, not the organisation's.
    elsewhere: Keycloak
    config: OspreyConfig
    elsewhere_config: OspreyConfig
    values: dict[str, str]
    org_secret: str
    redirect: str
    logout: str


def _config(port: int, folder: Path, ca: Path) -> OspreyConfig:
    return OspreyConfig.model_validate({
        "profile": "small",
        "network": {"public_origin": f"https://{HOST}:{port}",
                    "tls": {"certificate": str(folder / "osprey.crt"),
                            "key": str(folder / "osprey.key"), "ca": str(ca)}},
        "governance": {"organisation_sign_in": ALIAS,
                       "organisation_provider": {
                           "label": "Example Organisation account",
                           "issuer": f"https://{ORG_HOST}:{{org_port}}/realms/{ORG_REALM}",
                           "client_id": ORG_CLIENT}},
    })  # fmt: skip


def _with_issuer(config: OspreyConfig, issuer: str) -> OspreyConfig:
    raw = config.model_dump(mode="json")
    raw["governance"]["organisation_provider"]["issuer"] = issuer
    return OspreyConfig.model_validate(raw)


def _rendered_keycloak(config: OspreyConfig) -> dict[str, Any]:
    compose = yaml.safe_load(
        render(config, resolver=lambda _image: "sha256:" + "0" * 64).artefacts["compose.yaml"]
    )
    return dict(compose["services"]["keycloak"])


def _truststore(config: OspreyConfig) -> tuple[dict[str, str], list[str]]:
    """The truststore as the rendered compose file gives it to Keycloak: its environment variable
    and the CA's read-only mount, and nothing else of the rendered service."""
    service = _rendered_keycloak(config)
    environment = {
        k: v for k, v in service["environment"].items() if k == "KC_TRUSTSTORE_PATHS"
    }
    volumes = [v for v in service["volumes"] if KEYCLOAK_TRUSTSTORE_PATH in v]
    return environment, volumes


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    folder = tmp_path_factory.mktemp("organisation-sign-in")
    root = Authority.root("Example Organisation Root CA (test only)")
    issuing = root.intermediate()
    leaf, leaf_key = issuing.issue(NAMES)
    _write(folder / "osprey.crt", pem(leaf, issuing.cert))
    _write(folder / "osprey.key", key_pem(leaf_key))
    ca = _write(folder / "org-root.pem", pem(root.cert))
    org_leaf, org_key = issuing.issue([ORG_HOST])
    org_cert = _write(folder / "login.crt", pem(org_leaf, issuing.cert))
    org_key_file = _write(folder / "login.key", key_pem(org_key))
    # Another organisation's CA: a truststore holding it does not reach the organisation's chain.
    other = Authority.root("Another Organisation Root CA (test only)")
    (folder / "other").mkdir()
    other_ca = _write(folder / "other" / "org-root.pem", pem(other.cert))

    network = f"osprey-test-idp-{uuid.uuid4().hex[:8]}"
    docker("network", "create", network)
    started: list[Keycloak] = []
    # `answer_the_deployment_here` changes this process's resolver and trust store; every test
    # after this module gets them back as they were.
    patched = pytest.MonkeyPatch()
    patched.setattr(socket, "getaddrinfo", socket.getaddrinfo)
    patched.setattr(ssl, "create_default_context", ssl.create_default_context)
    patched.setattr(ssl, "_create_default_https_context", ssl._create_default_https_context)
    patched.setattr(site, "_HERE", {})
    patched.setattr(site, "_TRUSTED", [])
    patched.setattr(site, "_answered", False)
    try:
        deployment_port = _free_port()
        config = _config(deployment_port, folder, ca)
        elsewhere_config = _config(deployment_port, folder, other_ca)
        realm_file = folder / "realm.json"
        realm_file.write_text(render_realm_json(config), encoding="utf-8")
        realm_file.chmod(0o644)

        def org() -> Keycloak:
            return _start_keycloak(network, host=ORG_HOST, folder=folder, certificate=org_cert,
                                   key=org_key_file, extra_args=[], environment={}, volumes=[],
                                   command=["start-dev"])  # fmt: skip

        def deployment(at: OspreyConfig, port: int | None) -> Keycloak:
            environment, volumes = _truststore(at)
            return _start_keycloak(
                network, host=f"id.{HOST}", folder=folder, certificate=folder / "osprey.crt",
                key=folder / "osprey.key", extra_args=["--import-realm"],
                environment=environment,
                volumes=[*volumes, f"{realm_file}:/opt/keycloak/data/import/realm.json:ro"],
                command=["start-dev", "--features=token-exchange"], port=port,
            )  # fmt: skip

        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            futures = [pool.submit(org), pool.submit(deployment, config, deployment_port),
                       pool.submit(deployment, elsewhere_config, None)]  # fmt: skip
            for future in futures:
                started.append(future.result())
        org_kc, deployment_kc, elsewhere_kc = started

        # Every name in this process resolves to 127.0.0.1, each Keycloak's own certificate trusted
        # through the organisation's CA — the product's own host-tool path (Amendment 33 decision 2).
        site.answer_the_deployment_here(config)
        site._HERE[ORG_HOST] = "127.0.0.1"
        for keycloak in started:
            _wait_ready(keycloak)

        issuer = f"https://{ORG_HOST}:{org_kc.port}/realms/{ORG_REALM}"
        config = _with_issuer(config, issuer)
        elsewhere_config = _with_issuer(elsewhere_config, issuer)
        redirect, logout = organisation_redirect_uris(config)
        org_secret = secrets.token_urlsafe(24)
        _organisation_realm(org_kc, redirect, logout, org_secret)
        values = {"OSPREY_OIDC_CLIENT_SECRET": secrets.token_urlsafe(24),
                  "OSPREY_ORG_SIGN_IN_SECRET": org_secret}  # fmt: skip
        yield Stack(org_kc, deployment_kc, elsewhere_kc, config, elsewhere_config, values,
                    org_secret, redirect, logout)  # fmt: skip
    finally:
        for keycloak in started:
            docker("rm", "-f", "-v", keycloak.name, check=False)
        docker("network", "rm", network, check=False)
        patched.undo()
        urllib.request.install_opener(None)


# ---- the browser, scripted ----------------------------------------------------------------------


@dataclass
class Outcome:
    """Where a sign-in ended: the Glass's tokens, or the page that stopped it."""

    tokens: dict[str, Any] | None
    #: Every address the browser was sent to, in order.
    visited: list[str]
    stopped_at: httpx.Response | None = None


def _form(page: str) -> tuple[str, dict[str, str]]:
    """The first form on a Keycloak page: its action and its named inputs' values."""
    match = re.search(r'<form[^>]*action="([^"]+)"', page)
    assert match, page[:2000]
    inputs = {
        name: html.unescape(value)
        for name, value in re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', page)
    }
    return html.unescape(match.group(1)), inputs


def sign_in(stack: Stack, client: httpx.Client | None = None) -> Outcome:
    """The Glass's *Continue with organisation sign-in*, as a browser carries it out."""
    origin = stack.config.network.public_origin
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    query = urllib.parse.urlencode({
        "client_id": GLASS_CLIENT_ID, "response_type": "code", "scope": "openid",
        "redirect_uri": f"{origin}/", "state": secrets.token_urlsafe(8),
        "code_challenge": challenge.decode(), "code_challenge_method": "S256",
        "kc_idp_hint": ALIAS,
    })  # fmt: skip
    url = f"{stack.deployment.origin}/realms/osprey/protocol/openid-connect/auth?{query}"
    browser = client or httpx.Client(verify=ssl.create_default_context(), timeout=30)
    visited: list[str] = []
    method, data = "GET", None
    for _ in range(20):
        visited.append(url)
        if url.startswith(f"{origin}/"):
            code = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["code"][0]
            answer = browser.post(
                f"{stack.deployment.origin}/realms/osprey/protocol/openid-connect/token",
                data={"grant_type": "authorization_code", "client_id": GLASS_CLIENT_ID,
                      "code": code, "redirect_uri": f"{origin}/", "code_verifier": verifier},
            )  # fmt: skip
            assert answer.status_code == 200, answer.text
            return Outcome(answer.json(), visited)
        response = browser.request(method, url, data=data)
        method, data = "GET", None
        if response.is_redirect:
            url = urllib.parse.urljoin(url, response.headers["location"])
            continue
        page = response.text
        if response.status_code == 200 and 'name="password"' in page:
            # The organisation's own sign-in page.
            action, _inputs = _form(page)
            url, method = urllib.parse.urljoin(url, action), "POST"
            data = {"username": PERSON["username"], "password": PERSON["password"]}
            continue
        return Outcome(None, visited, response)
    raise AssertionError(f"the sign-in never ended: {visited}")


def _said(outcome: Outcome) -> str:
    """The words of the page a sign-in stopped at, for a failure's message."""
    if outcome.stopped_at is None:
        return ""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", outcome.stopped_at.text, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())[:600]


def _claims(token: str) -> dict[str, Any]:
    body = token.split(".")[1]
    return dict(json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))))


def _principal(stack: Stack, token: str) -> Any:
    issuer = f"{stack.deployment.origin}/realms/osprey"
    resolver = PrincipalResolver(OidcResolverSettings(
        oidc_jwks_url=f"{issuer}/protocol/openid-connect/certs",
        oidc_audience=CONDUIT_CLIENT_ID, oidc_issuer=issuer,
    ))  # fmt: skip
    return resolver.resolve(token)


def _register(stack: Stack, values: dict[str, str] | None = None) -> list[str]:
    """What `ospreyflow install` and `ospreyflow repair-sign-in` run against the identity
    provider."""
    return ensure_identity(
        issuer=stack.deployment.origin, realm="osprey", token=_admin(stack.deployment),
        config=stack.config, values=values or stack.values,
    )  # fmt: skip


def _forget(stack: Stack, username: str) -> None:
    """Remove the person from the deployment's realm, so the next sign-in is their first again."""
    token = _admin(stack.deployment)
    base = f"{stack.deployment.origin}/admin/realms/osprey/users"
    status, found = keycloak_admin._call(f"{base}?username={username}&exact=true", token=token)
    for user in found if status == 200 else []:
        keycloak_admin._call(f"{base}/{user['id']}", token=token, method="DELETE")


# ---- the tests ----------------------------------------------------------------------------------


def test_the_printed_redirect_uri_is_the_one_keycloak_sends(stack: Stack) -> None:
    """The address the install prints for the organisation to register is the one the deployment's
    Keycloak sends — and the organisation's provider, like Entra ID, refuses any other: here, the
    application registered with a trailing slash too many."""
    lines = _register(stack)
    assert any(stack.redirect in line and stack.logout in line for line in lines), lines
    outcome = sign_in(stack)
    assert outcome.tokens is not None, (outcome.visited, outcome.stopped_at and outcome.stopped_at.text[:1500])
    sent = [u for u in outcome.visited if u.startswith(f"https://{ORG_HOST}:")]
    asked = urllib.parse.parse_qs(urllib.parse.urlsplit(sent[0]).query)
    assert asked["redirect_uri"] == [stack.redirect]
    # PKCE on the organisation's side too (the provider is configured for S256).
    assert asked["code_challenge_method"] == ["S256"]

    _org_client(stack.org, redirectUris=[f"{stack.redirect}/"])
    try:
        refused = sign_in(stack)
        assert refused.tokens is None
        assert refused.stopped_at is not None and refused.stopped_at.status_code == 400
        assert "redirect_uri" in refused.stopped_at.text.lower() or (
            "invalid parameter" in refused.stopped_at.text.lower()
        ), refused.stopped_at.text[:1500]
    finally:
        _org_client(stack.org, redirectUris=[stack.redirect])


def test_a_person_from_the_organisation_has_no_role_until_an_administrator_grants_one(
    stack: Stack,
) -> None:
    """The owner's answer 6 (rule 4): a person arriving through the organisation is signed in — the
    Conduit's own resolver accepts the token — with no role, no handling code and a clearance and
    unit that see nothing. An administrator then grants a role and access through the Admin area's
    own code (`services.api.identity_admin`), and the next sign-in, through the organisation again,
    carries them: the arrival mappers ran once, and did not take the grant back."""
    from services.api.identity_admin import IdentityAdmin

    from schemas.admin import AccessInput

    _register(stack)
    _forget(stack, PERSON["username"])
    first = sign_in(stack)
    assert first.tokens is not None, first.visited
    principal = _principal(stack, first.tokens["access_token"])
    assert principal.roles == []
    assert principal.receivable_handling_codes == []
    assert (principal.clearance, principal.org_unit) == (
        ORGANISATION_ARRIVAL_ATTRIBUTES["clearance"], ORGANISATION_ARRIVAL_ATTRIBUTES["org_unit"])  # fmt: skip
    claims = _claims(first.tokens["id_token"])
    assert claims.get("email") == PERSON["email"]

    issuer = f"{stack.deployment.origin}/realms/osprey"
    admin = IdentityAdmin(OidcResolverSettings(
        oidc_jwks_url=f"{issuer}/protocol/openid-connect/certs",
        oidc_token_exchange_url=f"{issuer}/protocol/openid-connect/token",
        oidc_token_exchange_client_id=CONDUIT_CLIENT_ID,
        oidc_token_exchange_client_secret=stack.values["OSPREY_OIDC_CLIENT_SECRET"],
        oidc_admin_users_url=f"{stack.deployment.origin}/admin/realms/osprey/users",
    ))  # fmt: skip

    async def grant() -> None:
        try:
            people = {p.username: p for p in await admin.list_people()}
            person = people[PERSON["username"]]
            assert person.roles == [] and person.clearance == "unassigned"
            await admin.set_roles(person.id, ["analyst"])
            await admin.set_access(
                person.id,
                AccessInput(clearance="OFFICIAL", org_unit="unit-1", receivable_handling_codes=["P"]),
            )
        finally:
            await admin.aclose()

    asyncio.run(grant())
    # A new browser: the organisation's own sign-in again, and an account that already exists.
    second = sign_in(stack)
    assert second.tokens is not None, second.visited
    assert any(u.startswith(f"https://{ORG_HOST}:") for u in second.visited)
    granted = _principal(stack, second.tokens["access_token"])
    assert granted.roles == ["analyst"]
    assert (granted.clearance, granted.org_unit, granted.receivable_handling_codes) == (
        "OFFICIAL", "unit-1", ["P"])  # fmt: skip


def test_a_wrong_client_secret_is_refused_by_the_organisation_and_repair_puts_it_back(
    stack: Stack,
) -> None:
    """The organisation's provider refuses the code exchange made with any other secret, so no
    person is signed in; `ospreyflow repair-sign-in`'s registration sets the deployment's own
    again — safe to repeat, and never naming it."""
    _register(stack, {**stack.values, "OSPREY_ORG_SIGN_IN_SECRET": "not-the-organisations"})
    refused = sign_in(stack)
    assert refused.tokens is None, refused.visited
    assert refused.stopped_at is not None
    assert not any(u.startswith(stack.config.network.public_origin + "/?") for u in refused.visited)

    first = _register(stack)
    second = _register(stack)
    for line in first + second:
        assert stack.org_secret not in line and "not-the-organisations" not in line
    assert sign_in(stack).tokens is not None


def test_repair_sign_in_sets_the_brokers_client_secret_again(stack: Stack) -> None:
    """A realm imported afresh (a wipe, a restart of an unpersisted Keycloak) has no organisation
    sign-in at all, nor anyone who arrived through it: the import carries neither. The registration
    puts the provider back, its secret and arrival mappers with it, and the person can sign in
    through the organisation again.

    The person is removed before the provider, as in a realm made afresh: measured on Keycloak
    26.0, removing a provider while an account is still linked to it leaves Keycloak's own cache
    answering a later sign-in with "an account with this email already exists"."""
    token = _admin(stack.deployment)
    base = f"{stack.deployment.origin}/admin/realms/osprey/identity-provider/instances/{ALIAS}"
    _register(stack)
    _forget(stack, PERSON["username"])
    status, _ = keycloak_admin._call(base, token=token, method="DELETE")
    assert status == 204
    lines = _register(stack)
    assert any("organisation sign-in org: registered" in line for line in lines), lines
    status, mappers = keycloak_admin._call(f"{base}/mappers", token=token)
    assert status == 200 and {m["config"]["attribute"] for m in mappers} == set(
        ORGANISATION_ARRIVAL_ATTRIBUTES
    )
    outcome = sign_in(stack)
    assert outcome.tokens is not None, (outcome.visited, _said(outcome))
    assert _principal(stack, outcome.tokens["access_token"]).roles == []


def test_keycloak_trusts_the_organisations_ca_for_its_back_channel(stack: Stack) -> None:
    """With the organisation's CA in its truststore (as rendered), Keycloak reads the provider's
    discovery document over HTTPS and signs people in (the cases above); with a truststore that
    holds another organisation's CA, the same registration is refused, in words naming
    `network.tls.ca`, because the provider's chain reaches no root Keycloak trusts."""
    environment, volumes = _truststore(stack.config)
    assert environment == {"KC_TRUSTSTORE_PATHS": KEYCLOAK_TRUSTSTORE_PATH}
    assert len(volumes) == 1
    elsewhere = stack.elsewhere
    token = _admin(elsewhere)
    with pytest.raises(RealmConfigurationFailed) as refused:
        ensure_identity(issuer=elsewhere.origin, realm="osprey", token=token,
                        config=stack.elsewhere_config, values=stack.values)  # fmt: skip
    words = str(refused.value)
    assert "network.tls.ca" in words and "could not read" in words
    assert stack.org_secret not in words


def _sign_out(stack: Stack, browser: httpx.Client, id_token: str) -> list[str]:
    """The Glass's sign-out (RP-initiated logout at the deployment's identity provider), each
    redirect followed; the addresses visited."""
    origin = stack.config.network.public_origin
    url = (
        f"{stack.deployment.origin}/realms/osprey/protocol/openid-connect/logout?"
        + urllib.parse.urlencode({"id_token_hint": id_token, "post_logout_redirect_uri": origin,
                                  "client_id": GLASS_CLIENT_ID})  # fmt: skip
    )
    visited: list[str] = []
    for _ in range(15):
        visited.append(url)
        if url.rstrip("/") == origin or url.startswith(f"{origin}/"):
            return visited
        response = browser.get(url)
        if not response.is_redirect:
            visited.append(f"stopped: {response.status_code}")
            return visited
        url = urllib.parse.urljoin(url, response.headers["location"])
    return visited


def test_signing_out_returns_through_the_printed_post_logout_address(stack: Stack) -> None:
    """Amendment 33 decision 4's second address, "to be confirmed against the pinned Keycloak
    26.0": signing out of OspreyFlow sends the browser to the organisation's own sign-out with
    exactly the printed post-logout redirect URI, and back to the Glass — and the organisation's
    provider refuses it when the application registered another."""
    _register(stack)
    browser = httpx.Client(verify=ssl.create_default_context(), timeout=30)
    outcome = sign_in(stack, browser)
    assert outcome.tokens is not None, (outcome.visited, _said(outcome))
    visited = _sign_out(stack, browser, outcome.tokens["id_token"])
    at_org = [u for u in visited if u.startswith(f"https://{ORG_HOST}:") and "logout" in u]
    assert at_org, visited
    asked = urllib.parse.parse_qs(urllib.parse.urlsplit(at_org[0]).query)
    assert asked["post_logout_redirect_uri"] == [stack.logout]
    assert visited[-1].startswith(stack.config.network.public_origin), visited

    _org_client(stack.org, attributes={"post.logout.redirect.uris": f"{stack.logout}/elsewhere",
                                       "pkce.code.challenge.method": "S256"})  # fmt: skip
    try:
        browser = httpx.Client(verify=ssl.create_default_context(), timeout=30)
        again = sign_in(stack, browser)
        assert again.tokens is not None
        refused = _sign_out(stack, browser, again.tokens["id_token"])
        assert refused[-1].startswith("stopped: 400"), refused
    finally:
        _org_client(stack.org, attributes={"post.logout.redirect.uris": stack.logout,
                                           "pkce.code.challenge.method": "S256"})  # fmt: skip


def test_a_restored_person_still_signs_in_through_the_organisation(stack: Stack) -> None:
    """ADR-114 Amendment 33 decision 5 (drop 2, unit 6): a backup carries the realm's people by
    their ids (`harness/identity.py`), not Keycloak's database. A person who arrived through the
    organisation must come back still linked to it — measured on Keycloak 26.0, an account with
    their email but no link stops their next sign-in at "an account with this email already
    exists" — and with the roles an administrator gave them."""
    from harness import identity

    _register(stack)
    first = sign_in(stack)
    assert first.tokens is not None, (first.visited, _said(first))
    subject = _claims(first.tokens["access_token"])["sub"]
    token = _admin(stack.deployment)
    exported = identity.export_identity(issuer=stack.deployment.origin, realm="osprey", token=token)
    (person,) = [p for p in exported["people"] if p["username"] == PERSON["username"]]
    assert person["federatedIdentities"][0]["identityProvider"] == ALIAS
    # A restore: the realm made afresh (here, the person removed), then their identity imported.
    _forget(stack, PERSON["username"])
    identity.import_identity(issuer=stack.deployment.origin, realm="osprey", token=token,
                             identity={**exported, "people": [person], "dashboards": []})  # fmt: skip
    again = sign_in(stack)
    assert again.tokens is not None, (again.visited, _said(again))
    assert _claims(again.tokens["access_token"])["sub"] == subject
