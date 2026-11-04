"""What the welcome page is told about the organisation's sign-in (`/deployment.json`, rendered by
`harness.site.render_glass_settings`): ADR-115 Amendment 5 (build order step 28 (a)) — the button
names the provider by the label the answers gave it (`sign_in.organisation.label`, kept as
`governance.organisation_provider.label`), and keeps ADR-115 decision 3's words without one."""

from __future__ import annotations

import json

from harness.site import render_glass_settings

from schemas.deployment import OspreyConfig


def _settings(raw: dict[str, object]) -> dict[str, object]:
    return dict(json.loads(render_glass_settings(OspreyConfig.model_validate(raw))))


def test_the_organisations_label_reaches_the_welcome_page() -> None:
    settings = _settings({
        "profile": "small",
        "network": {"public_origin": "https://osprey.example.org"},
        "governance": {"organisation_sign_in": "org",
                       "organisation_provider": {"label": "Example Department account",
                                                 "issuer": "https://login.example.org/realms/org",
                                                 "client_id": "osprey"}},
    })  # fmt: skip
    assert settings["organisation_sign_in"] == "org"
    assert settings["organisation_label"] == "Example Department account"


def test_an_alias_brokered_by_hand_has_no_label_and_says_so() -> None:
    """A deployment naming a provider it registered in Keycloak itself (Lite's
    `governance.organisation_sign_in` alone) has no label: the page keeps the plain words."""
    settings = _settings({"network": {"public_origin": "http://localhost:9999"},
                          "governance": {"organisation_sign_in": "acme-entra"}})  # fmt: skip
    assert settings["organisation_sign_in"] == "acme-entra"
    assert settings["organisation_label"] is None


def test_no_organisation_sign_in_names_no_label() -> None:
    settings = _settings({"network": {"public_origin": "http://localhost:9999"}})
    assert settings["organisation_sign_in"] is None
    assert settings["organisation_label"] is None
