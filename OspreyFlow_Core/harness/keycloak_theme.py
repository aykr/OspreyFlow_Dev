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

THEME_NAME = LOGIN_THEME_NAME
#: What the realm calls itself on the sign-in page and in the tab title.
DISPLAY_NAME = REALM_DISPLAY_NAME

THEME_PROPERTIES = "login/theme.properties"
THEME_STYLESHEET = "login/resources/css/osprey.css"
THEME_MESSAGES = "login/messages/messages_en.properties"
#: Where, beside the compose file, the theme is written and where compose mounts it from.
THEME_DIRECTORY = "keycloak-theme"

TOKENS_RELATIVE_PATH = Path("apps") / "workspace" / "src" / "design" / "tokens.css"

_PROPERTIES = """\
parent=keycloak.v2
styles=css/osprey.css
"""

_MESSAGES = f"""\
loginAccountTitle=Sign in to {DISPLAY_NAME}
doLogIn=Sign in
"""

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
.pf-v5-c-login__container {
  display: block;
  max-width: 26rem;
  margin-inline: auto;
  padding: var(--sp-40) var(--sp-24);
}
/* Keycloak's own sheet puts the header in a second grid column from 1200px up, which left the name
   floating to the right of the card. One column, header first, above the card. */
.pf-v5-c-login__header {
  grid-column: 1;
  grid-row: 1;
  padding: 0 0 var(--sp-24);
  text-align: left;
}
#kc-header-wrapper { padding: 0; text-align: left; }
/* The brand mark stands in for the loose wordmark. The text stays in the page (it is the realm's
   accessible name) but is not displayed; the mark is a mask, so its colour is a token. */
.kc-logo-text { font-size: 0; line-height: 0; }
.kc-logo-text::before {
  content: "";
  display: block;
  width: var(--sp-40);
  height: var(--sp-40);
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
.pf-v5-c-title, #kc-page-title, h1 {
  color: var(--text-primary);
  font: 700 var(--fs-23) / var(--lh-23) var(--ui);
}
.pf-v5-c-form__label-text, label { color: var(--text-secondary); font-family: var(--ui); }
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
.pf-v5-c-form-control:focus-within {
  border-color: var(--brass);
  outline: 2px solid var(--brass);
  outline-offset: 2px;
}
.pf-v5-c-button.pf-m-primary {
  background: var(--brass);
  border: 1px solid var(--brass);
  border-radius: var(--r-control);
  color: var(--brass-ink);
  font: 600 var(--fs-14) / var(--lh-14) var(--ui);
  transition: background var(--dur-fast) var(--ease);
}
.pf-v5-c-button.pf-m-primary:hover {
  background: var(--brass-hover);
  border-color: var(--brass-hover);
}
.pf-v5-c-button.pf-m-primary:active { background: var(--brass-press); }
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


def render_login_theme(tokens_css: str) -> dict[str, str]:
    """The theme's files, keyed by path relative to the theme's own directory."""
    return {
        THEME_PROPERTIES: _PROPERTIES,
        THEME_STYLESHEET: tokens_css + _rules(),
        THEME_MESSAGES: _MESSAGES,
    }


def write_login_theme(out_dir: Path, *, tokens_css: str | None = None) -> list[Path]:
    """Writes the theme where compose mounts it: `<out_dir>/keycloak-theme/osprey/`."""
    root = out_dir / THEME_DIRECTORY / THEME_NAME
    written: list[Path] = []
    for name, content in sorted(
        render_login_theme(read_tokens() if tokens_css is None else tokens_css).items()
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(target)
    return written
