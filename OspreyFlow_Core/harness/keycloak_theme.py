"""The sign-in page Keycloak shows, restyled with the OspreyFlow design system.

The launcher and the workspace use `apps/workspace/src/design/tokens.css`; Keycloak's stock sign-in
page is grey, in another typeface, under the realm's name in capitals. This module renders a
Keycloak *login theme* that extends Keycloak's own (`keycloak.v2`, so password reset, error pages
and the rest still exist) and restyles it from the same tokens. Nothing here changes who can sign
in or what they may do: only how the page looks and the words on it.

Like `realm.json` and `litellm.yaml` it is a service's own config that happens to be generated, not
one of `05_DEPLOYMENT.md` §2.1's four artefacts: `harness.apply` writes it beside the compose file
and compose mounts it into Keycloak at `/opt/keycloak/themes/osprey`. It is mounted **beside**
Keycloak's own themes; mounting onto the themes directory itself would hide them.

Pure apart from `read_tokens`, which fails loudly if the design tokens are absent: an unbranded page
that looks as though it worked is worse than a stopped render that says why.
"""

from __future__ import annotations

from pathlib import Path

from harness.realm import LOGIN_THEME_NAME, REALM_DISPLAY_NAME
from harness.render import REPO_ROOT
from harness.theme_script import read_theme_script

THEME_NAME = LOGIN_THEME_NAME
#: What the realm calls itself on the sign-in page and in the tab title.
DISPLAY_NAME = REALM_DISPLAY_NAME

THEME_PROPERTIES = "login/theme.properties"
THEME_STYLESHEET = "login/resources/css/osprey.css"
THEME_MESSAGES = "login/messages/messages_en.properties"
#: The light and dark choice (ADR-072): a stylesheet cannot read the cookie the Glass saves it in.
THEME_SCRIPT = "login/resources/js/osprey-theme.js"
#: The handoff's sign-in card behaviour on Keycloak's pages (ADR-115 E2, `sign_in_form.js`).
SIGN_IN_SCRIPT = "login/resources/js/osprey-sign-in.js"
SIGN_IN_SCRIPT_SOURCE = Path(__file__).resolve().parent / "sign_in_form.js"
#: Where, beside the compose file, the theme is written and where compose mounts it from.
THEME_DIRECTORY = "keycloak-theme"

TOKENS_RELATIVE_PATH = Path("apps") / "workspace" / "src" / "design" / "tokens.css"

_PROPERTIES = """\
parent=keycloak.v2
styles=css/osprey.css
scripts=js/osprey-theme.js js/osprey-sign-in.js
"""

#: The header's wordmark. The brand splits the compound on weight alone (Osprey 700, Flow 400), so
#: Keycloak's header message, which it prints unescaped, carries one bold element. Its text is still
#: the realm's display name, which is what a screen reader reads.
#: One element, because the header is a flex row: bare text beside the `<b>` would be a second flex
#: item with the lockup's gap before it ("Osprey  Flow", seen live at ADR-115 E2).
_WORDMARK_HTML = '<span class="osprey-wordmark"><b>Osprey</b>Flow</span>'

_INSTRUCTION = (
    "For OspreyFlow accounts only. If you sign in through your organisation, reset your password "
    "there instead."
)

_MESSAGES = f"""\
loginAccountTitle=Sign in
loginTitleHtml={_WORDMARK_HTML}
doLogIn=Sign in
usernameOrEmail=Email or username
doForgotPassword=Forgot password?
emailForgotTitle=Reset your password
emailInstruction={_INSTRUCTION}
backToLogin=Back to sign in
"""

#: ADR-115 decisions 5 and 6, the handoff's words. Keycloak 26.0.8 says "Invalid username or
#: password." for a wrong password and for a locked account alike, so the lock the realm sets (five
#: failures, 15 minutes, measured) is named here; "reset your password" only where a mail server
#: can send the link. The text is a Java message format: an apostrophe is written twice.
_REFUSED = {
    True: "That email or username and password do not match an OspreyFlow account. Check for "
    "typos, or reset your password. Five failed attempts lock the account for 15 minutes.",
    False: "That email or username and password do not match an OspreyFlow account. Check for "
    "typos, or ask your OspreyFlow administrator to reset your sign-in. Five failed attempts lock "
    "the account for 15 minutes.",
}
#: Never says whether the account exists; the reset link lives as long as the realm says (1800s).
#: Keycloak does not give the message what was typed, so "what you entered" stands for it.
_SENT = (
    "If an OspreyFlow account matches what you entered, a reset link is on its way to the email "
    "address on that account. It expires in 30 minutes. Nothing after five minutes? Check your "
    "junk folder, or ask your administrator to confirm the address on your account."
)

