"""What Docker Compose refuses to interpolate in a deployment's compose file, read before Compose
is asked (CARRIES, the v0.5.0 upgrade rehearsal, 10 November 2026: a compose file naming a value
`deployment.env` did not hold locked the operator out of `apply` and `stop`, in Compose's words or
none).

Compose refuses `${NAME:?…}` when NAME is unset or empty, and `${NAME?…}` when it is unset; it
takes a value from the shell before the env file (an empty one too), and reads `export NAME=v`, one
pair of quotes and an unquoted ` #` comment there as `harness.preflight.ports.read_env_file` does.
`${NAME}`, `${NAME:-default}` and the escaped `$${NAME:?…}` it never refuses.
`cli/ospreyflow/run.py` keeps a copy for the command's verbs, which cannot import the harness;
`tests/harness/test_compose_lockout.py` holds them to the same answers.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

import yaml

from harness.preflight.ports import read_env_file

_REQUIRED = re.compile(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)(:?)\?")


def unset_required(directory: Path, environ: Mapping[str, str] | None = None) -> list[str]:
    """Each name `directory`'s compose file requires that Compose would find without a value, by
    `deployment.env` and `environ` (the process's own by default). Names only, never a value."""
    shell = os.environ if environ is None else environ
    compose = (directory / "compose.yaml").read_text(encoding="utf-8")
    env_path = directory / "deployment.env"
    # As Compose reads it: one pair of matching quotes taken whole, an unquoted ` #` comment off.
    held = read_env_file(env_path) if env_path.is_file() else {}
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


def locked_out(
    directory: Path, missing: list[str], environ: Mapping[str, str] | None = None
) -> str:
    """The words for a compose file Compose cannot read: what is missing and where (deployment.env,
    or the shell, whose empty value Compose takes over the file's), the way out for this deployment
    by name, and how to stop its containers meanwhile, which needs no compose file (and runs nothing
    when none is up)."""
    shell = os.environ if environ is None else environ
    emptied = [name for name in missing if name in shell]
    where = "which deployment.env does not hold"
    if emptied:
        names = ", ".join(emptied)
        where += (
            f" ({names} {'is' if len(emptied) == 1 else 'are'} set empty in this shell, which "
            f"Compose reads before deployment.env: unset {names} first)"
        )
    named = f" --name {directory.name if directory.parent.name == 'deployments' else 'default'}"
    return (
        f"The compose file needs {', '.join(missing)}, {where}, so Docker Compose refuses every "
        f"command on this deployment and nothing was changed. Run `ospreyflow apply{named}`: it "
        "renders the compose file again and keeps or mints every value it needs (a backup set "
        "from before the value existed does not hold it). To stop its containers meanwhile: "
        "docker ps -q --filter "
        f"label=com.docker.compose.project={project(directory)} | xargs -r docker stop"
    )
