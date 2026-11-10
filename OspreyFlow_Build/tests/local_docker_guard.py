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
import re
import shlex
import shutil
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


def why(switch: Path, call: str = "") -> str:
    named = f" ({call})" if call else ""
    return (
        f"a server-only test: it calls the docker CLI{named}, and local stacks are off on this "
        f"machine ({switch}); run it on the test server "
        "(scripts/stack_lease.sh offline|live <lane>)"
    )


#: Programs that run the command after their own options: `env FOO=1 docker …`,
#: `sudo -u x docker …`, `timeout 60 docker …` (the independent review's shapes).
_WRAPPERS = {"env", "sudo", "timeout", "nice", "nohup", "stdbuf", "exec", "command"}
#: A wrapper's option that takes the next word as its value.
_VALUED = {
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"},
    "nice": {"-n"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "env": {"-u", "-C", "-S"},
}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _words(args: Any) -> list[str] | None:
    """A Popen call's argv as words; None for a command string."""
    if isinstance(args, (str, bytes)):
        return None
    if isinstance(args, os.PathLike):
        return [os.fsdecode(args)]
    if isinstance(args, Sequence):
        return [os.fsdecode(a) if isinstance(a, (str, bytes, os.PathLike)) else "" for a in args]
    return []


def _docker_in_argv(words: list[str]) -> bool:
    while words and _ASSIGNMENT.match(words[0]):
        words = words[1:]
    while words and os.path.basename(words[0]) in _WRAPPERS:
        wrapper, words = os.path.basename(words[0]), words[1:]
        while words and (words[0].startswith("-") or _ASSIGNMENT.match(words[0])):
            takes = words[0] in _VALUED.get(wrapper, set())
            words = words[2:] if takes else words[1:]
        if wrapper == "timeout" and words:
            words = words[1:]  # its duration
    if not words:
        return False
    program = os.path.basename(words[0])
    if program == "docker":
        return True
    if program in _SHELLS:
        for i, word in enumerate(words[1:], start=1):
            if word.startswith("-") and not word.startswith("--") and "c" in word[1:]:
                return i + 1 < len(words) and _docker_in_command(words[i + 1])
    return False


def _docker_in_command(text: str) -> bool:
    """Whether any simple command in a shell string starts the docker CLI."""
    for segment in re.split(r"&&|\|\||[;|&\n()]", text):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        if _docker_in_argv(words):
            return True
    return False


def starts_docker(args: Any) -> bool:
    """Whether a Popen call's `args` start the docker CLI: directly, behind a wrapper (`env`,
    `sudo`, `timeout` …), or anywhere in a shell's command string (`sh -c "cd x && docker …"`)."""
    words = _words(args)
    if words is None:
        text = args.decode() if isinstance(args, bytes) else args
        return _docker_in_command(text)
    return _docker_in_argv(words)


def _named(args: Any) -> str:
    words = _words(args)
    text = (
        (args.decode() if isinstance(args, bytes) else args) if words is None else " ".join(words)
    )
    return text if len(text) <= 60 else text[:57] + "..."


def guarded_popen(popen: type[subprocess.Popen[Any]], switch: Path) -> type[subprocess.Popen[Any]]:
    """`popen`, refusing a docker call with a skip in words while `switch` exists."""

    class Guarded(popen):  # type: ignore[valid-type, misc]
        def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
            if switch.exists() and starts_docker(args):
                pytest.skip(why(switch, _named(args)), allow_module_level=True)
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


_installed: dict[str, Any] = {}


def install() -> None:
    switch = switch_path()
    if not switch.exists():
        return
    shim_dir = Path(tempfile.mkdtemp(prefix="osprey-no-docker-"))
    _installed.update(popen=subprocess.Popen, path=os.environ.get("PATH", ""), shim_dir=shim_dir)
    subprocess.Popen = guarded_popen(subprocess.Popen, switch)  # type: ignore[assignment, misc]
    refusing_docker(shim_dir, switch)
    os.environ["PATH"] = f"{shim_dir}{os.pathsep}{_installed['path']}"


def uninstall() -> None:
    """Put back what `install` changed, and remove its folder."""
    if not _installed:
        return
    subprocess.Popen = _installed["popen"]  # type: ignore[misc]
    os.environ["PATH"] = _installed["path"]
    shutil.rmtree(_installed["shim_dir"], ignore_errors=True)
    _installed.clear()


def pytest_configure(config: pytest.Config) -> None:
    install()


def pytest_unconfigure(config: pytest.Config) -> None:
    uninstall()
