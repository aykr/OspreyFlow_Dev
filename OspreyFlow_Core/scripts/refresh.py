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

It also brings the deployment's models up to date with its own `osprey.yaml` (ADR-095): the chosen
extraction model's pull line in `compose.yaml`, the proxy's routing table `litellm.yaml`, and the
model lines of `deployment.env`, each exactly as `harness.render` writes them, and restarts the
proxy when its table changed. Nothing else in those files is touched, and no secret changes.

What it never does, on purpose: render the deployment again (that mints new secrets for stores that
keep the old ones), remove a volume, force a container to be recreated, or seed. First-time set-up
is still `python -m harness.apply`. Every compose call reads the deployment's own `--env-file`.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import yaml
from harness import register_sign_in
from harness.apply import _compose
from harness.keycloak_theme import (
    THEME_DIRECTORY,
    THEME_NAME,
    read_tokens,
    render_login_theme,
    write_login_theme,
)
from harness.render import load_config, render_litellm_config, render_ollama_pull_script

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


#: The `deployment.env` lines that name the deployment's models (ADR-095), and the line rendered
#: just before them.
_MODEL_LINES = (
    "OSPREY_EXTRACTION_MODEL",
    "OSPREY_VISION_MODEL",
    "OSPREY_TRANSCRIPTION_MODEL",
    "OSPREY_EMBEDDING_MODEL",
)
_BEFORE_MODELS = "OSPREY_MODELS_LOCAL_ONLY="


def _models_up_to_date(directory: Path) -> bool:
    """Write the model parts of the deployment's files from its `osprey.yaml`, as `render` would;
    return whether the proxy's routing table changed. A deployment with no `osprey.yaml` beside it
    is left alone."""
    config_path = directory / "osprey.yaml"
    if not config_path.is_file():
        return False
    config = load_config(config_path)

    compose_path = directory / "compose.yaml"
    text = compose_path.read_text(encoding="utf-8")
    header_end = text.find("\nname:") + 1
    document = yaml.safe_load(text)
    ollama = document.get("services", {}).get("ollama")
    wanted_command = [render_ollama_pull_script(config)]
    if ollama is not None and ollama.get("command") != wanted_command:
        ollama["command"] = wanted_command
        body = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
        compose_path.write_text(text[:header_end] + body, encoding="utf-8")

    env_path = directory / "deployment.env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    models = config.models
    wanted = [
        f"OSPREY_EXTRACTION_MODEL={models.extraction}",
        f"OSPREY_VISION_MODEL={models.vision}",
        f"OSPREY_TRANSCRIPTION_MODEL={models.transcription}",
        f"OSPREY_EMBEDDING_MODEL={models.embedding}",
    ]
    kept = [line for line in lines if line.split("=", 1)[0] not in _MODEL_LINES]
    at = next((i + 1 for i, line in enumerate(kept) if line.startswith(_BEFORE_MODELS)), len(kept))
    updated = kept[:at] + wanted + kept[at:]
    if updated != lines:
        env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")

    proxy_path = directory / "litellm.yaml"
    routing = render_litellm_config(config)
    if not proxy_path.is_file() or proxy_path.read_text(encoding="utf-8") != routing:
        proxy_path.write_text(routing, encoding="utf-8")
        return True
    return False


def refresh(
    repo_root: Path = REPO_ROOT,
    *,
    run: Callable[[Sequence[str]], None] = _run,
    register: Callable[[list[str]], int] = _register,
) -> None:
    directory = _deployment_dir(repo_root)
    compose = _compose(directory / "compose.yaml")
    theme_changed = _theme_changed(directory, repo_root)
    proxy_changed = _models_up_to_date(directory)
    run([*compose, "build"])
    run([*compose, "up", "-d", "--wait"])
    if proxy_changed:
        # The proxy reads its routing table at start; `up` recreates the Ollama and API
        # containers itself, since their command and environment file changed.
        run([*compose, "restart", "litellm"])
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
