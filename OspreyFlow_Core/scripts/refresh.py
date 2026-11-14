"""Bring a running deployment up to date with this checkout, in one command.

    PYTHONPATH=.:packages python -m scripts.refresh   # or: ospreyflow start --build

`docker compose up` starts the images that already exist; it never rebuilds one, and it never
rewrites the sign-in theme that Keycloak mounts. So after any change to the code, the Glass, the
Conduit and the sign-in page each stayed as they were until someone knew which command to run for
which. This is that sequence, in order:

1. Write the sign-in theme from the design tokens, noting whether it changed.
2. `docker compose build --pull` the OspreyFlow-owned images, on freshly pulled bases (build order
   step 14). Unchanged layers still come from the cache.
3. `docker compose up -d --wait`, which recreates only the containers whose image changed.
4. If the theme changed, restart Keycloak (it reads a mounted theme at start) and wait for health.
5. Register the sign-in accounts again. Keycloak's database is not persisted, so a restart removes
   the demo administrator while `deployment.env` still names their password; registering is safe to
   repeat and makes the file true again.
6. Where the deployment searches with OpenSearch, rebuild the search index from the graph
   (`harness.search_rebuild`, as install, update and restore do; ADR-150 Amendment 2), so a new
   version's mapping is never left behind an index made for an old one.

A third-party store the checkout pins at a new version (ADR-101: ArcadeDB 26.10.1) is moved to it:
the service takes the rendered image, its probe and the rendered value of each setting the render
names, and
`versions.lock` names the new tag. A setting of the operator's own stays, and a service already at
the checkout's version is not touched, so an operator's edit to it is theirs.

It also brings the deployment's models up to date with its own `osprey.yaml` (ADR-095): the chosen
extraction model's pull line in `compose.yaml`, the proxy's routing table `litellm.yaml`, and the
model lines of `deployment.env`, each exactly as `harness.render` writes them, fetches a newly
chosen model before anything that uses it starts (`harness.model_downloads`), and restarts the
proxy when its table changed. Nothing else in those files is touched, and no secret changes. The
Glass's `/deployment.json` (`glass.json`, no secret in it) is written as the checkout renders it.

Before its `up`, a deployment whose stores' data is not yet in their named volumes has the
volumes added to `compose.yaml` and the data moved there once (`harness.store_volumes`, ADR-114
Amendment 35); the old volumes are kept. A refused move puts every file this wrote back as it was
(Amendment 35 point 7), so the next `start` runs on the old data, never on empty named volumes.

What it never does, on purpose: render the deployment again (that mints new secrets for stores that
keep the old ones), remove a volume, force a container to be recreated, or seed. First-time set-up
is still `python -m harness.apply`. Every compose call reads the deployment's own `--env-file`.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from harness import (
    compose_env,
    ingest_uploads,
    model_downloads,
    register_sign_in,
    search_rebuild,
    store_volumes,
    update,
)
from harness.apply import _compose, release_registry
from harness.atomic import replace_whole
from harness.keycloak_theme import (
    THEME_DIRECTORY,
    THEME_NAME,
    clear_theme_cache,
    login_theme_options,
    read_tokens,
    render_login_theme,
    write_login_theme,
)
from harness.profiles import postgres_connections_up_to_date
from harness.render import (
    STATE_CONTAINER_PATH,
    STORE_VOLUMES,
    _render_compose,
    load_config,
    release_version,
    render_litellm_config,
    render_ollama_download_script,
    render_ollama_pull_script,
    service_images,
)
from harness.site import (
    LOOPBACK,
    answer_localhost_with_loopback,
    answer_the_deployment_in,
    deployment_origins,
)

from schemas.deployment import OspreyConfig, Profile, generated_folder

REPO_ROOT = Path(__file__).resolve().parents[1]


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


#: ADR-138: the folder of a deployment kept under `~/.ospreyflow/deployments/<name>/`, which the
#: `ospreyflow` command names when it runs this (or a seed) for a deployment chosen with `--name`.
DEPLOYMENT_DIR_VARIABLE = "OSPREYFLOW_DEPLOYMENT_DIR"


#: How recent a rollback point marks a deployment as the one an update is moving.
_UPDATE_IN_PROGRESS_SECONDS = 3600
#: The rollback point `harness.update` keeps in the deployment's own folder just before its files
#: step, as v0.4.12 wrote it (964a2a9, `harness/update.py` lines 278-287, called at line 430):
#: `rollback/<version>-<UTC %Y%m%dT%H%M%SZ>/`, holding `.commit`.
_ROLLBACK_POINT = re.compile(r"^.+-(\d{8}T\d{6}Z)$")


def _newest_rollback_point(folder: Path) -> datetime | None:
    points = folder / "rollback"
    stamps = []
    for point in points.iterdir() if points.is_dir() else []:
        made = _ROLLBACK_POINT.match(point.name)
        if made and (point / ".commit").is_file():
            try:
                stamp = datetime.strptime(made.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except ValueError:  # a stamp no clock writes (month 13): not v0.4.12's point
                continue
            stamps.append(stamp)
    return max(stamps, default=None)


def _being_updated(repo_root: Path) -> list[Path]:
    """The rendered deployments, the checkout's own and those kept by name (ADR-138), whose newest
    rollback point was made in the last hour: the one an update from an earlier release is moving,
    whose `update` (v0.4.12's among them) names no deployment to `--files-only` (the rehearsal, 10
    November 2026)."""
    roots = [repo_root / "deploy" / "generated", Path.home() / ".ospreyflow" / "deployments"]
    now = datetime.now(UTC)
    found = []
    for root in roots:
        for compose in sorted(root.glob("[!.]*/compose.yaml")) if root.is_dir() else []:
            newest = _newest_rollback_point(compose.parent)
            age = (now - newest).total_seconds() if newest is not None else -1.0
            if 0 <= age < _UPDATE_IN_PROGRESS_SECONDS:  # a future stamp is no update under way
                found.append(compose.parent)
    return found


def _for_an_update(repo_root: Path) -> None:
    """`--files-only` given no deployment (`OSPREYFLOW_DEPLOYMENT_DIR`): the one being updated, if
    one is; refused, naming them, if several are; otherwise as before."""
    if os.environ.get(DEPLOYMENT_DIR_VARIABLE):
        return
    moving = _being_updated(repo_root)
    if len(moving) == 1:
        os.environ[DEPLOYMENT_DIR_VARIABLE] = str(moving[0])
    elif len(moving) > 1:
        raise RefreshFailed(
            "More than one deployment has an update under way ("
            + ", ".join(str(p) for p in moving)
            + "), so this refresh cannot tell which to bring up to date; nothing was changed. "
            "Check out the version you are moving to, then update one at a time with "
            "`ospreyflow update --name <deployment>`, which names it to this step."
        )


def _deployment_dir(repo_root: Path) -> Path:
    """The rendered deployment a host tool acts on — `start --build`, `update`'s files and every
    seed find it here — with its names answered on this server (ADR-114 Amendment 33 decision 2),
    so each of them reaches a server's own names before the organisation's DNS does."""
    found = _find_deployment_dir(repo_root)
    answer_the_deployment_in(found)
    return found


def _find_deployment_dir(repo_root: Path) -> Path:
    named = os.environ.get(DEPLOYMENT_DIR_VARIABLE)
    if named:
        chosen = Path(named)
        if not (chosen / "compose.yaml").is_file():
            raise NothingToRefresh(
                f"{chosen} holds no rendered deployment (no compose.yaml). Install it first with "
                "`ospreyflow install --name <name>`."
            )
        return chosen
    generated = repo_root / "deploy" / "generated"
    # ADR-132 Amendment 1: the deployment's own folder first, `deployment.name` or the profile, so a
    # product folder holding two rendered deployments rebuilds the one its `osprey.yaml` names.
    preferred = generated / generated_folder(load_config(repo_root / "osprey.yaml"))
    if (preferred / "compose.yaml").is_file():
        return preferred
    # Never a stage a refresh killed outright left behind (`.<name>.refresh-staging`).
    found = sorted(p.parent for p in generated.glob("[!.]*/compose.yaml"))
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
    # ADR-115 decision 6: the page's words depend on whether the deployment can mail a reset link.
    # ADR-132 Amendment 2: and, under the GOV.UK brand, on the deployment's appearance.
    config_path = directory / "osprey.yaml"
    config = load_config(config_path) if config_path.is_file() else OspreyConfig()
    options = login_theme_options(config)
    wanted = render_login_theme(tokens, **options)
    changed = any(
        not (root / name).is_file() or (root / name).read_text(encoding="utf-8") != content
        for name, content in wanted.items()
    )
    if changed:
        write_login_theme(directory, tokens_css=tokens, **options)
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

#: ADR-114 Amendment 7: the steps that fetch model weights exist only with the internal network
#: (the servers that read case content have no route out, so the weights are fetched by these).
#: A deployment rendered before it has neither; only a fresh render brings the layout whole.
_WITH_THE_INTERNAL_NETWORK = ("ollama-models", "whisper-models")


def _on_the_internal_network(document: dict) -> bool:
    return "osprey" in (document.get("networks") or {})


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
    # Before the internal network the server pulls its own weights; with it, `ollama-models` does
    # and then exits (ADR-114 Amendment 7).
    script = render_ollama_pull_script(config)
    if _on_the_internal_network(document):
        puller = document.get("services", {}).get("ollama-models")
        wanted_command = [render_ollama_download_script(config)]
    else:
        puller = document.get("services", {}).get("ollama")
        wanted_command = [script]
    if puller is not None and puller.get("command") != wanted_command:
        puller["command"] = wanted_command
        body = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
        compose_path.write_text(text[:header_end] + body, encoding="utf-8")

    env_path = directory / "deployment.env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    models = config.models
    wanted = [
        f"OSPREY_EXTRACTION_MODEL={config.extraction_model}",
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


def _build_context(services: dict) -> str:
    """The `build.context` the deployment's own Conduit names (`../../..` before ADR-138)."""
    api = services.get("api")
    build = api.get("build") if isinstance(api, dict) else None
    context = build.get("context") if isinstance(build, dict) else None
    return str(context) if context else "../../.."


