"""Someone arriving through the organisation's identity provider whose email an OspreyFlow account
already holds (ADR-114 Amendment 33, "Step 28 (e)"; build order step 28 (e)).

Keycloak's own *first broker login* flow stops such a person at its raw "Account already exists"
page, which offers to join the two accounts (by an email to the account's address, or the account's
password). The deployment registers a flow of its own instead: a new account when the email is not
held, and otherwise **access refused with OspreyFlow's words** — never a join by email
(`trustEmail` stays false and no step links automatically).

**The stand-in.** `test_register_sign_in.FakeKeycloak` (the admin API with its refusals), extended
with Keycloak 26's authentication-flow and identity-provider admin routes, and with the refusals
those make: a flow or sub-flow alias already held anywhere in the realm is 409; an execution of a
provider Keycloak does not have is 400; an unknown flow, execution or configuration is 404; a
configuration without an alias is 400; and an identity provider naming a first-sign-in flow that
does not exist is refused (400, "No available authentication flow with alias"). It also **runs** a
first-broker-login flow as Keycloak's `DefaultAuthenticationFlow` does: a level holding a REQUIRED
step ignores its ALTERNATIVE ones; alternatives are tried in order until one succeeds; *Create User
If Unique* as an alternative steps aside when the email is held (and shows Keycloak's own "already
exists" error when REQUIRED); *Confirm Link Existing Account* is the raw page; *Deny Access* refuses
with its configured message. So the tests below fail on what a person would see, not on how the
flow was written. A real Keycloak 26.0 is in `test_organisation_sign_in.py`.
"""

from __future__ import annotations

import itertools
import urllib.parse
from dataclasses import dataclass
from typing import Any

import pytest
from harness import keycloak_admin, register_sign_in
from harness.keycloak_admin import RealmConfigurationFailed
from harness.keycloak_theme import THEME_MESSAGES, render_login_theme

from schemas.deployment import AppearanceConfig, OspreyConfig

from .test_register_sign_in import ADMIN_PASSWORD, ISSUER, FakeKeycloak

ALIAS = "org"
ORG_SECRET = "the-organisations-client-secret"
EMAIL = "pat.example@example.org"

#: The authenticators Keycloak 26.0 has, of those a first-broker-login flow uses, by provider id.
KNOWN_AUTHENTICATORS = {
    "idp-review-profile",
    "idp-create-user-if-unique",
    "idp-confirm-link",
    "idp-email-verification",
    "idp-username-password-form",
    "idp-auto-link",
    "deny-access-authenticator",
    "auth-otp-form",
}


def _organisation_config() -> OspreyConfig:
    return OspreyConfig.model_validate({
        "profile": "small",
        "network": {"public_origin": "https://osprey.example.org"},
        "governance": {"organisation_sign_in": ALIAS,
                       "organisation_provider": {"label": "Example Department account",
                                                 "issuer": "https://login.example.org/realms/org",
                                                 "client_id": "osprey"}},
    })  # fmt: skip


@dataclass
class Arrival:
    """Where a person's first sign-in through the organisation ended."""

    #: "signed-in", "page" (a page that asks something), or "refused" (an error page).
    outcome: str
    #: The page's template, or the message key an error page shows.
    said: str