_BRAND_MARK = (
    'url("data:image/svg+xml,'
    "%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2048%2048'%3E"
    "%3Cpath%20d='M4.9%206.7L6.4%2017.2L23.9%2011.1Z'/%3E"
    "%3Cpath%20d='M6.8%2017.9L24.3%2019.9L24.2%2011.7Z'/%3E"
    "%3Cpath%20d='M6.6%2018.6L8%2029.1L24.2%2020.7Z'/%3E"
    "%3Cpath%20d='M8.4%2030.1L9.4%2041L24.4%2021.2Z'/%3E"
    "%3Cpath%20d='M9.8%2041.2L24.4%2030.2L24.7%2021.5Z'/%3E"
    "%3Cpath%20d='M25.6%2011.9L26.2%2029.2L43.9%2025.7Z'/%3E"
    "%3C/svg%3E"
    '")'
)

#: Rules only: every colour, size and typeface is a token from the file this is appended to (a test
#: forbids a colour literal here). Written against Keycloak 26's PatternFly 5 login markup, and it
#: replaces the stock page's background picture, card, inputs and button.
_RULES = """
/* --- Keycloak sign-in page, restyled from the tokens above. ------------------------------- */
html, body, .login-pf, .login-pf-page, .pf-v5-c-login {
  background-color: var(--surface-app) !important;
  background-image: none !important;
  color: var(--text-primary);
  font-family: var(--ui);
}
/* The page is centred, so the card does not sit high on a tall window. */
.pf-v5-c-login {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
}
.pf-v5-c-login__container {
  display: block;
  box-sizing: border-box;
  width: 100%;
  max-width: 26rem;
  margin-inline: auto;
  padding: var(--sp-40) var(--sp-24);
}
/* Keycloak's own sheet puts the header in a second grid column from 1200px up, which left the name
   floating to the right of the card. One column, header first, above the card, a set distance
   away. */
.pf-v5-c-login__header {
  grid-column: 1;
  grid-row: 1;
  margin: 0 0 var(--sp-24);
  padding: 0;
  text-align: left;
}
/* The brand's horizontal lockup (spec/design/OspreyFlow_Brand_Foundations.html): the mark, a gap of
   a third of its width, then the wordmark at the screen-title size, Osprey bold and Flow regular.
   Keycloak 26 prints the header into `#kc-header-wrapper`; the mark is a mask over a block, so its
   colour is a token and it follows light and dark. */
#kc-header-wrapper {
  --lockup-mark: 36px;
  display: flex;
  align-items: center;
  gap: calc(var(--lockup-mark) / 3);
  padding: 0;
  color: var(--text-primary);
  font: 400 var(--fs-23) / var(--lh-23) var(--ui);
  letter-spacing: -0.01em;
  text-align: left;
}
#kc-header-wrapper b { font-weight: 700; }
#kc-header-wrapper::before {
  content: "";
  flex: none;
  display: block;
  width: var(--lockup-mark);
  height: var(--lockup-mark);
  background-color: var(--text-primary);
  -webkit-mask: __MARK__ center / contain no-repeat;
  mask: __MARK__ center / contain no-repeat;
}
.pf-v5-c-login__main {
  background: var(--surface-panel);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-panel);
  box-shadow: none;
  color: var(--text-primary);
}
.pf-v5-c-login__main-header, .pf-v5-c-login__main-body, .pf-v5-c-login__main-footer {
  background: transparent;
  color: var(--text-primary);
}
.pf-v5-c-login__main-header { padding: var(--sp-32) var(--sp-32) 0; }
.pf-v5-c-login__main-body { padding: var(--sp-16) var(--sp-32) var(--sp-32); }
.pf-v5-c-title, #kc-page-title, h1 {
  color: var(--text-primary);
  font: 700 var(--fs-23) / var(--lh-23) var(--ui);
}
.pf-v5-c-form { --pf-v5-c-form--GridGap: var(--sp-20); row-gap: var(--sp-20); }
.pf-v5-c-form__label { padding-block-end: var(--sp-8); }
.pf-v5-c-form__label-text, label {
  color: var(--text-secondary);
  font: 600 var(--fs-13) / var(--lh-13) var(--ui);
}
.pf-v5-c-form-control {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--r-control);
  color: var(--text-primary);
}
.pf-v5-c-form-control::before, .pf-v5-c-form-control::after { display: none; }
.pf-v5-c-form-control input, .pf-v5-c-form-control select {
  background: transparent;
  color: var(--text-primary);
  font-family: var(--ui);
}
/* One ring. The tokens give every focused element an outline of its own; the input inside the box
   would wear it as a second ring, so it carries none and the box shows a single one. */
.pf-v5-c-form-control input:focus-visible, .pf-v5-c-form-control select:focus-visible {
  outline: none;
}
.pf-v5-c-form-control:focus-within {
  border-color: var(--brass);
  box-shadow: 0 0 0 1px var(--brass);
}
/* The password box and its show button are one control: equal height, no seam, no underline. */
.pf-v5-c-input-group { display: flex; align-items: stretch; }
.pf-v5-c-input-group .pf-v5-c-form-control { flex: 1 1 auto; min-width: 0; }
.pf-v5-c-input-group .pf-v5-c-button {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-left: 0;
  border-radius: 0 var(--r-control) var(--r-control) 0;
  color: var(--text-secondary);
}
.pf-v5-c-input-group .pf-v5-c-button::before, .pf-v5-c-input-group .pf-v5-c-button::after {
  display: none;
}
.pf-v5-c-input-group .pf-v5-c-form-control:not(:last-child) {
  border-radius: var(--r-control) 0 0 var(--r-control);
}
.pf-v5-c-button.pf-m-primary {
  background: var(--brass);
  border: 1px solid var(--brass);
  border-radius: var(--r-control);
  color: var(--brass-ink);
  font: 600 var(--fs-14) / var(--lh-14) var(--ui);
  padding: var(--sp-12) var(--sp-16);
  transition: background var(--dur-fast) var(--ease);
}
.pf-v5-c-button.pf-m-primary:hover {
  background: var(--brass-hover);
  border-color: var(--brass-hover);
}
.pf-v5-c-button.pf-m-primary:active { background: var(--brass-press); }
#kc-form-buttons { margin-top: var(--sp-8); }
.pf-v5-c-button.pf-m-control, .pf-v5-c-button.pf-m-plain {
  background: transparent;
  border-color: var(--border);
  color: var(--text-secondary);
}
.pf-v5-c-alert {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  color: var(--text-primary);
}
.pf-v5-c-alert.pf-m-danger { border-color: var(--error); }
.pf-v5-c-alert.pf-m-warning { border-color: var(--warning); }
.pf-v5-c-alert.pf-m-success { border-color: var(--success); }
.pf-v5-c-helper-text__item-text, .pf-m-error { color: var(--error); }
.pf-v5-c-login__main-footer-links a, .pf-v5-c-login__main-footer-band a { color: var(--brass); }
a { color: var(--brass); }
a:hover { color: var(--brass-hover); }

/* --- ADR-115 E2: the handoff's sign-in card. ----------------------------------------------- */
.pf-v5-c-login__main-header .pf-v5-c-title, #kc-page-title {
  font: 700 var(--fs-19) / var(--lh-19) var(--ui);
}
.pf-v5-c-form-control {
  background: var(--surface-sunken);
  min-height: var(--h-control-32);
}
.pf-v5-c-form-control input {
  font: 400 var(--fs-13) / var(--lh-13) var(--mono); letter-spacing: -0.005em;
}
.pf-v5-c-form-control:has(input[aria-invalid="true"]) { border-color: var(--error); }
.pf-v5-c-button.pf-m-primary { min-height: var(--h-control-36); width: 100%; font-weight: 700; }
/* The reset page's "Back to sign in": the handoff's quiet text button, not PatternFly's outline. */
.pf-v5-c-button.pf-m-secondary {
  align-self: flex-start; width: auto; min-height: 0; padding: 0;
  background: none; border: 0; border-bottom: 1px solid var(--border-strong); border-radius: 0;
  color: var(--text-secondary); font: 400 var(--fs-13) / var(--lh-13) var(--ui);
}
.pf-v5-c-button.pf-m-secondary::after { display: none; }
.pf-v5-c-button.pf-m-secondary:hover { color: var(--brass); border-bottom-color: var(--brass); }
.osprey-lead {
  margin: 0 0 var(--sp-16); color: var(--text-tertiary);
  font: 400 var(--fs-13) / var(--lh-13) var(--ui);
}
/* Keycloak's sheet gives the form `display: grid`, which beats the `hidden` attribute. */
#kc-form-login[hidden] { display: none !important; }
.osprey-field-error {
  display: block; margin-top: var(--sp-6);
  color: var(--error); font: 400 var(--fs-12) / var(--lh-12) var(--ui);
}
.osprey-no-reset, .osprey-card-foot {
  margin: var(--sp-8) 0 0; color: var(--text-tertiary);
  font: 400 var(--fs-12) / var(--lh-12) var(--ui);
}
.osprey-card-foot {
  margin-top: var(--sp-16); padding-top: var(--sp-4); border-top: 1px solid var(--border-subtle);
}
.osprey-back {
  width: 100%; min-height: var(--h-control-34); margin-top: var(--sp-16);
  background: var(--surface-raised); border: 1px solid var(--border);
  border-radius: var(--r-control);
  color: var(--text-primary); font: 600 var(--fs-13) / var(--lh-13) var(--ui);
}
"""


