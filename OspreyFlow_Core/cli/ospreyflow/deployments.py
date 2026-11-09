"""Several deployments side by side (`06_DECISIONS.md` ADR-138 decision 2).

A deployment installed with `ospreyflow install --name <name>` lives in a folder of its own,
`~/.ospreyflow/deployments/<name>/`: its `osprey.yaml`, every file the harness renders from it and
its `deployment.env` (mode 600). Its Compose project and volumes are named `<name>`, and it answers
at an address of its own (`--address`, default `http://<name>.localhost:<next free port>`). The
checkout is shared; no worktree is needed.

**The checkout-rooted deployment is `default`.** One installed before this ADR — its `osprey.yaml`
in the checkout, rendered under `deploy/generated/` — keeps working exactly as it did, and is
listed and chosen as `default`. Nothing here moves, renames or rewrites it.

**Which deployment a verb acts on** (`resolve`): the one `--name` names; else the one last used
(the name `current` records, written by `install --name`, `switch` and any verb given `--name`);
else, when no deployment has been installed by name, `default` — so a machine with none behaves as
before.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from .home import LITE_ORIGIN, CommandRefused, deployment_dir, public_origin, read_config

#: The name the checkout-rooted deployment is listed and chosen by.
DEFAULT = "default"
#: What Compose takes as a project name (`schemas.deployment._COMPOSE_NAME`, held equal by a test).
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
#: The first port a new deployment's address is offered from, and its graph store's.
FIRST_ADDRESS_PORT = 8090
FIRST_GRAPH_PORT = 2500
#: Ports never offered to a new deployment: the checkout-rooted deployments' own (the front proxy on
#: 80, a second at 8081, the ArcadeDB door at 2480) and the stores' and the workspace's defaults.
RESERVED_PORTS = frozenset({80, 443, 2480, 5432, 8000, 8080, 8081})
#: The first line of an `osprey.yaml` a starter made (ADR-138 decision 1): a comment, not a setting.
STARTER_COMMENT = re.compile(r"^#\s*Starter:\s*(?P<name>[a-z]+-[a-z]+)\b")


@dataclass(frozen=True)
class Target:
    """One deployment: its name (`default` for the checkout's), where its `osprey.yaml` is and where
    it is rendered."""

    name: str
    config_path: Path
    rendered: Path

    @property
    def named(self) -> bool:
        return self.name != DEFAULT

    @property
    def folder(self) -> Path:
        """The folder holding its `osprey.yaml`: the checkout for `default`."""
        return self.config_path.parent

    def origin(self) -> str:
        return address_of(self.config_path)


def deployments_root(env: Mapping[str, str]) -> Path:
    """`~/.ospreyflow/deployments`, under the home folder `HOME` names (the tests' own home)."""
    home = env.get("HOME") or env.get("USERPROFILE")
    return (Path(home) if home else Path.home()) / ".ospreyflow" / "deployments"


def _current_file(env: Mapping[str, str]) -> Path:
    return deployments_root(env).parent / "current"


def named(env: Mapping[str, str]) -> list[str]:
    """The deployments installed by name, sorted: each folder under the root holding an
    `osprey.yaml`. A staging folder (`.<name>.staging`, the harness's own) is never one."""
    root = deployments_root(env)
    if not root.is_dir():
        return []
    return sorted(
        folder.name
        for folder in root.iterdir()
        if folder.is_dir()
        and not folder.name.startswith(".")
        and (folder / "osprey.yaml").is_file()
    )


def default_target(product: Path) -> Target:
    return Target(DEFAULT, product / "osprey.yaml", deployment_dir(product))


def named_target(env: Mapping[str, str], name: str) -> Target:
    folder = deployments_root(env) / name
    return Target(name, folder / "osprey.yaml", folder)


def read_current(env: Mapping[str, str]) -> str | None:
    try:
        text = _current_file(env).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def remember(env: Mapping[str, str], name: str) -> None:
    """Record `name` as the deployment last used. Only once some deployment has been installed by
    name: a machine with none is never written to."""
    if not named(env) and name == DEFAULT:
        return
    path = _current_file(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name + "\n", encoding="utf-8")


#: `schemas.deployment.Profile`'s values (held to them by a test, as this command runs before the
#: product's Python): the checkout's own deployment's name, and so its backups subfolder.
PROFILE_NAMES = ("local-lite", "small", "cluster")


def check_name(name: str) -> None:
    if name == DEFAULT:
        raise CommandRefused(
            "'default' is the name of the deployment in the checkout itself; give the new one a "
            "name of its own."
        )
    if not _NAME.match(name) or len(name) > 40:
        raise CommandRefused(
            f"'{name}' cannot name a deployment: use lowercase letters, digits and hyphens, "
            "starting with a letter or digit, at most 40 characters."
        )


def resolve(
    name: str | None, product: Path, env: Mapping[str, str], *, creating: bool = False
) -> Target:
    """The deployment a verb acts on (the module's docstring says the order)."""
    installed = named(env)
    if name is None:
        if not installed:
            return default_target(product)
        last = read_current(env)
        if last in installed:
            return named_target(env, last)
        checkout = default_target(product)
        only_one = len(installed) == 1 and not (checkout.rendered / "compose.yaml").is_file()
        if last is None and only_one:
            return named_target(env, installed[0])  # the only deployment there is
        return checkout
    if name == DEFAULT:
        return default_target(product)
    check_name(name)
    if creating and name in PROFILE_NAMES and name not in installed:
        # ADR-114 Amendment 38: a deployment's backups are in `<backups folder>/<its name>/`, and
        # the checkout's own deployment is named by its profile, so the two would share sets. One
        # installed by such a name before it is still reached by it.
        raise CommandRefused(
            f"'{name}' is the name of a profile, which the checkout's own deployment goes by (its "
            "backups are kept under that name); give the new one a name of its own."
        )
    if creating and name not in installed and (product / "osprey.yaml").is_file():
        own = read_config(product)
        section = own.get("deployment")
        given = section.get("name") if isinstance(section, dict) else None
        checkouts = given or own.get("profile")
        if checkouts == name:
            # Amendment 38 decision 6: the checkout's own deployment goes by `deployment.name`
            # when it gives one (ADR-132 Amendment 1), and its backups by that name.
            raise CommandRefused(
                f"'{name}' is the checkout's own deployment's name (deployment.name in "
                f"{product / 'osprey.yaml'}), under which its backups are kept; give the new one "
                "a name of its own."
            )
    if name not in installed and not creating:
        known = ", ".join([DEFAULT, *installed])
        raise CommandRefused(
            f"There is no deployment called '{name}'. The deployments on this machine are: "
            f"{known}. Install one with ospreyflow install --mode lite --name {name}."
        )
    return named_target(env, name)


def address_of(config_path: Path) -> str:
    """`network.public_origin` of the `osprey.yaml` at `config_path`, else the Lite default."""
    if config_path.name == "osprey.yaml" and config_path.parent.is_dir():
        try:
            return public_origin(config_path.parent)
        except (OSError, yaml.YAMLError, CommandRefused):
            return LITE_ORIGIN
    return LITE_ORIGIN


def starter_of(config_path: Path) -> str | None:
    """The starter an `osprey.yaml` records in its first comment lines, if it was made from one."""
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()[:5]
    except OSError:
        return None
    for line in lines:
        found = STARTER_COMMENT.match(line)
        if found:
            return found["name"]
    return None


def _port_of(origin: str) -> int:
    parts = urlsplit(origin)
    return parts.port or (443 if parts.scheme == "https" else 80)


def ports_in_use(product: Path, env: Mapping[str, str]) -> set[int]:
    """Every port a deployment this command knows of is given: each one's address port and graph
    store port, and the checkout's own."""
    taken: set[int] = set()
    targets = [default_target(product), *(named_target(env, n) for n in named(env))]
    for target in targets:
        if not target.config_path.is_file():
            continue
        taken.add(_port_of(target.origin()))
        try:
            deployment = read_config(target.folder).get("deployment")
        except (OSError, yaml.YAMLError, CommandRefused):
            continue
        if isinstance(deployment, dict) and isinstance(deployment.get("graph_port"), int):
            taken.add(int(deployment["graph_port"]))
        else:
            taken.add(2480)
    return taken


def next_free_port(start: int, taken: Iterable[int], port_free: Callable[[int], bool]) -> int:
    """The first port from `start` that no deployment is given, that is not reserved, and that
    nothing on this machine is listening on."""
    avoid = set(taken) | RESERVED_PORTS
    for port in range(start, 65535):
        if port not in avoid and port_free(port):
            return port
    raise CommandRefused("No free port was found on this machine for the new deployment.")


def default_address(name: str, port: int) -> str:
    return f"http://{name}.localhost:{port}"


def check_address(address: str) -> None:
    parts = urlsplit(address)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.path not in ("", "/"):
        raise CommandRefused(
            f"--address {address!r} is an origin such as http://{{name}}.localhost:8090: a scheme, "
            "a host name and, if it is not 80, a port; no path."
        )


def compose_projects(listing: list[dict[str, object]]) -> dict[str, list[Path]]:
    """`docker compose ls --all`'s rows as `project -> the compose files it was started from`."""
    projects: dict[str, list[Path]] = {}
    for row in listing:
        files = [Path(f.strip()) for f in str(row.get("ConfigFiles", "")).split(",") if f.strip()]
        projects[str(row.get("Name", ""))] = files
    return projects


def refuse_a_taken_project(name: str, folder: Path, projects: Mapping[str, list[Path]]) -> None:
    """Compose names a project's containers and volumes after it. A second deployment given a name
    another project already has would take that project's containers over (Compose recreates them
    from its own file), so a name in use by any other folder is refused before anything is
    written."""
    own = (folder / "compose.yaml").resolve()
    files = projects.get(name)
    if files and all(f.resolve() != own for f in files):
        raise CommandRefused(
            f"Docker already has a Compose project called '{name}' (started from "
            f"{', '.join(str(f) for f in files)}). Give this deployment another name: two "
            "deployments with one name would share containers and volumes."
        )


def private_folder(folder: Path) -> None:
    """The deployment's folder, readable by its owner alone: it holds `deployment.env`."""
    folder.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        folder.chmod(0o700)