class FlowKeycloak(FakeKeycloak):
    def __init__(self) -> None:
        super().__init__()
        self._ids = itertools.count(1)
        #: alias -> {"id", "alias", "topLevel", "builtIn", "providerId", "description"}
        self.flows: dict[str, dict[str, Any]] = {}
        #: id -> {"id", "parent", "provider" | "flow", "requirement", "config"}
        self.executions: dict[str, dict[str, Any]] = {}
        self.configs: dict[str, dict[str, Any]] = {}
        self.providers: dict[str, dict[str, Any]] = {}
        self.provider_mappers: dict[str, list[dict[str, Any]]] = {}
        #: username -> the identity providers the account is joined to.
        self.links: dict[str, set[str]] = {}
        self._builtin_first_broker_login()

    # --- the realm's own flows, as Keycloak 26.0 makes them -------------------------------------

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids)}"

    def _add_flow(self, alias: str, *, top: bool, builtin: bool = False) -> None:
        self.flows[alias] = {"id": self._new_id("flow"), "alias": alias, "topLevel": top,
                             "builtIn": builtin, "providerId": "basic-flow",
                             "description": ""}  # fmt: skip

    def _add_step(self, parent: str, requirement: str, *, provider: str | None = None,
                  flow: str | None = None,
                  config: dict[str, str] | None = None) -> None:  # fmt: skip
        identifier = self._new_id("exec")
        config_id = None
        if config is not None:
            config_id = self._new_id("config")
            self.configs[config_id] = {
                "id": config_id,
                "alias": f"{identifier} config",
                "config": config,
            }
        self.executions[identifier] = {"id": identifier, "parent": parent, "provider": provider,
                                       "flow": flow, "requirement": requirement,
                                       "config": config_id}  # fmt: skip

    def _builtin_first_broker_login(self) -> None:
        self._add_flow("first broker login", top=True, builtin=True)
        self._add_step("first broker login", "REQUIRED", provider="idp-review-profile",
                       config={"update.profile.on.first.login": "missing"})  # fmt: skip
        self._add_flow("User creation or linking", top=False, builtin=True)
        self._add_step("first broker login", "REQUIRED", flow="User creation or linking")
        self._add_step(
            "User creation or linking", "ALTERNATIVE", provider="idp-create-user-if-unique"
        )
        self._add_flow("Handle Existing Account", top=False, builtin=True)
        self._add_step("User creation or linking", "ALTERNATIVE", flow="Handle Existing Account")
        self._add_step("Handle Existing Account", "REQUIRED", provider="idp-confirm-link")
        self._add_flow("Account verification options", top=False, builtin=True)
        self._add_step("Handle Existing Account", "REQUIRED", flow="Account verification options")
        self._add_step(
            "Account verification options", "ALTERNATIVE", provider="idp-email-verification"
        )

    def _children(self, alias: str) -> list[dict[str, Any]]:
        return [e for e in self.executions.values() if e["parent"] == alias]

    def _listing(self, alias: str, level: int = 0) -> list[dict[str, Any]]:
        """`GET …/flows/{alias}/executions`: every execution under the flow, depth first, each with
        its level relative to the flow named."""
        out: list[dict[str, Any]] = []
        for index, execution in enumerate(self._children(alias)):
            rep: dict[str, Any] = {"id": execution["id"], "requirement": execution["requirement"],
                                   "level": level, "index": index}  # fmt: skip
            if execution["flow"]:
                rep.update(displayName=execution["flow"], authenticationFlow=True,
                           flowId=self.flows[execution["flow"]]["id"])  # fmt: skip
            else:
                rep.update(displayName=execution["provider"], providerId=execution["provider"],
                           authenticationFlow=False)  # fmt: skip
                if execution["config"]:
                    rep["authenticationConfig"] = execution["config"]
            out.append(rep)
            if execution["flow"]:
                out.extend(self._listing(execution["flow"], level + 1))
        return out

    # --- the admin API ------------------------------------------------------------------------

    def call(self, url: str, *, token: str | None = None, data: Any = None, form: bool = False,
             method: str | None = None) -> tuple[int, Any]:  # fmt: skip
        path = url.removeprefix(ISSUER)
        route = urllib.parse.unquote(path.removeprefix("/admin/realms/osprey"))
        if not (route.startswith("/authentication/") or route.startswith("/identity-provider/")):
            return super().call(url, token=token, data=data, form=form, method=method)
        if self.unreachable:
            raise RealmConfigurationFailed(f"{url} unreachable: connection refused")
        verb = method or ("POST" if data is not None else "GET")
        self.calls.append((verb, path))
        if token != "admin-token":
            return 401, {"error": "HTTP 401 Unauthorized"}
        if route.startswith("/authentication/"):
            return self._authentication(verb, route.removeprefix("/authentication"), data)
        return self._identity_provider(verb, route.removeprefix("/identity-provider"), data)

    def _authentication(self, verb: str, route: str, data: Any) -> tuple[int, Any]:
        if route == "/flows" and verb == "GET":
            return 200, [dict(f) for f in self.flows.values() if f["topLevel"]]
        if route == "/flows" and verb == "POST":
            if data["alias"] in self.flows:
                return 409, {"errorMessage": f"Flow {data['alias']} already exists"}
            self._add_flow(data["alias"], top=bool(data.get("topLevel", True)))
            return 201, ""
        parts = route.split("/")
        if route.startswith("/flows/") and len(parts) >= 4 and parts[3] == "executions":
            alias = parts[2]
            if alias not in self.flows:
                return 404, {"error": "Flow not found"}
            tail = parts[4:]
            if verb == "GET" and not tail:
                return 200, self._listing(alias)
            if verb == "PUT" and not tail:
                execution = self.executions.get(data.get("id", ""))
                if execution is None:
                    return 404, {"error": "Illegal execution"}
                execution["requirement"] = data["requirement"]
                return 204, ""
            if verb == "POST" and tail == ["execution"]:
                if data.get("provider") not in KNOWN_AUTHENTICATORS:
                    return 400, {
                        "error": f"No authentication provider found for id: {data.get('provider')}"
                    }
                self._add_step(alias, "DISABLED", provider=data["provider"])
                return 201, ""
            if verb == "POST" and tail == ["flow"]:
                if data.get("alias") in self.flows:
                    return 409, {"errorMessage": "New flow alias name already exists"}
                if data.get("type") not in ("basic-flow", "form-flow"):
                    return 400, {"error": "unknown flow type"}
                self._add_flow(data["alias"], top=False)
                self._add_step(alias, "DISABLED", flow=data["alias"])
                return 201, ""
        if route.startswith("/executions/") and route.endswith("/config") and verb == "POST":
            execution = self.executions.get(parts[2])
            if execution is None:
                return 404, {"error": "Illegal execution"}
            if not data.get("alias"):
                return 400, {"error": "Failed to create authenticator config: alias is required"}
            config_id = self._new_id("config")
            self.configs[config_id] = {"id": config_id, "alias": data["alias"],
                                       "config": dict(data.get("config") or {})}  # fmt: skip
            execution["config"] = config_id
            return 201, ""
        if route.startswith("/config/"):
            config = self.configs.get(parts[2])
            if config is None:
                return 404, {"error": "Could not find authenticator config"}
            if verb == "GET":
                return 200, dict(config)
            if verb == "PUT":
                config["config"] = dict(data.get("config") or {})
                return 204, ""
        raise AssertionError(f"the stand-in has no authentication route for {verb} {route}")

    def _identity_provider(self, verb: str, route: str, data: Any) -> tuple[int, Any]:
        if route == "/import-config":
            issuer = data["fromUrl"].removesuffix("/.well-known/openid-configuration")
            return 200, {"authorizationUrl": f"{issuer}/auth", "tokenUrl": f"{issuer}/token",
                         "issuer": issuer, "jwksUrl": f"{issuer}/certs"}  # fmt: skip
        if route in ("/instances",) or route.startswith("/instances/") and route.count("/") == 2:
            if verb in ("POST", "PUT"):
                flow = data.get("firstBrokerLoginFlowAlias") or "first broker login"
                if flow not in self.flows:
                    return 400, {
                        "errorMessage": f"No available authentication flow with alias: {flow}"
                    }
            if verb == "POST":
                if data["alias"] in self.providers:
                    return 409, {"errorMessage": "Identity Provider already exists"}
                self.providers[data["alias"]] = dict(data)
                return 201, ""
            alias = route.split("/")[2]
            if alias not in self.providers:
                return 404, {"error": "Could not find identity provider"}
            if verb == "GET":
                return 200, dict(self.providers[alias])
            self.providers[alias] = dict(data)
            return 204, ""
        if route.endswith("/mappers"):
            alias = route.split("/")[2]
            held = self.provider_mappers.setdefault(alias, [])
            if verb == "GET":
                return 200, [dict(m) for m in held]
            held.append({**data, "id": self._new_id("mapper")})
            return 201, ""
        raise AssertionError(f"the stand-in has no identity-provider route for {verb} {route}")

    # --- a person arriving -------------------------------------------------------------------

    def invite(self, username: str, email: str) -> None:
        """An account as Admin -> People's invitation makes it (`identity_admin.invite`)."""
        identifier = f"uid-{len(self.users) + 1}"
        self.users[identifier] = {"id": identifier, "username": username, "email": email,
                                  "emailVerified": False,
                                  "requiredActions": ["UPDATE_PASSWORD"]}  # fmt: skip

    def arrive(self, username: str, email: str) -> Arrival:
        """The person's sign-in through the organisation's provider, as Keycloak carries it out."""
        if ALIAS in self.links.get(username, set()):
            return Arrival("signed-in", "")
        provider = self.providers[ALIAS]
        flow = provider.get("firstBrokerLoginFlowAlias") or "first broker login"
        person = {"username": username, "email": email}
        result, said = self._run(flow, person)
        if result == "success":
            return Arrival("signed-in", "")
        return Arrival(result, said)

    def _run(self, alias: str, person: dict[str, str]) -> tuple[str, str]:
        steps = [e for e in self._children(alias) if e["requirement"] != "DISABLED"]
        required = [e for e in steps if e["requirement"] in ("REQUIRED", "CONDITIONAL")]
        if required:
            for step in required:  # alternatives beside a required step are ignored
                result = self._step(step, person)
                if result[0] != "success":
                    return result
            return "success", ""
        for step in steps:
            result = self._step(step, person)
            if result[0] == "attempted":
                continue
            return result
        return "attempted", ""

    def _step(self, step: dict[str, Any], person: dict[str, str]) -> tuple[str, str]:
        if step["flow"]:
            return self._run(step["flow"], person)
        config = self.configs[step["config"]]["config"] if step["config"] else {}
        provider = step["provider"]
        if provider == "idp-review-profile":
            return "success", ""
        if provider == "idp-create-user-if-unique":
            held = any(u.get("email") == person["email"] or u["username"] == person["username"]
                       for u in self.users.values())  # fmt: skip
            if not held:
                identifier = f"uid-{len(self.users) + 1}"
                self.users[identifier] = {"id": identifier, **person}
                self.links.setdefault(person["username"], set()).add(ALIAS)
                return "success", ""
            if step["requirement"] == "REQUIRED":
                return "refused", "federatedIdentityExistsMessage"
            return "attempted", ""
        if provider == "idp-confirm-link":
            return "page", "login-idp-link-confirm.ftl"
        if provider == "idp-auto-link":
            (held,) = [u for u in self.users.values() if u.get("email") == person["email"]]
            self.links.setdefault(held["username"], set()).add(ALIAS)
            return "success", ""
        if provider == "deny-access-authenticator":
            return "refused", config.get("denyErrorMessage") or "accessDeniedMessage"
        return "page", provider