def read_tokens(repo_root: Path = REPO_ROOT) -> str:
    """The design tokens as they are on disk. Raises rather than fall back to an unbranded page."""
    path = repo_root / TOKENS_RELATIVE_PATH
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise FileNotFoundError(
            f"the design tokens were not found at {path}; the sign-in page cannot be styled "
            "without them, so nothing was rendered"
        ) from error


def _rules() -> str:
    return _RULES.replace("__MARK__", _BRAND_MARK)


def read_sign_in_script() -> str:
    """The card's script as it is on disk. Raises rather than ship a form with no validation."""
    try:
        return SIGN_IN_SCRIPT_SOURCE.read_text(encoding="utf-8")
    except OSError as error:
        raise FileNotFoundError(
            f"the sign-in card's script was not found at {SIGN_IN_SCRIPT_SOURCE}; "
            "nothing was rendered"
        ) from error


def render_login_theme(tokens_css: str, *, reset_by_email: bool = False) -> dict[str, str]:
    """The theme's files, keyed by path relative to the theme's own directory. `reset_by_email` is
    whether the deployment has a mail server (ADR-115 decision 6)."""
    messages = (
        _MESSAGES
        + f"invalidUserMessage={_REFUSED[reset_by_email]}\n"
        + f"emailSentMessage={_SENT}\n"
    ).replace("'", "''")
    flag = "true" if reset_by_email else "false"
    return {
        THEME_PROPERTIES: _PROPERTIES,
        THEME_STYLESHEET: tokens_css + _rules(),
        THEME_MESSAGES: messages,
        THEME_SCRIPT: read_theme_script(),
        SIGN_IN_SCRIPT: f"window.OSPREY_RESET_BY_EMAIL = {flag};\n" + read_sign_in_script(),
    }


def write_login_theme(
    out_dir: Path, *, tokens_css: str | None = None, reset_by_email: bool = False
) -> list[Path]:
    """Writes the theme where compose mounts it: `<out_dir>/keycloak-theme/osprey/`."""
    root = out_dir / THEME_DIRECTORY / THEME_NAME
    written: list[Path] = []
    tokens = read_tokens() if tokens_css is None else tokens_css
    for name, content in sorted(render_login_theme(tokens, reset_by_email=reset_by_email).items()):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(target)
    return written
