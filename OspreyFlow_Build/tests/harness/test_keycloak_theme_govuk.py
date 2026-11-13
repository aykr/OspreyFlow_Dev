"""ADR-132 Amendment 2: the identity provider's sign-in page follows the deployment's brand.

Under `appearance.brand: govuk` the login theme imports GOV.UK Frontend's stylesheet from the
deployment's own origin, marks the page `data-brand="govuk"` (so the brand block in `tokens.css`
re-themes it), shows the service's name rather than the OspreyFlow wordmark, and adds the GOV.UK
header and footer. Amendment 5 (4 November 2026): no service-name band under the header; the chrome
script names the service in the page title instead. The front proxy serves `/assets/govuk/` on the
`id.` name from the Glass, so the stylesheet and its fonts are same-origin. Under the OspreyFlow
brand nothing changes: the cases below hold the theme and the routing table to what they were.
"""

from __future__ import annotations

import json

from harness.keycloak_theme import (
    GOVUK_CHROME_SCRIPT,
    THEME_MESSAGES,
    THEME_PROPERTIES,
    THEME_SCRIPT,
    THEME_STYLESHEET,
    render_login_theme,
)
from harness.site import render_caddyfile
from tools.layout import REPO as REPO_ROOT

from schemas.deployment import AppearanceConfig, OspreyConfig

TOKENS = (REPO_ROOT / "apps" / "workspace" / "src" / "design" / "tokens.css").read_text(
    encoding="utf-8"
)
GLASS = "http://govuk.ospreyflow.localhost:8081"
GOVUK = AppearanceConfig(brand="govuk", service_name="Prison Intelligence", phase="beta")


def test_the_ospreyflow_brand_renders_the_theme_it_always_did() -> None:
    plain = render_login_theme(TOKENS)
    assert render_login_theme(TOKENS, appearance=AppearanceConfig(), glass_origin=GLASS) == plain
    assert GOVUK_CHROME_SCRIPT not in plain
    assert "/assets/govuk/" not in plain[THEME_STYLESHEET]


def test_under_govuk_the_stylesheet_imports_the_gov_uk_one_first() -> None:
    css = render_login_theme(TOKENS, appearance=GOVUK, glass_origin=GLASS)[THEME_STYLESHEET]
    # An @import is honoured only before every other rule.
    assert css.startswith('@import url("/assets/govuk/govuk-frontend.css");\n')
    assert TOKENS in css


def test_under_govuk_the_page_is_marked_before_the_theme_script_runs() -> None:
    script = render_login_theme(TOKENS, appearance=GOVUK, glass_origin=GLASS)[THEME_SCRIPT]
    marked = script.index('setAttribute("data-brand", "govuk")')
    assert marked < script.index("ospreyflow_theme"), "the brand is set before the theme reads it"


def test_under_govuk_the_header_names_the_service_and_the_chrome_script_is_loaded() -> None:
    theme = render_login_theme(TOKENS, appearance=GOVUK, glass_origin=GLASS)
    assert GOVUK_CHROME_SCRIPT in theme
    assert "js/govuk-chrome.js" in theme[THEME_PROPERTIES]
    settings = theme[GOVUK_CHROME_SCRIPT].split("\n", 1)[0]
    assert settings.startswith("window.OSPREY_GOVUK = ")
    assert json.loads(settings.removeprefix("window.OSPREY_GOVUK = ").rstrip(";")) == {
        "serviceName": "Prison Intelligence",
        "organisation": None,
        "phase": "beta",
        "glassOrigin": GLASS,
    }
    messages = theme[THEME_MESSAGES]
    assert "loginTitleHtml=Prison Intelligence\n" in messages
    assert "osprey-wordmark" not in messages


def test_a_service_name_is_escaped_where_keycloak_prints_it_unescaped() -> None:
    hostile = AppearanceConfig(brand="govuk", service_name="<b>Prison</b> & Probation")
    messages = render_login_theme(TOKENS, appearance=hostile, glass_origin=GLASS)[THEME_MESSAGES]
    assert "loginTitleHtml=&lt;b&gt;Prison&lt;/b&gt; &amp; Probation\n" in messages