@pytest.fixture
def keycloak(monkeypatch: pytest.MonkeyPatch) -> FlowKeycloak:
    fake = FlowKeycloak()
    monkeypatch.setattr(keycloak_admin, "_call", fake.call)
    return fake


def _identity(keycloak: FlowKeycloak) -> list[str]:
    """What `ospreyflow install` and `ospreyflow repair-sign-in --no-demo-accounts` run."""
    token = keycloak_admin.admin_token(
        issuer=ISSUER, admin_user="admin", admin_password=ADMIN_PASSWORD
    )
    return register_sign_in.ensure_identity(
        issuer=ISSUER, realm="osprey", token=token, config=_organisation_config(),
        values={"OSPREY_ORG_SIGN_IN_SECRET": ORG_SECRET},
    )  # fmt: skip


def _flow_writes(keycloak: FlowKeycloak) -> int:
    return sum(1 for verb, path in keycloak.calls
               if verb in ("POST", "PUT") and "/authentication/" in path)  # fmt: skip


def test_the_stand_in_shows_keycloaks_raw_page_under_its_own_first_broker_login() -> None:
    """What step 20's drop 2 left in place, and what the person met: the realm's own flow stops an
    arrival whose email an invited account holds at "Account already exists"."""
    keycloak = FlowKeycloak()
    keycloak.providers[ALIAS] = {"alias": ALIAS, "firstBrokerLoginFlowAlias": "first broker login"}
    keycloak.invite("pat.local", EMAIL)
    assert keycloak.arrive("pat.example", EMAIL) == Arrival("page", "login-idp-link-confirm.ftl")