def _like_the_deployment(config: OspreyConfig, services: dict, directory: Path) -> OspreyConfig:
    """Build or pull as the deployment does. `apply --build` builds the owned images from the
    checkout but leaves the copied `osprey.yaml` without `source_path`, so the mode is read from the
    deployment itself (found on the owner's: the recogniser was added in pull mode, a registry image
    that does not exist)."""
    api = services.get("api")
    if isinstance(api, dict) and "build" in api and config.components.source_path is None:
        # Where the deployment builds from: three levels up for one in a checkout's
        # `deploy/generated/`, the checkout's own path for one kept under `~/.ospreyflow` (ADR-138).
        root = (directory / str(_build_context(services))).resolve()
        return config.model_copy(
            update={"components": config.components.model_copy(update={"source_path": str(root)})}
        )
    return config


#: ADR-135 Amendment 2's gateway secrets, which only `harness.apply` mints.
_GATEWAY_SECRETS = (
    "OSPREY_LITELLM_MASTER_SECRET",
    "OSPREY_LITELLM_SALT_SECRET",
    "OSPREY_LITELLM_DB_PASSWORD",
)


def _named(directory: Path) -> str:
    """` --name <deployment>`: one kept by name (ADR-138), or `default`, the checkout's own, so the
    words never fall to "the only one, or the one last used" on a machine with several."""
    return f" --name {directory.name if directory.parent.name == 'deployments' else 'default'}"


