"""What Docker Compose refuses to interpolate in a deployment's compose file, read before Compose
is asked (CARRIES, the v0.5.0 upgrade rehearsal, 10 November 2026: a compose file naming a value
`deployment.env` did not hold locked the operator out of `apply` and `stop`, in Compose's words or
none).

Compose refuses `${NAME:?…}` when NAME is unset or empty, and `${NAME?…}` when it is unset; it takes
a value from the shell before the env file, and reads `export NAME=v` there. `${NAME}`,
`${NAME:-default}` and the escaped `$${NAME:?…}` it never refuses. `cli/ospreyflow/run.py` keeps a
copy for `ospreyflow stop`, which cannot import the harness; `tests/harness/test_compose_lockout.py`
holds them to the same answers.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

import yaml

_REQUIRED = re.compile(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)(:?)\?")


def unset_required(directory: Path, environ: Mapping[str, str] | None = None) -> list[str]:
    """Each name `directory`'s compose file requires that Compose would find without a value, by
    `deployment.env` and `environ` (the process's own by default). Names only, never a value."""
    shell = os.environ if environ is None else environ
    compose = (directory / "compose.yaml").read_text(encoding="utf-8")
    held: dict[str, str] = {}
    env_path = directory / "deployment.env"
    for line in env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []:
        name, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and not name.startswith("#"):
            held[name.strip()] = value.strip().strip("\"'")
    missing = set()
    for name, colon in _REQUIRED.findall(compose):
        found = shell[name] if name in shell else held.get(name)
        if found is None or (colon and found == ""):
            missing.add(name)
    return sorted(missing)


def project(directory: Path) -> str:
    """The compose project's name (`name:`), or the folder's, as Compose takes it."""
    loaded = yaml.safe_load((directory / "compose.yaml").read_text(encoding="utf-8")) or {}
    return str(loaded.get("name") or directory.name)


def locked_out(directory: Path, missing: list[str]) -> str:
    """The words for a compose file Compose cannot read: what is missing, where to find it, and how
    to stop the containers meanwhile, which needs no compose file."""
    return (
        f"The compose file needs {', '.join(missing)}, which deployment.env does not hold, so "
        "Docker Compose refuses every command on this deployment and nothing was changed. Put each "
        "back in deployment.env from the deployment's last backup set (its config/deployment.env), "
        "then run this again. To stop its containers meanwhile: docker stop $(docker ps -q "
        f"--filter label=com.docker.compose.project={project(directory)})"
    )
