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
from tools.layout import REPO as REPO_ROOT

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


THEME_SCRIPT = (REPO_ROOT / "harness" / "theme_cookie.js").read_text(encoding="utf-8")


def test_the_sign_in_page_loads_the_shared_light_and_dark_script() -> None:
    """ADR-072. A stylesheet cannot read a cookie, so without a script the sign-in page stays dark
    whatever the analyst chose in the Glass. Catches a script that is produced but never named in
    the theme (Keycloak then never loads it), and one that differs from the shared file."""
    files = _theme()
    properties = files[THEME_PROPERTIES]
    match = re.search(r"^scripts=(.+)$", properties, flags=re.MULTILINE)
    assert match is not None, "theme.properties does not name a script"
    # Keycloak's list is space-separated (ADR-115 E2 added the card's script beside this one).
    named = match.group(1).split()
    assert "js/osprey-theme.js" in named
    assert all(f"login/resources/{name}" in files for name in named)
    assert files["login/resources/js/osprey-theme.js"] == THEME_SCRIPT


def test_the_page_says_ospreyflow_and_sign_in_in_plain_words() -> None:
    """The stock heading is "Sign in to your account" under a shouted realm name. ADR-115 E2: the
    card says "Sign in" under the OspreyFlow lockup, as the handoff's card does."""
    messages = _theme()["login/messages/messages_en.properties"]
    assert "loginAccountTitle=Sign in\n" in messages
    assert "doLogIn=Sign in" in messages
    assert DISPLAY_NAME == "OspreyFlow"


# --- ADR-115 E2: the handoff's sign-in card, on Keycloak's own pages ------------------------------
# Keycloak 26.0.8's stock words, measured: "Username or email", "Forgot Password?", "Forgot Your
# Password?", "Enter your username or email address and we will send you instructions…",
# "« Back to Login", and "Invalid username or password." for a wrong password and for a locked
# account alike (it never says an account is locked).


def _messages(reset_by_email: bool) -> dict[str, str]:
    text = render_login_theme(TOKENS, reset_by_email=reset_by_email)["login/messages/messages_en.properties"]
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def test_the_card_uses_the_handoffs_words() -> None:
    messages = _messages(reset_by_email=True)
    assert messages["usernameOrEmail"] == "Email or username"
    assert messages["doForgotPassword"] == "Forgot password?"
    assert messages["emailForgotTitle"] == "Reset your password"
    assert messages["emailInstruction"] == (
        "For OspreyFlow accounts only. If you sign in through your organisation, reset your password there instead."
    )
    assert messages["backToLogin"] == "Back to sign in"


def test_a_refused_sign_in_names_the_lock_and_a_way_back_that_this_deployment_has() -> None:
    """ADR-115 decisions 5 and 6: the lock-out the copy names is the realm's (5 failures, 15
    minutes); "reset your password" only where a mail server can send the link."""
    assert _messages(reset_by_email=True)["invalidUserMessage"] == (
        "That email or username and password do not match an OspreyFlow account. Check for typos, or "
        "reset your password. Five failed attempts lock the account for 15 minutes."
    )
    assert _messages(reset_by_email=False)["invalidUserMessage"] == (
        "That email or username and password do not match an OspreyFlow account. Check for typos, or "
        "ask your OspreyFlow administrator to reset your sign-in. Five failed attempts lock the account "
        "for 15 minutes."
    )


def test_check_your_email_never_says_whether_the_account_exists_and_names_the_expiry() -> None:
    sent = _messages(reset_by_email=True)["emailSentMessage"]
    assert sent.startswith("If an OspreyFlow account matches what you entered, a reset link is on its way")
    assert "It expires in 30 minutes." in sent


def test_the_card_script_is_loaded_and_told_whether_reset_by_email_exists() -> None:
    for reset_by_email in (True, False):
        theme = render_login_theme(TOKENS, reset_by_email=reset_by_email)
        assert "js/osprey-sign-in.js" in theme[THEME_PROPERTIES]
        script = theme["login/resources/js/osprey-sign-in.js"]
        assert script.startswith(f"window.OSPREY_RESET_BY_EMAIL = {'true' if reset_by_email else 'false'};\n")


