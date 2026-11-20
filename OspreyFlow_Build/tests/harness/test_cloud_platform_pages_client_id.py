"""The `pages` service's Entra client, through the deployment configuration (ADR-152 decision 11, X1).

`cloud_platform.claims.pages_client_id` is the `pages` service's own app registration. Set, it is
emitted into the rendered `OSPREY_CLAIM_MAPPING` that the Conduit reads; unset, nothing is emitted (no
key, so every existing deployment's mapping is byte for byte as it was); a malformed one is refused at
the configuration. The two ends meet: the JSON the render emits, planted in the environment as the
Conduit reads it (`ClaimMapping.from_env`), admits a token issued to the pages client and still refuses a
third (rule 15: the emitted JSON, not a hand-built mapping).

The render's refusal for a `pages` service on under Entra with no `pages_client_id` is not here: there is
no `pages` service yet (PL3). Synthetic ids (rule 9).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from services.api.auth import PrincipalResolutionError, PrincipalResolver

from principal_auth import ClaimMapping
from schemas.deployment import OspreyConfig
from tests.conftest import sign_token
from tests.harness.test_cloud_platform_entra import API, EXT, GLASS, SUPERSET_APP
from tests.harness.test_cloud_platform_render import FIXTURES, _values
from tests.services.api.test_auth import _config as _api_config
from tests.services.api.test_auth_entra_claims import FakePeople, entra_claims

PAGES_APP = "77777777-aaaa-4bbb-8ccc-dddddddddddd"
OTHER_APP = "cccccccc-dddd-4eee-8fff-000000000000"


def _with_claims(**changes: Any) -> OspreyConfig:
    raw = yaml.safe_load((FIXTURES / "development.yaml").read_text(encoding="utf-8"))
    raw["cloud_platform"]["claims"] |= changes
    return OspreyConfig.model_validate(raw)


def _emitted(config: OspreyConfig) -> dict[str, Any]:
    return json.loads(_values(config)["environment"]["OSPREY_CLAIM_MAPPING"])


def test_pages_client_id_set_is_emitted_into_the_rendered_claim_mapping() -> None:
    assert _emitted(_with_claims(pages_client_id=PAGES_APP))["pages_client_id"] == PAGES_APP


def test_pages_client_id_unset_emits_nothing() -> None:
    assert "pages_client_id" not in _emitted(_with_claims())
    # And an empty one is not "set to nothing": it is refused as malformed.
    assert _with_claims(pages_client_id=PAGES_APP)  # control: the field exists
    with pytest.raises(ValidationError, match="pages_client_id"):
        _with_claims(pages_client_id="")


@pytest.mark.parametrize("bad", ["not-a-guid", "7777", "api://" + PAGES_APP, PAGES_APP + "x"])
def test_a_malformed_pages_client_id_is_refused_at_the_configuration(bad: str) -> None:
    assert _with_claims(pages_client_id=PAGES_APP)  # control: a GUID is accepted
    with pytest.raises(ValidationError, match="pages_client_id"):
        _with_claims(pages_client_id=bad)


@pytest.mark.parametrize("same", [GLASS, API, SUPERSET_APP], ids=["the-glass", "the-api", "superset"])
def test_a_pages_client_id_that_is_another_registration_s_is_refused_before_it_is_rendered(same: str) -> None:
    """The configuration may accept it (the pattern is a GUID's); the claim mapping the render builds
    must not, and the render says so rather than emitting a mapping the Conduit would refuse at start."""
    from harness.cloud_platform import CloudPlatformNotRenderable

    from tests.harness.test_cloud_platform_render import _artefacts

    assert _artefacts(_with_claims(pages_client_id=PAGES_APP))  # control: a distinct GUID renders
    changes: dict[str, Any] = {"pages_client_id": same}
    if same == SUPERSET_APP:
        changes["superset_client_id"] = SUPERSET_APP
    with pytest.raises((ValidationError, CloudPlatformNotRenderable), match="pages_client_id|claim mapping"):
        _artefacts(_with_claims(**changes))


def test_the_claim_mapping_the_conduit_reads_from_that_env_accepts_it(
    keypair, jwks_url, monkeypatch
) -> None:
    """The render's own environment, read as the Conduit reads it, signs in a token issued to the pages
    client on every route, still refuses a third client's, and (unset) refuses the pages client's."""
    environment = _values(_with_claims(pages_client_id=PAGES_APP))["environment"]
    monkeypatch.setenv("OSPREY_CLAIM_MAPPING", environment["OSPREY_CLAIM_MAPPING"])
    mapping = ClaimMapping.from_env()
    assert mapping.pages_client_id == PAGES_APP

    def resolver_for(mapping: ClaimMapping) -> PrincipalResolver:
        return PrincipalResolver(
            _api_config(
                jwks_url,
                oidc_issuer=environment["OIDC_ISSUER"],
                oidc_audience=environment["OIDC_AUDIENCE"],
            ),
            claim_mapping=mapping,
            role_source=FakePeople(),
        )

    def resolve(resolver: PrincipalResolver, client: str):  # type: ignore[no-untyped-def]
        claims = entra_claims(azp=client, scp="access_as_user")
        claims |= {"aud": API, "iss": environment["OIDC_ISSUER"], f"{EXT}_clearance": "OFFICIAL",
                   "groups": ["20000000-0000-4000-8000-000000000001"]}  # fmt: skip
        return asyncio.run(resolver.resolve_principal(sign_token(keypair[0], claims)))

    principal = resolve(resolver_for(mapping), PAGES_APP)
    assert principal.routes is None and principal.org_unit == "unit-1"
    with pytest.raises(PrincipalResolutionError, match="Glass's client"):
        resolve(resolver_for(mapping), OTHER_APP)

    # The same render without the setting: the pages client is another client's.
    monkeypatch.setenv("OSPREY_CLAIM_MAPPING", _values(_with_claims())["environment"]["OSPREY_CLAIM_MAPPING"])
    with pytest.raises(PrincipalResolutionError, match="Glass's client"):
        resolve(resolver_for(ClaimMapping.from_env()), PAGES_APP)