def test_an_arrival_whose_email_an_invited_account_holds_is_told_in_words_and_not_joined(
    keycloak: FlowKeycloak,
) -> None:
    keycloak.invite("pat.local", EMAIL)
    _identity(keycloak)
    arrival = keycloak.arrive("pat.example", EMAIL)
    assert arrival == Arrival("refused", "ospreyAccountExistsMessage")
    # Nothing made, nothing joined: the invited account is as it was, and no second account.
    assert [u["username"] for u in keycloak.users.values() if u.get("email") == EMAIL] == [
        "pat.local"
    ]
    assert keycloak.links == {}


def test_an_arrival_whose_email_nobody_holds_gets_a_new_account_as_before(
    keycloak: FlowKeycloak,
) -> None:
    keycloak.invite("someone.else", "someone.else@example.org")
    _identity(keycloak)
    assert keycloak.arrive("pat.example", EMAIL) == Arrival("signed-in", "")
    assert keycloak.links == {"pat.example": {ALIAS}}
    assert keycloak.arrive("pat.example", EMAIL) == Arrival("signed-in", ""), "and again, joined"


def test_the_provider_trusts_no_email_and_no_step_joins_accounts(keycloak: FlowKeycloak) -> None:
    """The safe default (ADR-114 Amendment 33, step 28 (e)): joining by email is an account
    takeover wherever the organisation's email claim is not verified — Entra ID's `email` is not."""
    _identity(keycloak)
    provider = keycloak.providers[ALIAS]
    assert provider["trustEmail"] is False
    flow = provider["firstBrokerLoginFlowAlias"]
    assert flow != "first broker login"
    used = {s.get("providerId") for s in keycloak._listing(flow)}
    assert used.isdisjoint({"idp-auto-link", "idp-confirm-link", "idp-email-verification",
                            "idp-username-password-form"}), used  # fmt: skip