def before_the_gateway_database(directory: Path) -> str:
    """ADR-114 Amendment 39's words, on one line (`update` reports the last line its files step
    prints): the route the v0.5.0 upgrade rehearsal proved, nothing done by refresh itself."""
    n = _named(directory)
    return (
        "This deployment was rendered before the model gateway kept its own database (ADR-135 "
        "Amendment 2), which a refresh cannot bring it to, so nothing was changed. With the "
        "checkout at the version you are moving to (git checkout <its tag>), run "
        f"`ospreyflow backup{n}`, then `ospreyflow apply{n}` (it keeps every value deployment.env "
        "holds, and an install from a release on its own images), then "
        f"`ospreyflow update{n}` and `ospreyflow apply{n}` "
        "once more for an install from a release (the second apply moves the providers' keys into "
        f"the gateway), or `ospreyflow start --build{n}` for one built from a checkout."
    )


def _unset_required(directory: Path) -> list[str]:
    """Each name the compose file requires (`${NAME:?...}`, `${NAME?...}`) that **`deployment.env`**
    holds no value for, read as Compose reads it (`harness.compose_env`): Compose refuses every
    command on such a file. Names only, never a value. **The shell is not asked** (ADR-114 Amendment
    39 decision 2): a file only this shell could interpolate would lock out the next `stop` or
    `apply` from any other (CARRIES row 104 asked otherwise; held for the orchestrator)."""
    return compose_env.unset_required(directory, environ={})


def _predates_the_gateway_database(directory: Path) -> bool:
    """Whether the deployment's gateway is as rendered before ADR-135 Amendment 2: a `litellm`
    service with no `LITELLM_SALT_KEY` (v0.4.12's held a fixed master key and no database)."""
    compose_path = directory / "compose.yaml"
    if not compose_path.is_file():
        return False
    document = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    gateway = (document.get("services") or {}).get("litellm")
    if not isinstance(gateway, dict):
        return False
    environment = gateway.get("environment") or {}
    if isinstance(environment, list):
        names = {str(item).partition("=")[0] for item in environment}
    else:
        names = set(environment)
    return "LITELLM_SALT_KEY" not in names


