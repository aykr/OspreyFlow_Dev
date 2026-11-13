"""ADR-132 Amendment 7: the GOV.UK phase banner's words are the deployment's to set
(`appearance.banner_text`), for a disclaimer such as the demonstration's. They reach the Glass
through
`/deployment.json`; the sign-in page's are `test_keycloak_theme_govuk.py`'s. Unset, every rendered
file is as it was: the setting is left out, never written as `null`."""

from __future__ import annotations

import json

import pytest
from harness.site import render_glass_settings
from pydantic import ValidationError

from schemas.deployment import AppearanceConfig, OspreyConfig

DISCLAIMER = "Demonstration only: this is not a government service, and all data is synthetic."


def _appearance(raw: dict[str, object]) -> dict[str, object]:
    config = OspreyConfig.model_validate({"appearance": raw})
    return dict(json.loads(render_glass_settings(config))["appearance"])


def test_the_banner_text_reaches_the_glass() -> None:
    told = _appearance({"brand": "govuk", "phase": "none", "banner_text": DISCLAIMER})
    assert told["banner_text"] == DISCLAIMER


def test_unset_the_glass_is_told_exactly_what_it_was() -> None:
    told = _appearance({"brand": "govuk", "phase": "beta"})
    assert "banner_text" not in told
    assert told == {"brand": "govuk", "service_name": None, "organisation": None, "phase": "beta"}


@pytest.mark.parametrize("words", ["", "   ", "x" * 201, "two\nlines"])
def test_banner_text_must_be_one_line_of_words(words: str) -> None:
    with pytest.raises(ValidationError, match="one line of at most 200 characters"):
        AppearanceConfig(banner_text=words)


def test_the_owners_wording_is_accepted() -> None:
    assert AppearanceConfig(banner_text=DISCLAIMER).banner_text == DISCLAIMER