def test_the_flow_is_made_once_and_a_second_run_writes_nothing(keycloak: FlowKeycloak) -> None:
    first = _identity(keycloak)
    writes = _flow_writes(keycloak)
    second = _identity(keycloak)
    assert _flow_writes(keycloak) == writes
    assert any("first sign-in" in line and "made" in line for line in first), first
    assert any("first sign-in" in line and "already in place" in line for line in second), second


def test_a_flow_changed_by_hand_is_put_back(keycloak: FlowKeycloak) -> None:
    """Someone turns the refusal off in Keycloak's console, or changes its message: a repair puts it
    back, and the arrival is refused in words again."""
    _identity(keycloak)
    flow = keycloak.providers[ALIAS]["firstBrokerLoginFlowAlias"]
    (deny,) = [
        e for e in keycloak.executions.values() if e["provider"] == "deny-access-authenticator"
    ]
    deny["requirement"] = "DISABLED"
    keycloak.configs[deny["config"]]["config"] = {"denyErrorMessage": "something else"}
    keycloak.invite("pat.local", EMAIL)
    assert keycloak.arrive("pat.example", EMAIL).said != "ospreyAccountExistsMessage"
    lines = _identity(keycloak)
    assert keycloak.arrive("pat.example", EMAIL) == Arrival("refused", "ospreyAccountExistsMessage")
    assert any("first sign-in" in line and "brought up to date" in line for line in lines), lines
    assert flow == keycloak.providers[ALIAS]["firstBrokerLoginFlowAlias"]