def _named_volumes_declared(document: dict[str, Any], rendered: dict[str, Any]) -> bool:
    """Every named volume a service mounts declared at the top level, as the render declares it: a
    mount `_new_services_added` gives the Conduit (`map-settings`, `model-settings`) names one a
    deployment rendered before it lacks, and Compose refuses the whole project (the v0.5.0 upgrade
    rehearsal). Says whether anything was added."""
    declared = dict(document.get("volumes") or {})
    wanted = rendered.get("volumes") or {}
    added = False
    for service in (document.get("services") or {}).values():
        mounts = (service.get("volumes") or []) if isinstance(service, dict) else []
        for volume in mounts:
            if isinstance(volume, dict):  # the long syntax: only a named volume's source
                source = str(volume.get("source") or "") if volume.get("type") == "volume" else ""
            else:
                source = str(volume).split(":", 1)[0] if ":" in str(volume) else ""
            if not source or source.startswith((".", "/", "~", "$")) or source in declared:
                continue
            declared[source] = wanted.get(source) or {"driver": "local"}
            added = True
    if added:
        document["volumes"] = declared
    return added


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
    rendered_document = yaml.safe_load(
        _render_compose(config, service_images(config, build_context=_build_context(services)))
    )
    rendered = rendered_document["services"]
    changed = False
    layout = _on_the_internal_network(document)
    left_out = []
    for name, service in rendered.items():
        if name in services:
            continue
        if not layout:
            if name in _WITH_THE_INTERNAL_NETWORK:
                left_out.append(name)
                continue
            # On the default network, like every other service of this deployment.
            service.pop("networks", None)
        services[name] = service
        changed = True
    if left_out:
        print(
            f"refresh: not added: {', '.join(left_out)}. They come with the internal network "
            "(ADR-114 Amendment 7), which only a fresh render of the deployment brings."
        )
    api = services.get("api")
    # A mount the render gives the Conduit at a place nothing is mounted yet (Amendment 8: the
    # `state/` folder). A place already mounted keeps the deployment's own source, which may be an
    # operator's edit (the ingest folder).
    if isinstance(api, dict):
        mounted = {str(v).split(":")[1] for v in api.get("volumes") or [] if ":" in str(v)}
        for volume in rendered.get("api", {}).get("volumes") or []:
            if ":" in str(volume) and str(volume).split(":")[1] not in mounted:
                api.setdefault("volumes", []).append(volume)
                changed = True
    wanted = rendered.get("api", {}).get("environment", {})
    if isinstance(api, dict) and isinstance(wanted, dict):
        environment = api.setdefault("environment", {})
        for key, value in wanted.items():
            if key not in environment:
                environment[key] = value
                changed = True
    if _named_volumes_declared(document, rendered_document):
        changed = True
    if changed:
        body = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
        compose_path.write_text(text[:header_end] + body, encoding="utf-8")


def _release_up_to_date(directory: Path) -> None:
    """The Conduit's version, its post-ingest resolution switch (ADR-127 Amendment 35) and the
    notice folder (ADR-114 Amendment 8), exactly as `render` writes them (the same
    `release_version`, so a refresh never disagrees with a render): each line
    replaced where it stands, or added after `OSPREY_PROFILE=` as render places it, nothing else in
    `deployment.env` touched; and `state/` made here so that Docker does not make it (as root, where
    a check could not write)."""
    (directory / "state").mkdir(exist_ok=True)
    config_path = directory / "osprey.yaml"
    if not config_path.is_file():
        return
    services = (yaml.safe_load((directory / "compose.yaml").read_text(encoding="utf-8")) or {}).get(
        "services", {}
    )
    config = _like_the_deployment(load_config(config_path), services, directory)
    wanted = {
        "OSPREY_RELEASE_VERSION": release_version(config),
        "OSPREY_STATE_DIR": STATE_CONTAINER_PATH,
        # ADR-127 Amendment 35: the switch Amendment 33 added, which a deployment rendered before
        # it never had, so its Conduit took the default whatever its `osprey.yaml` said.
        "OSPREY_POST_INGEST_RESOLUTION": "on"
        if config.components.post_ingest_resolution
        else "off",
    }
    env_path = directory / "deployment.env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = [
        f"{k}={wanted[k]}" if (k := line.split("=", 1)[0]) in wanted else line for line in lines
    ]
    missing = [
        f"{k}={v}" for k, v in wanted.items() if not any(x.startswith(f"{k}=") for x in lines)
    ]
    at = next(
        (i + 1 for i, line in enumerate(updated) if line.startswith("OSPREY_PROFILE=")),
        len(updated),
    )
    updated[at:at] = missing
    if updated != lines:
        env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


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


