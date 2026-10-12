"""Where the product is, how to run its Python, and where its deployment is rendered
(`06_DECISIONS.md` ADR-114 Amendment 3 decision 3).

The command knows its checkout from `OSPREYFLOW_HOME`, else the folder the bootstrap recorded, else
the checkout it is run inside. A "product folder" is the one holding `harness/__init__.py` and
`osprey.yaml`: the repository root in the user's repository, or `OspreyFlow_Core` inside the
developer repository.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path

import yaml

#: The file the bootstrap writes the product path into, below `~/.config` (below `%APPDATA%` on
#: Windows). `install.sh` and `install.ps1` write the same place.
HOME_FILE_PARTS = ("ospreyflow", "home")
DEFAULT_PROFILE = "local-lite"


class CommandRefused(Exception):
    """Something the person can fix; the message says what, in words."""


def home_file(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if os.name == "nt" and env.get("APPDATA"):
        base = Path(env["APPDATA"])
    else:
        base = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base.joinpath(*HOME_FILE_PARTS)


def read_recorded_home() -> Path | None:
    """The product path the bootstrap recorded, or None when there is none."""
    try:
        text = home_file().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(text) if text else None


def _is_product(folder: Path) -> bool:
    return (folder / "harness" / "__init__.py").is_file() and (folder / "osprey.yaml").is_file()


def find_product(
    start: Path | None,
    env: Mapping[str, str],
    *,
    recorded: Callable[[], Path | None] = read_recorded_home,
) -> Path:
    """The product folder, from `OSPREYFLOW_HOME`, else the recorded folder, else by walking up from
    `start` (the current folder when None). A folder that is the developer repository stands for its
    `OspreyFlow_Core`."""
    chosen = env.get("OSPREYFLOW_HOME")
    if chosen:
        folder = Path(chosen).expanduser()
        if not _is_product(folder):
            raise CommandRefused(
                f"OSPREYFLOW_HOME is {folder}, which holds no OspreyFlow checkout (it needs "
                "harness/__init__.py and osprey.yaml). Point it at the checkout, or unset it."
            )
        return folder
    remembered = recorded()
    if remembered is not None and _is_product(remembered):
        return remembered
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if _is_product(folder):
            return folder
        if _is_product(folder / "OspreyFlow_Core"):
            return folder / "OspreyFlow_Core"
    raise CommandRefused(
        "No OspreyFlow checkout found here. Run the bootstrap (install.sh or install.ps1) once, "
        "run this from inside the checkout, or set OSPREYFLOW_HOME to it."
    )


def python_for(product: Path, *, windows: bool | None = None) -> list[str]:
    """The command that runs Python inside the checkout's own environment: its `.venv` when it has
    one, else `uv run`, which makes one."""
    windows = os.name == "nt" if windows is None else windows
    interpreter = product / ".venv" / ("Scripts/python.exe" if windows else "bin/python")
    if interpreter.exists():
        return [str(interpreter)]
    return ["uv", "run", "--project", str(product), "python"]


def read_config(product: Path) -> dict[str, object]:
    """The product's `osprey.yaml` as plain data; empty when it holds nothing."""
    loaded = yaml.safe_load((product / "osprey.yaml").read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise CommandRefused(f"{product / 'osprey.yaml'} does not hold settings.")
    return loaded


def deployment_dir(product: Path) -> Path:
    """Where the harness renders this product's deployment: `deploy/generated/<profile>`."""
    profile = read_config(product).get("profile") or DEFAULT_PROFILE
    return product / "deploy" / "generated" / str(profile)


def public_origin(product: Path) -> str:
    """The address the Glass is reached at: `network.public_origin`, else the Lite default."""
    network = read_config(product).get("network")
    if isinstance(network, dict) and network.get("public_origin"):
        return str(network["public_origin"])
    return "http://localhost:8080"
