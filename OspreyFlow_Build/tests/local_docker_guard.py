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
#: Every refusing `docker`'s folder is made with this prefix (`install`). Under xdist each worker
#: installs its own on top of the controller's, which its environment inherits.
SHIM_PREFIX = "osprey-no-docker-"


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


def guarded_popen(
    popen: type[subprocess.Popen[Any]], switch: Path, shim_dir: Path | None = None
) -> type[subprocess.Popen[Any]]:
    """`popen`, refusing a docker call with a skip in words while `switch` exists: all but the one
    command `is_the_caddy_validation` names, which is handed the real docker."""

    class Guarded(popen):  # type: ignore[valid-type, misc]
        def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
            if switch.exists() and starts_docker(args):
                asking = os.environ.get("PYTEST_CURRENT_TEST", "")
                if rest or not is_the_caddy_validation(args, kwargs, asking):
                    pytest.skip(why(switch, _named(args)), allow_module_level=True)
                real = the_real_docker(shim_dir)
                if real:
                    args = [real, *args[1:]]
            super().__init__(args, *rest, **kwargs)

    return Guarded


# --- The one exempt command (the owner's ruling D234, 24 November 2026) ------------------------
#
# **Exempt: exactly one command, and nothing else.** The Caddy test of slice PL7f
# (`tests/harness/test_page_addresses_caddy.py`) runs the proxy's own image once to validate every
# Caddyfile the deployment can render; under the switch this guard refused that call as well, so
# the real Caddy ran on no merge on this Mac (the owner's condition of 23 November 2026). The owner
# exempted that one command. It is matched on its whole shape, as `subprocess.run` hands it to
# `Popen` (the argument list, `subprocess.Popen`'s own keyword arguments), and on the test asking:
#
#     docker run --rm --network none
#         -v <folder>:/cases:ro -v <folder>:/etc/caddy:ro -v <folder>:/certs:ro
#         caddy:2.11.4-alpine sh -c <CADDY_SCRIPT>
#
# with each `<folder>` under the system's temporary folder (so no mount can name the Docker socket,
# the home folder or `/`). Any difference is refused as before: another image or tag, a fourth
# mount, a mount that is not `:ro`, another network, no `--rm`, another script, a shell, an
# environment, another executable, another test asking, and every other docker command (the
# test's own earlier `docker image inspect` and `caddy hash-password` runs are gone for that
# reason). Under xdist (`make test`, the merge gate) each worker's plugin puts a second refusing
# `docker` in front of the one its controller put on the `PATH` the worker inherited, so the lookup
# of the real docker leaves out every folder made with `SHIM_PREFIX`, not only its own (PL7f round
# 10; `test_the_one_command_holds_under_the_merge_gates_own_run`). Every other docker call stays refused under the switch, the refusing `docker` on the
# session's `PATH` included: the one exempt call is handed the real docker (found on the `PATH`
# without the shim's folder), and nothing else is.
#
# **When 017-1 lands (the test server's container checks), this test moves there and this
# exemption comes out**, with `CADDY_*`, `is_the_caddy_validation` and the tests that hold them
# in `tests/test_local_docker_guard.py`.
CADDY_TEST = "tests/harness/test_page_addresses_caddy.py"
CADDY_IMAGE = "caddy:2.11.4-alpine"
#: One container validates every case: one `caddy validate` each, the exit code and what it said.
CADDY_SCRIPT = (
    'for d in /cases/*; do n=$(basename "$d"); '
    'out=$(caddy validate --config "$d/Caddyfile" --adapter caddyfile 2>&1); rc=$?; '
    'echo "@@CASE $n $rc"; echo "$out"; done'
)
#: The three mounts, in order: where each lands in the container.
CADDY_MOUNTS = ("/cases", "/etc/caddy", "/certs")


def _a_folder_under_the_temporary_one(host: str) -> bool:
    if not host or ":" in host or not os.path.isabs(host):
        return False
    temporary = Path(tempfile.gettempdir()).resolve()
    resolved = Path(os.path.realpath(host))
    return resolved != temporary and temporary in resolved.parents


def is_the_caddy_validation(args: Any, kwargs: dict[str, Any], asking: str) -> bool:
    """Whether this `Popen` call is the Caddy test's one command, asked by that test (`asking` is
    pytest's `PYTEST_CURRENT_TEST`: `<file>::<test> (<phase>)`, the file relative to the root)."""
    if asking.partition("::")[0] != CADDY_TEST:
        return False
    if kwargs.get("shell") or kwargs.get("env") is not None or kwargs.get("executable"):
        return False
    if not isinstance(args, list) or not all(isinstance(word, str) for word in args):
        return False
    head = ["docker", "run", "--rm", "--network", "none"]
    if len(args) != len(head) + 2 * len(CADDY_MOUNTS) + 4 or args[: len(head)] != head:
        return False
    mounts = args[len(head) : len(head) + 2 * len(CADDY_MOUNTS)]
    for i, target in enumerate(CADDY_MOUNTS):
        flag, value = mounts[2 * i], mounts[2 * i + 1]
        host, _, rest = value.rpartition(f":{target}:")
        if flag != "-v" or rest != "ro" or not _a_folder_under_the_temporary_one(host):
            return False
    return args[-4:] == [CADDY_IMAGE, "sh", "-c", CADDY_SCRIPT]


def _a_refusing_shims_folder(folder: str, shim_dir: Path | None) -> bool:
    """This process's own shim folder, or one an enclosing session made: under xdist the worker's
    `PATH` is the controller's (its shim first) with the worker's own put in front, and the
    controller's refusing `docker` is not the real one (PL7f round 10)."""
    if not folder:
        return False
    return bool(shim_dir and Path(folder) == shim_dir) or Path(folder).name.startswith(SHIM_PREFIX)


def the_real_docker(shim_dir: Path | None) -> str | None:
    """The docker on the `PATH` as it is now, leaving out every refusing shim's folder."""
    folders = os.environ.get("PATH", "").split(os.pathsep)
    kept = [f for f in folders if not _a_refusing_shims_folder(f, shim_dir)]
    return shutil.which("docker", path=os.pathsep.join(kept))


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
    shim_dir = Path(tempfile.mkdtemp(prefix=SHIM_PREFIX))
    _installed.update(popen=subprocess.Popen, path=os.environ.get("PATH", ""), shim_dir=shim_dir)
    subprocess.Popen = guarded_popen(subprocess.Popen, switch, shim_dir)  # type: ignore[assignment, misc]
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