def _routing_up_to_date(directory: Path) -> bool:
    """The front proxy's routing table as this checkout renders it; True when it changed, since the
    proxy reads it at start (ADR-132 Amendment 2: under GOV.UK the `id.` name routes
    `/assets/govuk/` to the Glass). It names no secret, so it is written whole."""
    config_path = directory / "osprey.yaml"
    if not config_path.is_file():
        return False
    from harness.render import _BANNER, _comment_block
    from harness.site import render_caddyfile

    wanted = _comment_block(_BANNER, "#") + render_caddyfile(load_config(config_path))
    path = directory / "Caddyfile"
    if path.is_file() and path.read_text(encoding="utf-8") == wanted:
        return False
    path.write_text(wanted, encoding="utf-8")
    return True


def _bare(port: object) -> bool:
    """A short-form published port with no host address (`80:8080`,
    `${OSPREY_API_PORT:-8000}:8000`): the part before the first colon is an address only when it
    has a dot or a bracket."""
    if not isinstance(port, str) or ":" not in port:
        return False
    host = port.split(":", 1)[0]
    return "." not in host and not host.startswith("[")


def _published_on_loopback(directory: Path) -> None:
    """S10 (`05_DEPLOYMENT.md` §7): every port a Lite deployment publishes is bound to `127.0.0.1`.
    A deployment rendered before it publishes its proxy as a bare `HOST:CONTAINER`, on every
    interface, and nothing else here rewrites a service the deployment already has (found at the
    step 11 rehearsal, 2 November 2026: both of the owner's deployments still answered on every
    interface after `start --build`). Only the host address is added; the operator's own port
    numbers stay, and `up` recreates the service because its ports changed."""
    config_path = directory / "osprey.yaml"
    if not config_path.is_file() or load_config(config_path).profile is not Profile.LOCAL_LITE:
        return
    compose_path = directory / "compose.yaml"
    text = compose_path.read_text(encoding="utf-8")
    header_end = text.find("\nname:") + 1
    document = yaml.safe_load(text)
    changed = False
    for service in (document.get("services") or {}).values():
        ports = service.get("ports") if isinstance(service, dict) else None
        if not ports:
            continue
        bound = [f"{LOOPBACK}:{port}" if _bare(port) else port for port in ports]
        if bound != ports:
            service["ports"] = bound
            changed = True
    if changed:
        body = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
        compose_path.write_text(text[:header_end] + body, encoding="utf-8")


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
    rendered = yaml.safe_load(
        _render_compose(config, service_images(config, build_context=_build_context(services)))
    )["services"]
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


def _stores_named(directory: Path) -> bool:
    """ADR-114 Amendment 35: each store the deployment runs given its named volume, as the render
    gives it, with the top-level declaration. A path the store already mounts from somewhere is
    left as it is (an operator's own edit). The data is moved by `harness.store_volumes` before the
    next `up`, never here. Says whether anything changed."""
    compose_path = directory / "compose.yaml"
    text = compose_path.read_text(encoding="utf-8")
    header_end = text.find("\nname:") + 1
    document = yaml.safe_load(text) or {}
    services = document.get("services") or {}
    declared = document.get("volumes") or {}
    changed = False
    for row in STORE_VOLUMES:
        service = services.get(row.service)
        if not isinstance(service, dict):
            continue
        mounted = {
            str(v).split(":")[1] for v in service.get("volumes") or [] if str(v).count(":") >= 1
        }
        if row.path in mounted:
            continue
        service["volumes"] = [*(service.get("volumes") or []), f"{row.volume}:{row.path}"]
        declared[row.volume] = {"driver": "local"}
        changed = True
    if changed:
        document["volumes"] = declared
        body = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
        compose_path.write_text(text[:header_end] + body, encoding="utf-8")
    return changed


def _postgres_connections_named(directory: Path) -> bool:
    """ADR-114 Amendment 43: PostgreSQL's `max_connections` and Keycloak's pool, as the render
    gives them (`harness.profiles.postgres_connections_up_to_date`), on a deployment rendered
    before them. Says whether anything changed."""
    compose_path = directory / "compose.yaml"
    text = compose_path.read_text(encoding="utf-8")
    header_end = text.find("\nname:") + 1
    document = yaml.safe_load(text) or {}
    if not postgres_connections_up_to_date(document.get("services") or {}):
        return False
    body = yaml.safe_dump(document, sort_keys=False, default_flow_style=False)
    compose_path.write_text(text[:header_end] + body, encoding="utf-8")
    return True


