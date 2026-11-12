"""Entra ID sign-in on the cloud-platform profile (`spec/06_DECISIONS.md` ADR-148 decision 9;
Amendment 8, P10 part 2).

What a mistake would do, and the case that catches it (rule 12):
- the render's claim settings not reaching the Conduit, or reaching it without the Glass's
  client: `test_the_rendered_settings_sign_in_a_glass_token_through_the_one_construction_path`
  (from the rendered environment, through `ClaimMapping.from_env`, to the resolver; red with
  `client_id` left out of the rendered mapping, `process/lanes/admin/p10p2/plants`);
- the realm's settings left in the Conduit's environment, pointing at a Keycloak that is not there:
  `test_the_realms_settings_are_gone_and_entras_are_rendered`;
- an Entra deployment rendered with nobody to administer it, or "nobody" read as everyone:
  `test_no_first_administrator_is_refused_never_everyone`;
- Keycloak's `deployment.json` changed by Entra's fields:
  `test_keycloaks_deployment_file_is_as_it_was`.

Synthetic ids (rule 9).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest
import yaml
from harness.cloud_platform import REALM_SETTINGS, CloudPlatformNotRenderable
from harness.site import render_glass_settings
from pydantic import ValidationError
from services.api.auth import PrincipalResolutionError, PrincipalResolver
from services.api.config import ApiConfig

from principal_auth import ClaimMapping
from schemas.deployment import OspreyConfig
from tests.conftest import sign_token
from tests.harness.test_cloud_platform_render import (
    FIXTURES,
    _artefacts,
    _config,
    _containers,
    _values,
)
from tests.services.api.test_auth import _config as _api_config
from tests.services.api.test_auth_entra_claims import FakePeople

TENANT = "00000000-1111-4222-8333-444444444444"
GLASS = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
API = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
ADMIN = "50000000-0000-4000-8000-000000000001"
EXT = "extension_0123456789abcdef0123456789abcdef"


def _raw(name: str = "development") -> dict[str, Any]:
    return yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))


def _with_claims(**changes: Any) -> OspreyConfig:
    raw = _raw()
    raw["cloud_platform"]["claims"] |= changes
    return OspreyConfig.model_validate(raw)


#: The realm's settings, named here and not read from the code under test (the lane-reviewer's
#: finding 4): dropping one from `REALM_SETTINGS` must turn this red.
REALM_NAMES = {"OIDC_TOKEN_EXCHANGE_URL", "OIDC_TOKEN_EXCHANGE_CLIENT_ID", "OIDC_ADMIN_USERS_URL",
               "OSPREY_IDENTITY_ORIGIN"}  # fmt: skip


def test_the_realms_settings_are_gone_and_entras_are_rendered() -> None:
    environment = _values(_config())["environment"]
    assert REALM_SETTINGS == REALM_NAMES
    assert not REALM_NAMES & set(environment)
    assert environment["OSPREY_IDENTITY_PROVIDER"] == "entra"
    assert environment["OIDC_ISSUER"] == f"https://login.microsoftonline.com/{TENANT}/v2.0"
    assert environment["OIDC_AUDIENCE"] == API
    assert environment["OIDC_JWKS_URL"] == (
        f"https://login.microsoftonline.com/{TENANT}/discovery/v2.0/keys"
    )
    assert environment["OSPREY_FIRST_ADMINISTRATORS"] == ADMIN
    assert environment["SUPERSET_SIGN_IN"] == "entra"
    mapping = json.loads(environment["OSPREY_CLAIM_MAPPING"])
    assert (mapping["client_id"], mapping["api_client_id"]) == (GLASS, API)


def test_v1_tokens_and_a_claims_mapping_policy_change_the_issuer_audience_and_keys() -> None:
    environment = _values(_with_claims(token_version="1.0", claims_mapping_policy=True))[
        "environment"
    ]
    assert environment["OIDC_ISSUER"] == f"https://sts.windows.net/{TENANT}/"
    assert environment["OIDC_AUDIENCE"] == f"api://{API}"
    assert environment["OIDC_JWKS_URL"] == (
        f"https://login.microsoftonline.com/{TENANT}/discovery/keys?appid={API}"
    )


def test_the_rendered_settings_sign_in_a_glass_token_through_the_one_construction_path(
    keypair, jwks_url, monkeypatch
) -> None:
    """The render's own environment, read as the Conduit reads it (`ClaimMapping.from_env`), signs
    in a Glass token and refuses another application's, with the roles from the people store. Only
    the keys' address is the test's (a loopback JWKS standing in for Entra's)."""
    environment = _values(_config())["environment"]
    monkeypatch.setenv("OSPREY_CLAIM_MAPPING", environment["OSPREY_CLAIM_MAPPING"])
    config: ApiConfig = _api_config(
        jwks_url,
        oidc_issuer=environment["OIDC_ISSUER"],
        oidc_audience=environment["OIDC_AUDIENCE"],
    )
    resolver = PrincipalResolver(
        config, claim_mapping=ClaimMapping.from_env(), role_source=FakePeople()
    )
    now = int(time.time())
    claims = {
        "aud": API, "iss": environment["OIDC_ISSUER"], "iat": now, "exp": now + 3600,
        "tid": TENANT, "oid": ADMIN, "azp": GLASS, "sub": "pairwise", "scp": "access_as_user",
        f"{EXT}_clearance": "OFFICIAL", "groups": ["20000000-0000-4000-8000-000000000001"],
    }  # fmt: skip
    principal = asyncio.run(resolver.resolve_principal(sign_token(keypair[0], claims)))
    assert (principal.id, principal.org_unit) == (ADMIN, "unit-1")
    other = {**claims, "azp": "cccccccc-dddd-4eee-8fff-000000000000"}
    with pytest.raises(PrincipalResolutionError, match="Glass's client"):
        asyncio.run(resolver.resolve_principal(sign_token(keypair[0], other)))


def test_no_first_administrator_is_refused_never_everyone() -> None:
    with pytest.raises(ValidationError, match="first administrator"):
        _with_claims(first_administrators=[])
    with pytest.raises(ValidationError, match="object id"):
        _with_claims(first_administrators=["Ana"])


def test_a_render_without_entra_sign_in_is_refused_in_words() -> None:
    raw = _raw()
    del raw["cloud_platform"]["claims"]
    with pytest.raises(CloudPlatformNotRenderable, match="cloud_platform.claims"):
        _artefacts(OspreyConfig.model_validate(raw))


def test_a_claim_setting_principal_auth_cannot_read_is_refused_at_render() -> None:
    """Both sources for the clearance: `ClaimMapping` refuses it, so the render does, in words."""
    config = _with_claims(clearance={"claim": "c", "groups": {ADMIN: "OFFICIAL"}})
    with pytest.raises(CloudPlatformNotRenderable, match="claim mapping"):
        _artefacts(config)


def test_the_glass_is_told_entras_sign_in() -> None:
    settings = json.loads(_values(_config())["files"]["glass.json"])
    assert settings["sign_in"] == {
        "kind": "entra",
        "authority": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "client_id": GLASS,
        "scope": f"openid profile api://{API}/access_as_user",
    }
    assert "identity_provider" not in settings and "realm" not in settings


#: Every other profile's `deployment.json` for the development fixture as a Small, byte for byte as
#: main's `harness/site.py` rendered it before P10 part 2 (its version pinned): generated from
#: main's own module, not from the code under test (the lane-reviewer's finding 9).
KEYCLOAK_DEPLOYMENT_JSON = """{
  "identity_provider": "http://id.ospreyflow.localhost",
  "realm": "osprey",
  "marking": "PUBLIC",
  "organisation_sign_in": null,
  "organisation_label": null,
  "welcome": {
    "about": true,
    "links": {}
  },
  "appearance": {
    "brand": "ospreyflow",
    "service_name": null,
    "organisation": null,
    "phase": "none"
  },
  "version": "0000000"
}
"""


def test_keycloaks_deployment_file_is_as_it_was(monkeypatch) -> None:
    """Every other profile's `deployment.json`, byte for byte as before P10 part 2: never a
    `sign_in`, no field moved."""
    import harness.site as site

    monkeypatch.setattr(site, "deployment_version", lambda: "0000000")
    raw = _raw()
    raw.pop("cloud_platform")
    raw["profile"] = "local-lite"
    for key in ("map", "models", "network"):
        raw.pop(key, None)
    assert render_glass_settings(OspreyConfig.model_validate(raw)) == KEYCLOAK_DEPLOYMENT_JSON


def test_the_bare_profile_renders_with_reporting_at_its_defaults() -> None:
    """The orchestrator's ruling (a): report sync and Superset are off by default, so the profile's
    own defaults render; only an explicit `on` is refused."""
    raw = _raw()
    assert "reporting" not in raw
    values = _values(OspreyConfig.model_validate(raw))
    assert not {"report-sync", "superset"} & {w["name"] for w in values["workloads"]}


@pytest.mark.parametrize("switch", ["sync", "superset"])
def test_report_sync_or_superset_switched_on_is_refused_naming_its_step(switch: str) -> None:
    raw = _raw()
    raw["reporting"] = {switch: True}
    with pytest.raises(CloudPlatformNotRenderable, match="their own step after P10"):
        _artefacts(OspreyConfig.model_validate(raw))


def test_no_rendered_value_names_keycloak_or_the_identity_host() -> None:
    """Nothing the namespace is given points at the realm the profile no longer renders (the
    lane-reviewer's finding 4): not a setting, a secret's name, a file or a workload."""
    values = _values(_config("production"))
    # The deployment's own `osprey.yaml`, mounted as it was written, keeps its settings' defaults
    # (`governance.identity_provider`, read only at render); the Conduit is told `entra`.
    del values["files"]["osprey.yaml"]
    text = yaml.safe_dump(values).lower()
    assert "keycloak" not in text
    assert "id.ospreyflow.apps.example.org" not in text
    assert values["environment"]["OSPREY_IDENTITY_PROVIDER"] == "entra"


@pytest.mark.parametrize(
    "fixture", ["development", "development-sources", "poc", "production", "production-bedrock"]
)
def test_the_set_up_console_is_no_part_of_the_render(fixture: str) -> None:
    """The set-up console (`python -m harness.webapp`, its `/admin` behind `webapp_auth`'s Keycloak
    role check) is the local install's: no pod, image, command or door of the cloud-platform render
    is it, so its Keycloak-only role check is never what admits someone there (the orchestrator's
    review of P10 part 2; `test_realm_readers_refuse_entra.py`'s docstring rests on this)."""
    values = _values(_config(fixture))
    for container in _containers(values):
        image = container["image"].split("@", 1)[0].rsplit(":", 1)[0]
        command = " ".join(map(str, [*container.get("command", []), *container.get("args", [])]))
        assert not image.endswith("/harness"), container["name"]
        assert "harness" not in command, container["name"]
    served = {p["service"] for rule in values["ingress"]["rules"] for p in rule["paths"]}
    assert served <= {w["name"] for w in values["workloads"]}
