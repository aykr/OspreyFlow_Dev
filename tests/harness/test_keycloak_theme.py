"""The sign-in page Keycloak shows, in the design system's own colours and type.

Seen on the owner's deployment: the launcher and the workspace use the OspreyFlow design system, and
then Keycloak's stock grey sign-in page appeared in the middle of the journey. `harness/
keycloak_theme.py` produces a Keycloak login theme from `apps/workspace/src/design/tokens.css` (the
authoritative source: "Do not introduce a colour that is not defined here").

What a theme can get wrong without anything failing loudly: Keycloak falls back to its stock page
when the theme is missing, misnamed, or unreadable, and a stylesheet that names a colour of its own
drifts from the design system without any test noticing. Each test below names what it would catch.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from harness.keycloak_theme import (
    DISPLAY_NAME,
    THEME_NAME,
    THEME_PROPERTIES,
    THEME_STYLESHEET,
    read_tokens,
    render_login_theme,
    write_login_theme,
)
from harness.realm import render_realm
from harness.render import _render_compose, service_images

from schemas.deployment import OspreyConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKENS = (REPO_ROOT / "apps" / "workspace" / "src" / "design" / "tokens.css").read_text(
    encoding="utf-8"
)


def _config() -> OspreyConfig:
    return OspreyConfig.model_validate(
        yaml.safe_load("network:\n  public_origin: http://localhost:9999\n")
    )


def _theme() -> dict[str, str]:
    return render_login_theme(TOKENS)


def _own_rules() -> str:
    """The stylesheet after the design tokens, i.e. only what this module wrote."""
    css = _theme()[THEME_STYLESHEET]
    assert css.startswith(TOKENS)
    return css[len(TOKENS) :]


def test_the_stylesheet_the_theme_names_is_one_of_the_files_it_produces() -> None:
    """Catches a stylesheet path that Keycloak cannot find: it then quietly shows its stock page."""
    properties = _theme()[THEME_PROPERTIES]
    match = re.search(r"^styles=(\S+)$", properties, flags=re.MULTILINE)
    assert match is not None
    assert f"login/resources/{match.group(1)}" == THEME_STYLESHEET


def test_the_theme_extends_keycloaks_own_login_theme_rather_than_replacing_its_forms() -> None:
    """Catches a theme with no parent: it would have to supply every screen, including password
    reset and error pages, and any it missed would fail to render at all."""
    assert re.search(r"^parent=keycloak\.v2$", _theme()[THEME_PROPERTIES], flags=re.MULTILINE)


def test_the_design_systems_tokens_are_carried_in_full_and_unaltered() -> None:
    """Catches a copy of the palette that has drifted, or a theme built from a stale file."""
    assert _theme()[THEME_STYLESHEET].startswith(TOKENS)


def test_the_stylesheet_introduces_no_colour_of_its_own() -> None:
    """The tokens file's rule, applied to this module's own rules: every colour is a token."""
    own = _own_rules()
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", own)
    assert not re.search(r"\b(?:rgb|rgba|hsl|hsla|oklch|oklab)\(", own)
    assert "var(--brass)" in own and "var(--surface-panel)" in own


def test_the_stylesheet_reaches_every_part_of_the_stock_page_it_replaces() -> None:
    """Catches a restyle that leaves a grey patch: the background picture, the white card, the
    input boxes and the blue button are four separate rules on the stock page."""
    own = _own_rules()
    for stock_part in (
        "pf-v5-c-login__main",
        "pf-v5-c-form-control",
        "pf-m-primary",
        "background-image: none",
    ):
        assert stock_part in own, stock_part


def test_the_page_says_ospreyflow_and_sign_in_in_plain_words() -> None:
    """The stock heading is "Sign in to your account" under a shouted realm name."""
    messages = _theme()["login/messages/messages_en.properties"]
    assert f"loginAccountTitle=Sign in to {DISPLAY_NAME}" in messages
    assert "doLogIn=Sign in" in messages


def test_the_realm_selects_the_theme_and_names_itself() -> None:
    """Catches a theme that is built and mounted but never chosen: the realm names it."""
    realm = render_realm(_config(), realm_name="osprey")
    assert realm["loginTheme"] == THEME_NAME
    assert realm["displayName"] == DISPLAY_NAME


def test_compose_mounts_the_theme_beside_keycloaks_own_and_not_over_them() -> None:
    """Catches the classic mistake: mounting onto the themes directory itself hides Keycloak's
    built-in themes, and the whole realm then has no sign-in page at all."""
    compose = _render_compose(_config(), service_images(_config()))
    (line,) = [ln for ln in compose.splitlines() if "keycloak-theme" in ln]
    assert line.strip().lstrip("- ").strip("'\"") == (
        f"./keycloak-theme/{THEME_NAME}:/opt/keycloak/themes/{THEME_NAME}:ro"
    )


def test_writing_the_theme_puts_every_file_where_compose_mounts_it(tmp_path: Path) -> None:
    written = write_login_theme(tmp_path, tokens_css=TOKENS)
    root = tmp_path / "keycloak-theme" / THEME_NAME
    assert sorted(p.relative_to(root).as_posix() for p in written) == sorted(_theme())
    assert (root / THEME_PROPERTIES).read_text(encoding="utf-8") == _theme()[THEME_PROPERTIES]


def test_a_missing_design_tokens_file_stops_the_render_and_says_so(tmp_path: Path) -> None:
    """Catches a silent fallback: better no theme, said plainly, than an unbranded page that looks
    like it worked."""
    with pytest.raises(FileNotFoundError, match="design tokens"):
        read_tokens(tmp_path)


def test_the_real_tokens_file_is_found_from_the_repository_root() -> None:
    assert read_tokens(REPO_ROOT) == TOKENS


def test_apply_writes_the_theme_beside_the_compose_file_it_is_mounted_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real `apply`, stopped at its preflight stage (no Docker needed) by a check that fails.
    Catches a theme that is rendered and tested but never written: compose would then mount a
    directory that does not exist and the realm would name a theme Keycloak cannot find.
    The realm is written by the same step, so it is the reference for 'beside the compose file'."""
    from types import SimpleNamespace

    from harness.preflight.result import Status

    from harness import apply

    failing = SimpleNamespace(
        check=lambda context: SimpleNamespace(
            status=Status.FAIL, check="stop here", what_is_wrong="test", what_to_do="none"
        )
    )
    monkeypatch.setattr(apply, "ALL_CHECKS", [failing])

    apply.main(["--out-root", str(tmp_path), "--no-build"])

    (profile_dir,) = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert (profile_dir / "realm.json").is_file()
    theme = profile_dir / "keycloak-theme" / THEME_NAME
    assert (theme / THEME_PROPERTIES).is_file()
    assert (theme / THEME_STYLESHEET).read_text(encoding="utf-8").startswith(TOKENS)
