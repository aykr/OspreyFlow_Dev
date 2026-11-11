"""Running the work the command delegates, with the output kept free of secrets.

`Runner` is what every verb calls: it streams a command's output line by line through a `Redactor`
and returns the exit code. The real one uses `subprocess`; the tests inject a recorder.
`06_DECISIONS.md` ADR-114 Amendment 3 decision 4: an install ends by saying where the sign-in
details are kept, "never a password".
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

_SECRET = re.compile(r"(?i)(password|secret|token|client_secret)")
#: A variable named, with no value after it, is advice, not a secret (ADR-114 Amendment 8: a
#: private repository is read with `GITHUB_TOKEN`). Its value, and every other line, stays hidden.
_NAMED_ONLY = re.compile(r"\b(?:GITHUB_TOKEN|GH_TOKEN|OSPREY_ORG_SIGN_IN_SECRET)\b(?!\s*[=:])")


class Runner(Protocol):
    def __call__(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
    ) -> int: ...


class Capture(Protocol):
    """Like a `Runner`, but returns the exit code and the output instead of showing it."""

    def __call__(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
    ) -> tuple[int, str]: ...


class StepFailed(Exception):
    def __init__(self, step: str, code: int) -> None:
        super().__init__(f"The step '{step}' failed (exit {code}); nothing after it was run.")
        self.code = code


class Redactor:
    """Hides any line that names a secret, saying where the person can find it instead."""

    def __init__(self, env_file: Path | str) -> None:
        self._notice = (
            f"  [a line naming a secret was hidden — the sign-in details are in {env_file}]"
        )

    def __call__(self, line: str) -> str:
        return self._notice if _SECRET.search(_NAMED_ONLY.sub("", line)) else line


class SubprocessRunner:
    def __init__(self, redact: Redactor) -> None:
        self._redact = redact

    def __call__(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
    ) -> int:
        try:
            process = subprocess.Popen(
                list(argv),
                cwd=cwd,
                env={**os.environ, **(env or {})},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
            )
        except FileNotFoundError as missing:
            print(f"Could not run {argv[0]}: {missing.strerror or 'not found'}.")
            return 127
        assert process.stdout is not None
        for line in process.stdout:
            print(self._redact(line.rstrip("\r\n")), flush=True)
        return process.wait()


def subprocess_capture(
    argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
) -> tuple[int, str]:
    try:
        done = subprocess.run(
            list(argv),
            cwd=cwd,
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        return 127, ""
    return done.returncode, done.stdout


def compose(directory: Path) -> list[str]:
    """`docker compose` against a rendered deployment, always with its own env file (the secrets the
    harness generates live there; without it Compose cannot see them)."""
    return [
        "docker",
        "compose",
        "--env-file",
        str(directory / "deployment.env"),
        "-f",
        str(directory / "compose.yaml"),
    ]


#: A copy of `harness.compose_env`'s reading, for `ospreyflow stop`, which cannot import the
#: harness; `tests/harness/test_compose_lockout.py` holds the two to the same answers.
_REQUIRED = re.compile(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)(:?)\?")


def unset_required(directory: Path, environ: Mapping[str, str] | None = None) -> list[str]:
    """Each name the deployment's compose file requires that Compose would find without a value."""
    shell = os.environ if environ is None else environ
    compose_text = (directory / "compose.yaml").read_text(encoding="utf-8")
    held: dict[str, str] = {}
    env_path = directory / "deployment.env"
    for line in env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []:
        name, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and not name.startswith("#"):
            held[name.strip()] = value.strip().strip("\"'")
    missing = set()
    for name, colon in _REQUIRED.findall(compose_text):
        found = shell[name] if name in shell else held.get(name)
        if found is None or (colon and found == ""):
            missing.add(name)
    return sorted(missing)


def locked_out(directory: Path, missing: list[str]) -> str:
    """`harness.compose_env.locked_out`'s words."""
    name = directory.name
    for line in (directory / "compose.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            name = line.partition(":")[2].strip().strip("\"'") or name
            break
    return (
        f"The compose file needs {', '.join(missing)}, which deployment.env does not hold, so "
        "Docker Compose refuses every command on this deployment and nothing was changed. Put each "
        "back in deployment.env from the deployment's last backup set (its config/deployment.env), "
        "then run this again. To stop its containers meanwhile: docker stop $(docker ps -q "
        f"--filter label=com.docker.compose.project={name})"
    )