def test_under_govuk_the_chrome_draws_no_service_name_band() -> None:
    """ADR-132 Amendment 5, the owner's ruling of 4 November 2026: the band is removed everywhere.
    The script that ships in the theme carries no band to draw; the name it is given is for the page
    title (`govuk_sign_in.test.mjs` runs the script and checks the title)."""
    chrome = render_login_theme(TOKENS, appearance=GOVUK, glass_origin=GLASS)[GOVUK_CHROME_SCRIPT]
    assert "govuk-service-navigation" not in chrome
    assert "document.title" in chrome


def test_under_govuk_the_chrome_takes_the_header_s_crown_off_gov_uk() -> None:
    """ADR-132 Amendment 8, the owner's ruling of 13 November 2026: off gov.uk the sign-in page's header
    draws no crown, as its footer draws none (Amendment 7). The script that ships in the theme is the
    one that removes it, by the host it is served on. This reads the shipped script's text only: that the
    removal works is `govuk_sign_in.test.mjs`'s, which runs the script on both hosts."""
    chrome = render_login_theme(TOKENS, appearance=GOVUK, glass_origin=GLASS)[GOVUK_CHROME_SCRIPT]
    assert '.slice(-7) === ".gov.uk"' in chrome  # the host test, as the footer's
    removal = chrome[chrome.index("Amendment 8") :]
    assert "if (!onGovUk)" in removal and '.querySelector(".govuk-header__logotype")' in removal


def _config(appearance: dict[str, object] | None = None) -> OspreyConfig:
    raw: dict[str, object] = {"network": {"public_origin": GLASS}}
    if appearance:
        raw["appearance"] = appearance
    return OspreyConfig.model_validate(raw)


def test_under_govuk_the_sign_in_name_serves_the_gov_uk_assets_from_the_glass() -> None:
    caddyfile = render_caddyfile(_config({"brand": "govuk"}))
    site = caddyfile[caddyfile.index("http://id.govuk.ospreyflow.localhost") :]
    site = site[: site.index("\n}\n")]
    assert "handle /assets/govuk/* {\n\t\treverse_proxy workspace:8080\n\t}" in site
    assert "handle {\n\t\treverse_proxy keycloak:8080\n\t}" in site


def test_under_the_ospreyflow_brand_the_routing_table_is_unchanged() -> None:
    assert "/assets/govuk/" not in render_caddyfile(_config())


def test_under_govuk_the_words_name_no_product_and_the_title_is_not_repeated() -> None:
    """Keycloak's own title above the card stays hidden, as on the Glass's sign-in page, which names
    the service only in the page title since Amendment 5; the messages name no product on a GOV.UK
    service."""
    for reset_by_email in (True, False):
        theme = render_login_theme(
            TOKENS, reset_by_email=reset_by_email, appearance=GOVUK, glass_origin=GLASS
        )
        assert "OspreyFlow" not in theme[THEME_MESSAGES]
    css = render_login_theme(TOKENS, appearance=GOVUK, glass_origin=GLASS)[THEME_STYLESHEET]
    assert '[data-brand="govuk"] #kc-header { display: none; }' in css


# ADR-132 Amendment 7: the deployment's own banner text, on the sign-in page as in the Glass.
DISCLAIMER = "Demonstration only: this is not a government service, and all data is synthetic."


def _chrome_settings(appearance: AppearanceConfig) -> dict[str, object]:
    chrome = render_login_theme(TOKENS, appearance=appearance, glass_origin=GLASS)[
        GOVUK_CHROME_SCRIPT
    ]
    first = chrome.split("\n", 1)[0]
    return json.loads(first.removeprefix("window.OSPREY_GOVUK = ").rstrip(";"))


def test_the_banner_text_reaches_the_sign_in_page_when_set() -> None:
    told = _chrome_settings(GOVUK.model_copy(update={"banner_text": DISCLAIMER, "phase": "none"}))
    assert told["bannerText"] == DISCLAIMER
    assert told["phase"] == "none"


def test_unset_banner_text_leaves_the_sign_in_page_byte_for_byte_as_it_was() -> None:
    """Nothing changes for a deployment that names none: not even a `bannerText: null`."""
    assert "bannerText" not in _chrome_settings(GOVUK)
    assert render_login_theme(TOKENS, appearance=GOVUK, glass_origin=GLASS) == render_login_theme(
        TOKENS, appearance=AppearanceConfig(**GOVUK.model_dump()), glass_origin=GLASS
    )