def files_up_to_date(repo_root: Path = REPO_ROOT) -> dict[str, bool]:
    """Every file of the deployment as this checkout writes it, and nothing run: `update` uses this
    from the new checkout (ADR-114 Amendment 8 point 6a). Says which services must restart."""
    directory = _deployment_dir(repo_root)
    with _release_registry(directory):
        return _files_up_to_date(directory, repo_root)


@contextlib.contextmanager
def _release_registry(directory: Path) -> Iterator[None]:
    """A deployment installed from a release runs the release's own images, which live where its
    lock says (`ghcr.io/<owner>`), not in the built-in registry: render as `apply` does for one, or
    every owned image looks moved to an address the registry refuses (step 20 unit 10, 4 November:
    each update of a release install rolled back at its pull)."""
    lock = directory / "versions.lock"
    compose = directory / "compose.yaml"
    services = (
        (yaml.safe_load(compose.read_text(encoding="utf-8")) or {}).get("services") or {}
        if compose.is_file()
        else {}
    )
    api = services.get("api") if isinstance(services, dict) else None
    from_a_release = (
        lock.is_file() and isinstance(api, dict) and "build" not in api
        and "@sha256:" in str(api.get("image", ""))
    )  # fmt: skip
    if not from_a_release:
        yield
        return
    before = os.environ.get("OSPREY_IMAGE_REGISTRY")
    os.environ["OSPREY_IMAGE_REGISTRY"] = release_registry(lock.read_text(encoding="utf-8"))
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("OSPREY_IMAGE_REGISTRY", None)
        else:
            os.environ["OSPREY_IMAGE_REGISTRY"] = before


#: What the files pass writes: these top-level files, the sign-in theme and `state/`. Staged
#: copies of these alone (a folder from before ADR-114 Amendment 35 may hold store data).
_STAGED_FOLDERS = (THEME_DIRECTORY,)


def _files_up_to_date(directory: Path, repo_root: Path) -> dict[str, bool]:
    """ADR-114 Amendment 39: the files pass runs on a staged copy beside the deployment, and only a
    result Compose can interpolate is moved into place; a refusal changes nothing in the folder."""
    if _predates_the_gateway_database(directory):
        raise RefreshFailed(before_the_gateway_database(directory))
    with one_refresh(directory):
        return _files_up_to_date_staged(directory, repo_root)


@contextlib.contextmanager
def one_refresh(directory: Path) -> Iterator[None]:
    """One refresh or update of a deployment at a time, for the whole of it (`harness.update`'s
    `one_change`, which `update` holds too and hands to its `--files-only` child); refused in words
    as a `RefreshFailed`."""
    try:
        with update.one_change(directory):
            yield
    except update.ChangeUnderWay as refused:
        raise RefreshFailed(str(refused)) from None


#: The restarts a files pass found needed, kept in the deployment's `state/` from before its files
#: move until `start --build` has done them, so a run that dies in between loses none.
PENDING_RESTARTS = update.PENDING_RESTARTS