def test_the_realm_locks_after_five_failures_for_fifteen_minutes_and_resets_by_email_only_with_mail() -> None:
    """Measured on Keycloak 26.0.8 with these settings: four wrong passwords then the right one
    signs in; five wrong then the right one is refused, locked for exactly 900 seconds; a reset link
    lives 1800 seconds; a reset asked for with no mail server ends on Keycloak's error page."""
    realm = render_realm(_config())
    assert {k: realm[k] for k in (
        "bruteForceProtected", "failureFactor", "waitIncrementSeconds", "maxFailureWaitSeconds",
        "permanentLockout", "actionTokenGeneratedByUserLifespan", "resetPasswordAllowed",
    )} == {
        "bruteForceProtected": True, "failureFactor": 5, "waitIncrementSeconds": 900,
        "maxFailureWaitSeconds": 900, "permanentLockout": False,
        "actionTokenGeneratedByUserLifespan": 1800, "resetPasswordAllowed": False,
    }  # fmt: skip
    mailed = OspreyConfig.model_validate(
        yaml.safe_load(
            "network:\n  public_origin: http://localhost:9999\n"
            "mail:\n  host: smtp.test\n  port: 587\n  from_address: osprey@acme.test\n"
        )
    )
    assert render_realm(mailed)["resetPasswordAllowed"] is True


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

    from harness import apply
    from harness.preflight.result import Status

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


def test_the_wordmark_sits_above_the_card_as_the_logo_and_not_beside_it() -> None:
    """Seen on the owner's deployment: at desktop widths "OspreyFlow" floated to the right of the
    sign-in card as loose text. Keycloak's own stylesheet puts the login container's header in a
    second grid column from 1200px up, and this theme's rules did not undo that. Catches a page
    where the header is still placed in a column beside the card: it must be a single column with
    the header first, and the loose text replaced by the brand mark."""
    own = _own_rules()
    container = re.search(r"\.pf-v5-c-login__container\s*\{([^}]*)\}", own)
    assert container is not None
    assert "display: block" in container.group(1)
    assert "grid-template-columns" not in container.group(1) or "1fr" in container.group(1)
    header = re.search(r"\.pf-v5-c-login__header\s*\{([^}]*)\}", own)
    assert header is not None
    assert "grid-column: 1" in header.group(1)
    assert "grid-row: 1" in header.group(1)


def test_the_brand_mark_is_drawn_from_the_brand_foundations_and_takes_its_colour_from_a_token() -> (
    None
):
    """Catches a logo that is a different drawing from the brand's, or one filled with a colour of
    its own. The six paths are the mark in `spec/design/OspreyFlow_Brand_Foundations.html`; the
    mark is a mask over a token-coloured block, so it follows the theme."""
    own = _own_rules()
    foundations = (
        REPO_ROOT.parent
        / "OspreyFlow_Build"
        / "spec"
        / "design"
        / "OspreyFlow_Brand_Foundations.html"
    ).read_text(encoding="utf-8")
    brand_paths = re.findall(r'<path d=\\"(M[^"\\]*)\\"', foundations)[:6]
    assert len(brand_paths) == 6
    decoded = own.replace("%20", " ").replace("%3C", "<").replace("%3E", ">")
    for path in brand_paths:
        assert f"d='{path}'" in decoded, path
    mark = re.search(r"#kc-header-wrapper::before\s*\{([^}]*)\}", own)
    assert mark is not None
    assert "background-color: var(--text-primary)" in mark.group(1)
    assert "mask:" in mark.group(1)


def test_the_logo_is_attached_to_the_header_keycloak_26_actually_renders() -> None:
    """Seen on the owner's deployment: no mark at all, only the word "OspreyFlow" in small type
    above the card. The rules named `.kc-logo-text`, a class of Keycloak's older themes; the
    `keycloak.v2` page of Keycloak 26 renders `#kc-header-wrapper` inside `.pf-v5-c-login__header`
    and has no such element, so every logo rule matched nothing and no test noticed, because the
    tests read the stylesheet and not the page. Catches a logo rule aimed at a class the page does
    not have."""
    own = _own_rules()
    assert "kc-logo-text" not in own
    assert re.search(r"#kc-header-wrapper::before\s*\{", own)


def test_the_header_is_the_brands_horizontal_lockup() -> None:
    """The brand foundations' lockup: the mark, a gap of one third of the mark's width, and the
    wordmark in the screen-title size, centred on the mark. Catches a mark with no wordmark beside
    it, a gap that is not a third of the mark, and a wordmark in the wrong size."""
    own = _own_rules()
    wrapper = re.search(r"#kc-header-wrapper\s*\{([^}]*)\}", own)
    assert wrapper is not None
    rule = wrapper.group(1)
    assert "display: flex" in rule
    assert "align-items: center" in rule
    assert "gap: calc(var(--lockup-mark) / 3)" in rule
    assert "--lockup-mark: 36px" in rule
    assert "var(--fs-23)" in rule
    mark = re.search(r"#kc-header-wrapper::before\s*\{([^}]*)\}", own)
    assert mark is not None
    assert "width: var(--lockup-mark)" in mark.group(1)
    assert "height: var(--lockup-mark)" in mark.group(1)


