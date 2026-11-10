"""No test starts the docker CLI where local stacks are off (CARRIES, 10 November 2026).

Docker Desktop came up on the owner's Mac at 08:18 UTC that day, most likely from a lane running
`tests/harness/test_workspace_proxy.py` locally, which shells out to `docker build`. On a machine
holding `<lease dir>/no-local-stacks` (the owner's per-machine switch of 9 November, read by
`scripts/stack_lease.sh`; the lease dir is `$OSPREY_LEASE_DIR`, else `~/.ospreyflow`), a test that
calls the docker CLI is a server-only test: it runs on the test server through
`stack_lease.sh offline|live <lane>`, where the switch is absent.

`install()`, run by this plugin's `pytest_configure` (`tests/conftest.py`'s `pytest_plugins`),
wraps `subprocess.Popen` (which `run`, `check_output` and asyncio's subprocesses all go through)
for the whole session, so a docker call
at collection (`test_image_references.py` asks `docker info` for its skip condition), in a
module-scoped fixture or in a test skips at once, saying why, before any process starts. A child
process the test starts (`python -m harness.apply`, `make`) is past the wrapper, so the session's
`PATH` also leads with a `docker` that refuses in words and starts nothing.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

SWITCH = "no-local-stacks"


def switch_path(environ: os._Environ[str] | dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    return Path(env.get("OSPREY_LEASE_DIR") or Path.home() / ".ospreyflow") / SWITCH


def why(switch: Path) -> str:
    return (
        f"a server-only test: it calls the docker CLI, and local stacks are off on this machine "
        f"({switch}); run it on the test server (scripts/stack_lease.sh offline|live <lane>)"
    )


def _program(args: Any) -> str | None:
    """The program a Popen call starts: the first word of a command string, or of an argv."""
    if isinstance(args, (str, bytes)):
        text = args.decode() if isinstance(args, bytes) else args
        try:
            words = shlex.split(text)
        except ValueError:
            words = text.split()
        return os.path.basename(words[0]) if words else None
    if isinstance(args, Sequence) and args:
        first = args[0]
        if isinstance(first, (str, bytes, Path)):
            return os.path.basename(os.fsdecode(first))
        return None
    if isinstance(args, os.PathLike):
        return os.path.basename(os.fsdecode(args))
    return None


def starts_docker(args: Any) -> bool:
    """Whether a Popen call's `args` start the docker CLI, directly or as `sh -c "docker …"`."""
    if _program(args) == "docker":
        return True
    if isinstance(args, Sequence) and not isinstance(args, (str, bytes)) and len(args) >= 3:
        if _program(args) in {"sh", "bash", "zsh"} and args[1] == "-c":
            return _program(args[2]) == "docker"
    return False


def guarded_popen(popen: type[subprocess.Popen[Any]], switch: Path) -> type[subprocess.Popen[Any]]:
    """`popen`, refusing a docker call with a skip in words while `switch` exists."""

    class Guarded(popen):  # type: ignore[valid-type, misc]
        def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
            if switch.exists() and starts_docker(args):
                pytest.skip(why(switch), allow_module_level=True)
            super().__init__(args, *rest, **kwargs)

    return Guarded


def refusing_docker(directory: Path, switch: Path) -> Path:
    """A `docker` in `directory` that says why and exits 1, for a child process's own calls."""
    shim = directory / "docker"
    shim.write_text(
        f"#!/bin/sh\necho {shlex.quote('refused: ' + why(switch))} >&2\nexit 1\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return shim


def install() -> None:
    switch = switch_path()
    if not switch.exists():
        return
    subprocess.Popen = guarded_popen(subprocess.Popen, switch)  # type: ignore[assignment, misc]
    shim_dir = Path(tempfile.mkdtemp(prefix="osprey-no-docker-"))
    refusing_docker(shim_dir, switch)
    os.environ["PATH"] = f"{shim_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def pytest_configure(config: pytest.Config) -> None:
    install()
