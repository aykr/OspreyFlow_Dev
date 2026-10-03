"""The light and dark choice for the pages that are not React (ADR-072).

`theme_cookie.js`, beside this file, is one small script. The launcher's welcome page carries it in
its head and Keycloak's sign-in theme ships it as a file; the Glass and the setup harness do the
same job in `apps/workspace/src/theme/theme.ts`. All of them read and write one cookie, which is how
a choice made on one page (they are on different ports of one host) reaches the others.
"""

from __future__ import annotations

from pathlib import Path

THEME_SCRIPT_PATH = Path(__file__).resolve().parent / "theme_cookie.js"


def read_theme_script() -> str:
    """The script as it is on disk. Raises rather than ship a page that cannot follow the choice."""
    try:
        return THEME_SCRIPT_PATH.read_text(encoding="utf-8")
    except OSError as error:
        raise FileNotFoundError(
            f"the light and dark script was not found at {THEME_SCRIPT_PATH}; "
            "the page would stay dark whatever was chosen, so nothing was rendered"
        ) from error
