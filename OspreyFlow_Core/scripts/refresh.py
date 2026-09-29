"""Bring a running deployment up to date with this checkout, in one command.

    PYTHONPATH=.:packages:../OspreyFlow_Build python -m scripts.refresh   # or: make refresh

`docker compose up` starts the images that already exist; it never rebuilds one, and it never
rewrites the sign-in theme that Keycloak mounts. So after any change to the code, the Glass, the
Conduit and the sign-in page each stayed as they were until someone knew which command to run for
which. This is that sequence, in order:

1. Write the sign-in theme from the design tokens, noting whether it changed.
2. `docker compose build` the OspreyFlow-owned images. Unchanged layers come from the cache.
3. `docker compose up -d --wait`, which recreates only the containers whose image changed.
4. If the theme changed, restart Keycloak (it reads a mounted theme at start) and wait for health.
5. Register the sign-in accounts again. Keycloak's database is not persisted, so a restart removes
   the demo administrator while `deployment.env` still names their password; registering is safe to
   repeat and makes the file true again.

What it never does, on purpose: render the deployment again (that mints new secrets for stores that
keep the old ones), remove a volume, force a container to be recreated, or seed. First-time set-up
is still `python -m harness.apply`. Every compose call reads the deployment's own `--env-file`.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from harness import register_sign_in
from harness.apply import _compose
from harness.keycloak_theme import (
    THEME_DIRECTORY,
    THEME_NAME,
    read_tokens,
    render_login_theme,
    write_login_theme,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = "local-lite"
DEFAULT_KEYCLOAK_PORT = 8081


class NothingToRefresh(Exception):
    """There is no rendered deployment to bring up to date."""


class RefreshFailed(Exception):
    """A step failed; the message names it and what to do."""


def _run(argv: Sequence[str]) -> None:
    result = subprocess.run(list(argv), check=False)
    if result.returncode != 0:
        raise RefreshFailed(f"`{' '.join(argv)}` exited {result.returncode}")


def _register(argv: list[str]) -> int:
    return register_sign_in.main(argv)


def _deployment_dir(repo_root: Path) -> Path:
    generated = repo_root / "deploy" / "generated"
    preferred = generated / DEFAULT_PROFILE
    if (preferred / "compose.yaml").is_file():
        return preferred
    found = sorted(p.parent for p in generated.glob("*/compose.yaml"))
    if len(found) == 1:
        return found[0]
    raise NothingToRefresh(
        "There is no single rendered deployment under deploy/generated/ to refresh. "
        "Run `python -m harness.apply` once (README.md, “Running it”) to build one."
    )


def _keycloak_port(env_file: Path) -> int:
    """`OSPREY_KEYCLOAK_PORT` from the deployment's env file; the only line read."""
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "OSPREY_KEYCLOAK_PORT":
                return int(value.strip())
    except (OSError, ValueError):
        pass
    return DEFAULT_KEYCLOAK_PORT


def _theme_changed(directory: Path, repo_root: Path) -> bool:
    """Write the theme; True when any file differs from what was on disk."""
    tokens = read_tokens(repo_root)
    root = directory / THEME_DIRECTORY / THEME_NAME
    wanted = render_login_theme(tokens)
    changed = any(
        not (root / name).is_file() or (root / name).read_text(encoding="utf-8") != content
        for name, content in wanted.items()
    )
    if changed:
        write_login_theme(directory, tokens_css=tokens)
    return changed


def refresh(
    repo_root: Path = REPO_ROOT,
    *,
    run: Callable[[Sequence[str]], None] = _run,
    register: Callable[[list[str]], int] = _register,
) -> None:
    directory = _deployment_dir(repo_root)
    compose = _compose(directory / "compose.yaml")
    theme_changed = _theme_changed(directory, repo_root)
    run([*compose, "build"])
    run([*compose, "up", "-d", "--wait"])
    if theme_changed:
        run([*compose, "restart", "keycloak"])
        run([*compose, "up", "-d", "--wait"])
    port = _keycloak_port(directory / "deployment.env")
    code = register(
        [
            "--out-root",
            str(directory.parent),
            "--profile",
            directory.name,
            "--keycloak-url",
            f"http://127.0.0.1:{port}",
        ]
    )
    if code != 0:
        raise RefreshFailed(
            "The stack is up, but the sign-in accounts could not be registered, so the demo "
            "administrator may not be able to sign in. Run `make register-sign-in` once Keycloak "
            "answers."
        )


def main() -> int:
    try:
        refresh()
    except (NothingToRefresh, RefreshFailed) as error:
        print(f"refresh: {error}", file=sys.stderr)
        return 1
    print("refresh: the deployment is up to date with this checkout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