def test_a_refused_flow_is_named_and_the_provider_is_not_left_pointing_at_nothing(
    keycloak: FlowKeycloak, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = keycloak.call

    def refusing(url: str, **kwargs: Any) -> tuple[int, Any]:
        if "/authentication/flows" in url and kwargs.get("data") is not None:
            return 403, {"error": "HTTP 403 Forbidden"}
        return real(url, **kwargs)

    monkeypatch.setattr(keycloak_admin, "_call", refusing)
    with pytest.raises(RealmConfigurationFailed, match="first sign-in"):
        _identity(keycloak)
    assert ALIAS not in keycloak.providers


def test_a_deployment_without_the_organisations_provider_gets_no_flow(
    keycloak: FlowKeycloak,
) -> None:
    token = keycloak_admin.admin_token(
        issuer=ISSUER, admin_user="admin", admin_password=ADMIN_PASSWORD
    )
    register_sign_in.ensure_identity(
        issuer=ISSUER, realm="osprey", token=token,
        config=OspreyConfig.model_validate({"network": {"public_origin": "http://localhost:9999"}}),
        values={},
    )  # fmt: skip
    assert _flow_writes(keycloak) == 0


# --- ADR-112 Amendment 3 (b), build order step 33: the realm keeps its record of a refusal --------


def test_a_realm_whose_events_were_off_records_refused_arrivals_and_nothing_else(
    keycloak: FlowKeycloak,
) -> None:
    """Admin -> People reads Keycloak's record of each refused first sign-in to offer the join; the
    realm keeps that one kind for seven days, and does not start recording everyone's sign-ins."""
    from harness.realm import ARRIVAL_EVENT, ARRIVAL_EVENTS_SECONDS

    lines = _identity(keycloak)
    assert keycloak.events_config["eventsEnabled"] is True
    assert keycloak.events_config["enabledEventTypes"] == [ARRIVAL_EVENT]
    assert keycloak.events_config["eventsExpiration"] == ARRIVAL_EVENTS_SECONDS == 604800
    assert keycloak.events_config["eventsListeners"] == ["jboss-logging"], "kept as it was"
    assert any("recorded for seven days" in line for line in lines), lines
    def writes() -> int:
        return sum(1 for verb, path in keycloak.calls
                   if verb == "PUT" and path.endswith("/events/config"))  # fmt: skip

    before = writes()
    assert any("already recorded" in line for line in _identity(keycloak))
    assert writes() == before, "a second run writes nothing"


def test_events_an_administrator_turned_on_are_kept_with_the_refusal_added(
    keycloak: FlowKeycloak,
) -> None:
    from harness.realm import ARRIVAL_EVENT

    keycloak.events_config.update(eventsEnabled=True, enabledEventTypes=["LOGIN_ERROR"],
                                  eventsExpiration=3600)  # fmt: skip
    _identity(keycloak)
    assert keycloak.events_config["enabledEventTypes"] == ["LOGIN_ERROR", ARRIVAL_EVENT]
    assert keycloak.events_config["eventsExpiration"] == 3600


def test_a_deployment_without_the_organisations_provider_keeps_its_events_as_they_were(
    keycloak: FlowKeycloak,
) -> None:
    before = dict(keycloak.events_config)
    token = keycloak_admin.admin_token(
        issuer=ISSUER, admin_user="admin", admin_password=ADMIN_PASSWORD
    )
    register_sign_in.ensure_identity(
        issuer=ISSUER, realm="osprey", token=token,
        config=OspreyConfig.model_validate({"network": {"public_origin": "http://localhost:9999"}}),
        values={},
    )  # fmt: skip
    assert keycloak.events_config == before


def test_the_conduit_is_told_the_organisations_sign_in_only_when_there_is_one() -> None:
    from harness.render import render

    def env(config: OspreyConfig) -> str:
        return render(config, resolver=lambda _image: "sha256:" + "0" * 64).artefacts[
            "deployment.env"
        ]

    assert f"OSPREY_ORGANISATION_SIGN_IN={ALIAS}" in env(_organisation_config())
    assert "OSPREY_ORGANISATION_SIGN_IN" not in env(OspreyConfig.model_validate({}))


@pytest.mark.parametrize("brand", ["ospreyflow", "govuk"])
def test_the_sign_in_page_says_what_happened_and_what_to_do(brand: str) -> None:
    appearance = AppearanceConfig.model_validate(
        {"brand": "govuk", "service_name": "Prison Intelligence"} if brand == "govuk" else {}
    )
    messages = render_login_theme("", appearance=appearance)[THEME_MESSAGES]
    (line,) = [m for m in messages.splitlines() if m.startswith("ospreyAccountExistsMessage=")]
    said = line.split("=", 1)[1]
    assert "already belongs to" in said and "administrator" in said
    assert "username and password" in said
    if brand == "govuk":
        assert "OspreyFlow" not in said
    else:
        assert "OspreyFlow account" in said