def test_the_wordmark_splits_on_weight_alone_and_still_reads_as_the_realm_name() -> None:
    """The brand: Osprey at 700, Flow at 400, no divider and no colour change. Keycloak prints the
    header from the `loginTitleHtml` message, so the theme sets it; its visible text must stay the
    realm's display name (the page's accessible name). Catches a wordmark whose words differ from
    the realm's, and a weight rule with nothing to apply to."""
    messages = _theme()["login/messages/messages_en.properties"]
    match = re.search(r"^loginTitleHtml=(.*)$", messages, flags=re.MULTILINE)
    assert match is not None
    # One element: the header is a flex row, so a bare `<b>Osprey</b>Flow` made two flex items with
    # the lockup's gap between them — "Osprey  Flow" on the live page (found at ADR-115 E2).
    assert match.group(1) == '<span class="osprey-wordmark"><b>Osprey</b>Flow</span>'
    assert re.sub(r"<[^>]+>", "", match.group(1)) == DISPLAY_NAME
    own = _own_rules()
    bold = re.search(r"#kc-header-wrapper b\s*\{([^}]*)\}", own)
    assert bold is not None
    assert "font-weight: 700" in bold.group(1)
    assert "font: 400 " in re.search(r"#kc-header-wrapper\s*\{([^}]*)\}", own).group(1)  # type: ignore[union-attr]


def test_the_sign_in_card_is_centred_on_the_page_and_not_left_high_with_a_gap_above_it() -> None:
    """Seen on the owner's deployment: the wordmark and card sat in the upper-middle of a tall dark
    page with a wide empty band between them. Catches a page that is not centred vertically and a
    header with no set distance to the card."""
    own = _own_rules()
    page = re.search(r"^\.pf-v5-c-login\s*\{([^}]*)\}", own, flags=re.MULTILINE)
    assert page is not None
    for declaration in ("display: flex", "justify-content: center", "min-height: 100vh"):
        assert declaration in page.group(1), declaration
    header = re.search(r"\.pf-v5-c-login__header\s*\{([^}]*)\}", own)
    assert header is not None
    assert "margin: 0" in header.group(1)


def test_a_focused_field_has_one_ring_not_two() -> None:
    """Seen on the owner's deployment: the username field wore a heavy double brass outline. The
    design tokens give every focused element an outline of its own (`*:focus-visible`), and this
    theme added a second on the box around the input, so both showed. Catches either one coming
    back: the input itself carries none and the box carries a single ring."""
    own = _own_rules()
    inner = re.search(r"\.pf-v5-c-form-control input:focus-visible[^{]*\{([^}]*)\}", own)
    assert inner is not None
    assert "outline: none" in inner.group(1)
    box = re.search(r"\.pf-v5-c-form-control:focus-within\s*\{([^}]*)\}", own)
    assert box is not None
    assert "border-color: var(--brass)" in box.group(1)
    assert "outline" not in box.group(1).replace("outline: none", "")
    assert box.group(1).count("box-shadow") == 1


def test_the_password_box_and_its_show_button_are_one_control() -> None:
    """Seen on the owner's deployment: the password field stopped short of the page's edge, the
    eye button floated beside it, and a stray line ran under the button. Catches the group not
    stretching its two parts to one height, the button keeping its own underline, and a seam
    border between the two."""
    own = _own_rules()
    group = re.search(r"\.pf-v5-c-input-group\s*\{([^}]*)\}", own)
    assert group is not None
    assert "display: flex" in group.group(1)
    assert "align-items: stretch" in group.group(1)
    button = re.search(r"\.pf-v5-c-input-group \.pf-v5-c-button\s*\{([^}]*)\}", own)
    assert button is not None
    assert "border-left: 0" in button.group(1)
    assert re.search(r"\.pf-v5-c-input-group \.pf-v5-c-button::after\s*\{[^}]*display: none", own)


def test_each_label_has_room_above_its_field_and_the_fields_are_spaced_evenly() -> None:
    """Seen on the owner's deployment: "Username or email" sat on top of its input with the input's
    ring running through the label. Catches a label with no clearance and a form with no set gap."""
    own = _own_rules()
    label = re.search(r"\.pf-v5-c-form__label\s*\{([^}]*)\}", own)
    assert label is not None
    assert "padding-block-end: var(--sp-8)" in label.group(1)
    form = re.search(r"\.pf-v5-c-form\s*\{([^}]*)\}", own)
    assert form is not None
    assert "--pf-v5-c-form--GridGap: var(--sp-20)" in form.group(1)


def test_a_form_the_card_hides_stays_hidden() -> None:
    """ADR-115 E2, found live: Keycloak's sheet gives the login form `display: grid`, which beats the
    `hidden` attribute, so "Check your email" showed the form it had hidden."""
    assert re.search(r"#kc-form-login\[hidden\]\s*\{\s*display:\s*none\s*!important;", _own_rules())
