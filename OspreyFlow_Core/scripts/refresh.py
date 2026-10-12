"""Bring a running deployment up to date with this checkout, in one command.

    PYTHONPATH=.:packages python -m scripts.refresh   # or: ospreyflow start --build

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

A third-party store the checkout pins at a new version (ADR-101: ArcadeDB 26.10.1) is moved to it:
the service takes the rendered image, its probe and the rendered value of each setting the render
names, and
`versions.lock` names the new tag. A setting of the operator's own stays, and a service already at
the checkout's version is not touched, so an operator's edit to it is theirs.

It also brings the deployment's models up to date with its own `osprey.yaml` (ADR-095): the chosen
extraction model's pull line in `compose.yaml`, the proxy's routing table `litellm.yaml`, and the
model lines of `deployment.env`, each exactly as `harness.render` writes them, and restarts the
proxy when its table changed. Nothing else in those files is touched, and no secret changes. The
Glass's `/deployment.json` (`glass.json`, no secret in it) is written as the checkout renders it.

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
from harness.render import (
    _render_compose,
    load_config,
    render_litellm_config,
    render_ollama_pull_script,
    service_images,
)
from harness.site import answer_localhost_with_loopback, deployment_origins

from schemas.deployment import OspreyConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = "local-lite"


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


def _identity_origin(env_file: Path) -> str:
    """Where this machine reaches the deployment's Keycloak: its identity origin through the front
    proxy (ADR-114 Amendment 4), or a pre-B3 deployment's published port."""
    return deployment_origins(env_file)[1]


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


def _like_the_deployment(config: OspreyConfig, services: dict, directory: Path) -> OspreyConfig:
    """Build or pull as the deployment does. `apply --build` builds the owned images from the
    checkout but leaves the copied `osprey.yaml` without `source_path`, so the mode is read from the
    deployment itself (found on the owner's: the recogniser was added in pull mode, a registry image
    that does not exist)."""
    api = services.get("api")
    if isinstance(api, dict) and "build" in api and config.components.source_path is None:
        root = directory.parent.parent.parent
        return config.model_copy(
            update={"components": config.components.model_copy(update={"source_path": str(root)})}
        )
    return config


def _new_services_added(directory: Path) -> None:
    """Brings in what a render of this checkout has and the deployment does not (ADR-098: the
    recogniser): each new service, and each new setting of the Conduit's. Nothing the deployment
    already has is changed, so an operator's own edit stays, and no secret is involved: the
    compose file names its secrets as `${...}`, kept in `deployment.env`, which is not touched."""
    config_path = directory / "osprey.yaml"
    if not config_path.is_file():
        return
    config = load_config(config_path)
    compose_path = directory / "compose.yaml"
    text = compose_path.read_text(encoding="utf-8")
    header_end = text.find("\nname:") + 1
    document = yaml.safe_load(text)
    services = document.setdefault("services", {})
    config = _like_the_deployment(config, services, directory)
    rendered = yaml.safe_load(_render_compose(config, service_images(config)))["services"]
    changed = False
    for name, service in rendered.items():
        if name not in services:
            services[name] = service
            changed = True
    api = services.get("api")
    wanted = rendered.get("api", {}).get("environment", {})
    if isinstance(api, dict) and isinstance(wanted, dict):
        environment = api.setdefault("environment", {})
        for key, value in wanted.items():
            if key not in environment:
                environment[key] = value
                changed = True
    if changed:
        body = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
        compose_path.write_text(text[:header_end] + body, encoding="utf-8")


def _glass_settings_up_to_date(directory: Path) -> None:
    """`/deployment.json` as this checkout renders it (ADR-115 E1 added the deployment's marking).
    It names no secret, so it is written whole; the workspace serves it per visit, so nothing
    restarts."""
    config_path = directory / "osprey.yaml"
    if not config_path.is_file():
        return
    from harness.site import render_glass_settings

    wanted = render_glass_settings(load_config(config_path))
    path = directory / "glass.json"
    if not path.is_file() or path.read_text(encoding="utf-8") != wanted:
        path.write_text(wanted, encoding="utf-8")


def _pins_moved(directory: Path) -> None:
    """A service built from no source here whose rendered image differs from the deployment's is
    moved to it, with the rendered values of its settings (a new version's launch options). Secrets
    are `${...}` references in both, so none is written."""
    config_path = directory / "osprey.yaml"
    if not config_path.is_file():
        return
    config = load_config(config_path)
    compose_path = directory / "compose.yaml"
    text = compose_path.read_text(encoding="utf-8")
    header_end = text.find("\nname:") + 1
    document = yaml.safe_load(text)
    services = document.get("services", {})
    # report-sync runs the Conduit's image with no `build` of its own: rendered in pull mode it
    # looked "moved" to a registry image that does not exist (ADR-111 Amendment 4's refresh).
    config = _like_the_deployment(config, services, directory)
    rendered = yaml.safe_load(_render_compose(config, service_images(config)))["services"]
    moved: dict[str, str] = {}
    for name, wanted in rendered.items():
        service = services.get(name)
        if not isinstance(service, dict) or "build" in wanted or "build" in service:
            continue
        if service.get("image") == wanted.get("image") or "image" not in wanted:
            continue
        service["image"] = wanted["image"]
        environment = service.get("environment")
        wanted_environment = wanted.get("environment")
        if isinstance(environment, dict) and isinstance(wanted_environment, dict):
            environment.update(wanted_environment)
        # A new version's probe comes with it: 26.10.1's image has no `curl` (ADR-101).
        if "healthcheck" in wanted:
            service["healthcheck"] = wanted["healthcheck"]
        moved[name] = str(wanted["image"]).rsplit(":", 1)[1]
    if not moved:
        return
    body = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
    compose_path.write_text(text[:header_end] + body, encoding="utf-8")
    lock_path = directory / "versions.lock"
    if lock_path.is_file():
        lock_text = lock_path.read_text(encoding="utf-8")
        lock_header = "".join(line for line in lock_text.splitlines(True) if line.startswith("#"))
        lock = yaml.safe_load(lock_text) or {}
        for entry in lock.get("images", []):
            if entry.get("service") in moved:
                entry["tag"] = moved[entry["service"]]
        lock_path.write_text(
            lock_header + "\n" + yaml.safe_dump(lock, sort_keys=False), encoding="utf-8"
        )


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
    _new_services_added(directory)
    _pins_moved(directory)
    _glass_settings_up_to_date(directory)
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
    identity = _identity_origin(directory / "deployment.env")
    code = register(
        [
            "--out-root",
            str(directory.parent),
            "--profile",
            directory.name,
            "--keycloak-url",
            identity,
        ]
    )
    if code != 0:
        raise RefreshFailed(
            "The stack is up, but the sign-in accounts could not be registered, so the demo "
            "administrator may not be able to sign in. Run `make register-sign-in` once Keycloak "
            "answers."
        )


def main() -> int:
    # ADR-114 Amendment 4 decision 7: the deployment's names reach its proxy on this machine.
    answer_localhost_with_loopback()
    try:
        refresh()
    except (NothingToRefresh, RefreshFailed) as error:
        print(f"refresh: {error}", file=sys.stderr)
        return 1
    print("refresh: the deployment is up to date with this checkout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
