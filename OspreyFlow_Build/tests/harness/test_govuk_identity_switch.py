"""Slice PL7c, item 1: the GOV.UK identity switch, `appearance.govuk_identity` (ADR-152 decision 14, invariant I9).

Off by default; a real `true` or `false` and nothing else; left out of every rendered file while it is off (a deployment
that does not use it renders byte for byte what it did); and, on, told to the Glass (`/deployment.json`), to the sign-in
page's theme (its stylesheet's marker and its script's settings) and to the workspace's build (the compose `build.args`,
which `test_default_build_holds_no_gds_transport.py` reads). The switch is the only thing that turns the GOV.UK identity
on: under `brand: govuk` alone, nothing is told.

Rule 15: each refusal is planted in the shape the code receives it: a YAML file's own scalars (`yaml.safe_load` of the
text a person writes: `yes`, `on`, a quoted `"true"`, a number), not a hand-written stand-in.
"""

from __future__ import annotations

import json

import pytest
import yaml
from harness.keycloak_theme import (
    GOVUK_CHROME_SCRIPT,
    THEME_SCRIPT,
    render_login_theme,
)
from harness.site import render_glass_settings
from pydantic import ValidationError
from tools.layout import CORE

from schemas.deployment import AppearanceConfig, OspreyConfig

TOKENS = (CORE / "packages" / "design" / "tokens.css").read_text(encoding="utf-8")
GLASS = "http://glass.example.test:8081"


def _told(raw: dict[str, object]) -> dict[str, object]:
    config = OspreyConfig.model_validate({"appearance": raw})
    return dict(json.loads(render_glass_settings(config))["appearance"])


def test_govuk_identity_is_off_by_default() -> None:
    assert AppearanceConfig().govuk_identity is False
    assert OspreyConfig().appearance.govuk_identity is False
    assert OspreyConfig.model_validate({"appearance": {"brand": "govuk"}}).appearance.govuk_identity is False


def test_off_the_glass_is_told_nothing_new() -> None:
    told = _told({"brand": "govuk", "phase": "beta"})
    assert "govuk_identity" not in told
    assert told == {"brand": "govuk", "service_name": None, "organisation": None, "phase": "beta"}
    # Written as false, it is the same as not written at all.
    assert _told({"brand": "govuk", "phase": "beta", "govuk_identity": False}) == told


def test_on_the_glass_is_told_it() -> None:
    assert _told({"brand": "govuk", "govuk_identity": True})["govuk_identity"] is True


@pytest.mark.parametrize("written", ["yes", "on", "'true'", '"yes"', "1", "0", "null", "[true]", "maybe"])
def test_only_a_real_true_or_false_is_accepted(written: str) -> None:
    # What a person types after `govuk_identity:`, read as the loader reads a file. An unquoted `yes` or `on` is a real
    # boolean in YAML 1.1 (`safe_load` turns it into True before the schema sees it), so it is accepted as what it is;
    # every other spelling reaches the schema as a string, a number or a null and is refused in words.
    value = yaml.safe_load(f"govuk_identity: {written}")["govuk_identity"]
    if isinstance(value, bool):
        assert AppearanceConfig(govuk_identity=value).govuk_identity is value
        return
    with pytest.raises(ValidationError, match="appearance.govuk_identity must be true or false"):
        AppearanceConfig(govuk_identity=value)


def test_the_switch_means_nothing_under_the_ospreyflow_brand_in_the_sign_in_theme() -> None:
    on = AppearanceConfig(brand="ospreyflow", govuk_identity=True)
    assert render_login_theme(TOKENS, appearance=on, glass_origin=GLASS) == render_login_theme(TOKENS)


def test_under_govuk_the_sign_in_theme_is_what_it_was_while_the_switch_is_off() -> None:
    off = render_login_theme(TOKENS, appearance=AppearanceConfig(brand="govuk", phase="beta"), glass_origin=GLASS)
    assert "data-govuk-identity" not in off[THEME_SCRIPT]
    # The settings the harness writes are the script's first line; the script's own text names the key.
    assert "govukIdentity" not in off[GOVUK_CHROME_SCRIPT].split("\n", 1)[0]


def test_under_govuk_the_sign_in_theme_is_told_the_switch_when_it_is_on() -> None:
    on = AppearanceConfig(brand="govuk", phase="beta", govuk_identity=True)
    theme = render_login_theme(TOKENS, appearance=on, glass_origin=GLASS)
    assert 'document.documentElement.setAttribute("data-govuk-identity", "on");' in theme[THEME_SCRIPT]
    # The page is marked with the brand first, then the switch, before the theme script's own lines.
    assert theme[THEME_SCRIPT].index('"data-brand"') < theme[THEME_SCRIPT].index('"data-govuk-identity"')
    assert '"govukIdentity": true' in theme[GOVUK_CHROME_SCRIPT].split("\n", 1)[0]


def test_the_typeface_is_in_one_rule_that_needs_the_switch() -> None:
    """tokens.css, which the sign-in theme's stylesheet carries whole: GDS Transport named only where
    `data-govuk-identity="on"` is, so a page without the switch can never ask for it."""
    import re

    code = re.sub(r"/\*.*?\*/", "", TOKENS, flags=re.S)
    rules = [m.group(1).strip() for m in re.finditer(r"([^{}]+)\{[^}]*GDS Transport[^}]*\}", code)]
    assert rules == ['[data-brand="govuk"][data-govuk-identity="on"]']


def test_the_switch_is_a_field_the_schema_describes() -> None:
    field = AppearanceConfig.model_fields["govuk_identity"]
    assert field.default is False
    assert field.description and field.description.startswith("Default: false.")