def _pending(directory: Path) -> dict[str, bool]:
    path = directory / "state" / PENDING_RESTARTS
    try:
        return {str(k): bool(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def _keep_pending(directory: Path, owed: dict[str, bool]) -> None:
    """The restarts still owed, whole or not at all; none owed, no record."""
    path = directory / "state" / PENDING_RESTARTS
    if any(owed.values()):
        replace_whole(path, json.dumps(owed, sort_keys=True).encode(), mode=0o644)
    else:
        path.unlink(missing_ok=True)


def _files_up_to_date_staged(directory: Path, repo_root: Path) -> dict[str, bool]:
    stage = directory.parent / f".{directory.name}.refresh-staging"
    shutil.rmtree(stage, ignore_errors=True)
    if stage.exists():
        # Left by a run killed under another account (sudo), whose files this one cannot remove.
        raise RefreshFailed(
            f"A refresh left {stage} behind under another account (a run under sudo), and this "
            "one cannot remove it, so nothing was changed. Remove it as that account (sudo rm -rf "
            f"{stage}), then run this again."
        )
    stage.mkdir(mode=0o700)  # private before anything is copied in: it holds deployment.env
    stage.chmod(0o700)  # whatever the umask took off
    try:
        for path in directory.iterdir():
            if path.is_file():  # a symlinked file by what it holds, written back through its link
                shutil.copy2(path, stage / path.name)
            elif path.name in _STAGED_FOLDERS and path.is_dir():
                shutil.copytree(path, stage / path.name, symlinks=True)
        changed = _files_up_to_date_in(stage, repo_root)
        missing = _unset_required(stage)
        if missing:
            gateway = any(name in _GATEWAY_SECRETS for name in missing)
            raise RefreshFailed(
                before_the_gateway_database(directory)
                if gateway
                else "This checkout's compose file requires "
                + ", ".join(missing)
                + ", which deployment.env does not hold, so nothing was changed. Run `ospreyflow "
                + f"apply{_named(directory)}` with the checkout at the version you are moving to."
            )
        # Into place: each changed file renamed over its old one (the stage is beside the
        # deployment, so on its file system, and a rename is all or nothing), `deployment.env` last,
        # so an interruption leaves whole files, old or new, and the secrets as they were.
        # A file a service mounts on its own (`./glass.json:…`) is written in place instead: a
        # rename gives it a new inode, and the running container would keep the old one (the
        # workspace serves `glass.json` per visit, and nothing restarts it). None holds a secret.
        mounted = _mounted_files(stage)
        # What must restart, kept before anything moves (with what an earlier run left undone).
        earlier = _pending(directory)
        changed = {k: bool(v) or earlier.get(k, False) for k, v in changed.items()}
        try:
            (directory / "state").mkdir(exist_ok=True)
            _keep_pending(directory, changed)
        except PermissionError:
            state = directory / "state"
            raise RefreshFailed(
                f"This account cannot write {state} (a run under sudo can leave it root's), so "
                "nothing was changed. Give the folder back to this account, then run this again."
            ) from None
        files = sorted(
            (p for p in stage.iterdir() if p.is_file()), key=lambda p: p.name == "deployment.env"
        )
        for path in files:
            target = directory / path.name
            if target.is_file() and target.read_bytes() == path.read_bytes():
                continue
            if path.name in mounted and target.is_file():
                # A container mounts it on its own and must keep seeing this inode; never a secret.
                with target.open("r+b") as handle:
                    handle.write(path.read_bytes())
                    handle.truncate()
            else:
                # Whole or not at all, through a link to its target, the old file's owner kept
                # under sudo, the folder flushed (`harness.atomic`, as every writer of
                # deployment.env).
                mode = 0o600 if path.name == "deployment.env" else path.stat().st_mode & 0o7777
                replace_whole(target, path.read_bytes(), mode=mode)
        for path in stage.iterdir():
            if path.is_dir() and path.name in _STAGED_FOLDERS:
                shutil.copytree(path, directory / path.name, symlinks=True, dirs_exist_ok=True)
            elif path.is_dir():
                (directory / path.name).mkdir(exist_ok=True)
        return changed
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _mounted_files(directory: Path) -> set[str]:
    """The top-level files of `directory` a service of its compose file mounts on their own."""
    document = yaml.safe_load((directory / "compose.yaml").read_text(encoding="utf-8")) or {}
    names = set()
    for service in (document.get("services") or {}).values():
        for volume in (service.get("volumes") or []) if isinstance(service, dict) else []:
            source = volume.get("source") if isinstance(volume, dict) else str(volume).split(":")[0]
            if isinstance(source, str) and source.startswith("./") and "/" not in source[2:]:
                names.add(source[2:])
    return names


def _files_up_to_date_in(directory: Path, repo_root: Path) -> dict[str, bool]:
    theme_changed = _theme_changed(directory, repo_root)
    proxy_changed = _models_up_to_date(directory)
    _new_services_added(directory)
    _pins_moved(directory)
    _published_on_loopback(directory)
    _glass_settings_up_to_date(directory)
    routing_changed = _routing_up_to_date(directory)
    _release_up_to_date(directory)
    _stores_named(directory)
    _postgres_connections_named(directory)
    return {
        "proxy_changed": proxy_changed,
        "theme_changed": theme_changed,
        "routing_changed": routing_changed,
    }


def _uploads_ready(compose_file: Path, run: Callable[[Sequence[str]], None]) -> None:
    """The Ingest Studio's upload folder the Conduit's to write, before `up` (ADR-114 Amendment 33,
    "as found on the first server"; `harness.ingest_uploads`)."""

    def run_it(argv: Sequence[str]) -> tuple[int, str]:
        try:
            run(argv)
        except RefreshFailed as failed:
            return 1, str(failed)
        return 0, ""

    try:
        ingest_uploads.prepare(compose_file, run=run_it)
    except ingest_uploads.UploadFolderRefused as refused:
        raise RefreshFailed(str(refused)) from refused


def refresh(
    repo_root: Path = REPO_ROOT,
    *,
    run: Callable[[Sequence[str]], None] = _run,
    register: Callable[[list[str]], int] = _register,
    docker: store_volumes.Run | None = None,
) -> None:
    directory = _deployment_dir(repo_root)
    with one_refresh(directory):
        _refresh(directory, repo_root, run=run, register=register, docker=docker)


def _refresh(
    directory: Path,
    repo_root: Path,
    *,
    run: Callable[[Sequence[str]], None],
    register: Callable[[list[str]], int],
    docker: store_volumes.Run | None,
) -> None:
    compose = _compose(directory / "compose.yaml")
    pulls_before = model_downloads.commands(directory / "compose.yaml")
    held = store_volumes.FilesHeld(directory)
    owed_before = _pending(directory)  # what an earlier run that died still owes
    changed = files_up_to_date(repo_root)
    theme_changed, proxy_changed = changed["theme_changed"], changed["proxy_changed"]
    run([*compose, "build", "--pull"])
    _uploads_ready(directory / "compose.yaml", run)
    # ADR-114 Amendment 35: a store's data moved into its named volume, once, before anything
    # starts on it. `docker` is Docker itself unless a test stands one in.
    try:
        store_volumes.move(directory / "compose.yaml", run=docker or store_volumes._subprocess)
    except store_volumes.StoresNotMoved as failed:
        held.put_back()
        # The files are as they were after the earlier run, so what that run owed is owed still,
        # and nothing of this one's.
        _keep_pending(directory, owed_before)
        raise RefreshFailed(failed.words(files_put_back=True)) from failed
    # Defect 9 (ADR-114 Amendment 33): `up` alone would start `ollama-models` again for its changed
    # command, but start the gateway and the Conduit on the new model beside it, before it is there.
    steps = model_downloads.steps_to_fetch(pulls_before, directory / "compose.yaml")
    try:
        for argv in model_downloads.fetch_argvs(compose, steps, force=False):
            run(argv)
    except RefreshFailed as failed:
        raise RefreshFailed(f"{model_downloads.failed_words(steps)} ({failed})") from failed
    run([*compose, "up", "-d", "--wait"])
    if proxy_changed:
        # The proxy reads its routing table at start; `up` recreates the Ollama and API
        # containers itself, since their command and environment file changed.
        run([*compose, "restart", "litellm"])
        run([*compose, "up", "-d", "--wait"])
    if changed["routing_changed"]:
        run([*compose, "restart", "proxy"])
    if theme_changed:
        run(clear_theme_cache(compose))
        run([*compose, "restart", "keycloak"])
        run([*compose, "up", "-d", "--wait"])
    # Every restart the files called for is done (ADR-114 Amendment 39's pending record).
    (directory / "state" / PENDING_RESTARTS).unlink(missing_ok=True)
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
            "administrator may not be able to sign in. Run `ospreyflow repair-sign-in` once "
            "Keycloak answers."
        )
    _search_index_rebuilt(directory / "compose.yaml", compose, run)


def _search_index_rebuilt(
    compose_file: Path, compose: Sequence[str], run: Callable[[Sequence[str]], None]
) -> None:
    """The search index made again from the graph where the deployment searches with OpenSearch,
    as install, update and restore do (the CARRIES row "an upgrade must rebuild when the mapping
    changes"; ADR-150 decision 4 and Amendment 2). Last, so every `up` and restart is done and the
    Conduit healthy: a deployment brought to a new version from its checkout otherwise keeps an
    index made for another mapping, the indexer writes nothing to it and search stays on the
    exact-identifier fallback (found on osprey-small, 14 November 2026)."""
    if not search_rebuild.renders_opensearch(compose_file):
        return
    try:
        run(search_rebuild.rebuild_argv(compose))
    except RefreshFailed as failed:
        raise RefreshFailed(
            f"The stack is up and the sign-in accounts registered, but the search index could not "
            f"be rebuilt from the graph ({failed}), so search answers only exact identifiers until "
            f"it is. Run `ospreyflow start --build` again once the Conduit and OpenSearch answer."
        ) from failed


def main(argv: Sequence[str] | None = None, *, repo_root: Path = REPO_ROOT) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--files-only"]:
        try:
            _for_an_update(repo_root)
            changed = files_up_to_date(repo_root)
            # Handed to `update`, which restarts what it names. The record stays until a restart
            # is known done: an `update` killed before its restarts leaves them owed to the next
            # `start --build`, which at worst restarts a service once more than needed.
        except (NothingToRefresh, RefreshFailed) as error:
            print(f"refresh: {error}", file=sys.stderr)
            return 1
        print(json.dumps(changed, sort_keys=True))
        return 0
    # ADR-114 Amendment 4 decision 7: the deployment's names reach its proxy on this machine;
    # Amendment 33 decision 2: and a server's own names, on this server.
    answer_localhost_with_loopback()
    try:
        _deployment_dir(repo_root)
        refresh(repo_root)
    except (NothingToRefresh, RefreshFailed) as error:
        print(f"refresh: {error}", file=sys.stderr)
        return 1
    print("refresh: the deployment is up to date with this checkout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
