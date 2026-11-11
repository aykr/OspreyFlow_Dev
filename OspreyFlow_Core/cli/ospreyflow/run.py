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
#: Advice that names a variable is not a secret (ADR-114 Amendment 8: a private repository is read
#: with `GITHUB_TOKEN`), but a name followed by a word cannot be told from a name followed by its
#: value (`GH_TOKEN hunter2`), so only **the producers' own fixed phrases** pass:
#: `harness.release`'s two lines for a private repository and `harness.apply`'s unset sign-in
#: secret (the orchestrator's confirmation of b2feedf, item 1). Any other line naming one stays
#: hidden.
_NAMED_ONLY = re.compile(
    r"\bor (?:GITHUB_TOKEN|GH_TOKEN) on this machine cannot read it\b"
    r"|\bset (?:GITHUB_TOKEN|GH_TOKEN) to (?:one|a token) that can read it\b"
    r"|\bOSPREY_ORG_SIGN_IN_SECRET is not set\."
)
#: Refresh's own refusals, as its `main` prints them and as `update` reports its files step's: a
#: line naming a secret is shown **only as one of these sentences in full** (anchored, the
#: variables' names alone, a deployment's name, nothing after), so neither a value after our words
#: nor a value among the names reaches the screen (the orchestrator's review of ad4bef7, item 1). A
#: variable's name has an underscore; a deployment's is lower case, digits and hyphens
#: (`secret-lab` too).
_DEPLOYMENT = r" --name [a-z0-9][a-z0-9-]*"
#: Every variable a deployment's compose file requires is ours (`OSPREY_…`), so a bare value shaped
#: like a name (`HUNTER_2`) is hidden. **Known limit**: a value shaped like one of ours
#: (`OSPREY_HUNTER_2`) would be shown as a name; no producer puts a value there (the
#: orchestrator's confirmation of b2feedf, item 2; checking the names against the compose file
#: would hide a refusal naming a variable only the new checkout requires, after update's rollback).
_VARIABLE = r"OSPREY(?:_[A-Z0-9]+)+"
_UNSET = (
    rf"This checkout's compose file requires {_VARIABLE}(?:, {_VARIABLE})*, which deployment\.env "
    rf"does not hold, so nothing was changed\. Run `ospreyflow apply{_DEPLOYMENT}` with the "
    r"checkout at the version you are moving to\."
)
#: `scripts.refresh.before_the_gateway_database`'s words, `{_N}` where it names the deployment;
#: held to refresh's own by `tests/cli/test_refusal_words_reach_the_operator.py`.
_GATEWAY_WORDS = (
    "This deployment was rendered before the model gateway kept its own database (ADR-135 "
    "Amendment 2), which a refresh cannot bring it to, so nothing was changed. With the "
    "checkout at the version you are moving to (git checkout <its tag>), run "
    "`ospreyflow backup{_N}`, then `ospreyflow apply{_N}` (it keeps every value deployment.env "
    "holds, and an install from a release on its own images), then "
    "`ospreyflow update{_N}` and `ospreyflow apply{_N}` "
    "once more for an install from a release (the second apply moves the providers' keys into "
    "the gateway), or `ospreyflow start --build{_N}` for one built from a checkout."
)
_GATEWAY = re.escape(_GATEWAY_WORDS).replace(re.escape("{_N}"), _DEPLOYMENT)
_OUR_SENTENCE = re.compile(
    r"(?:refresh: |ospreyflow: the update to v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.]+)? failed at "
    r"'bring the files up to date': refresh: )"
    rf"(?:{_UNSET}|{_GATEWAY})"
)


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
        if not _SECRET.search(_NAMED_ONLY.sub("", line)) or _OUR_SENTENCE.fullmatch(line):
            return line
        return self._notice


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


def _read_env_file(path: Path) -> dict[str, str]:
    """A copy of `harness.preflight.ports.read_env_file`: an env file as Compose reads it."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, sep, value = line.partition("=")
        if not sep or not name.strip():
            continue
        quoted = value.strip()
        if len(quoted) >= 2 and quoted[0] == quoted[-1] and quoted[0] in "'\"":
            value = quoted[1:-1]
        else:
            # The comment's space is looked for before the value is stripped: `X= # note` is
            # empty, as Compose reads it, not "# note" (the lane review of the carries, item 9).
            value = re.split(r"\s#", value, maxsplit=1)[0].strip()
        values[name.strip()] = value
    return values


def unset_required(directory: Path, environ: Mapping[str, str] | None = None) -> list[str]:
    """Each name the deployment's compose file requires that Compose would find without a value."""
    shell = os.environ if environ is None else environ
    compose_text = (directory / "compose.yaml").read_text(encoding="utf-8")
    env_path = directory / "deployment.env"
    held = _read_env_file(env_path) if env_path.is_file() else {}
    missing = set()
    for name, colon in _REQUIRED.findall(compose_text):
        found = shell[name] if name in shell else held.get(name)
        if found is None or (colon and found == ""):
            missing.add(name)
    return sorted(missing)


def project(directory: Path) -> str:
    """`harness.compose_env.project`: the compose project's name (`name:`), or the folder's."""
    name = directory.name
    for line in (directory / "compose.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            name = line.partition(":")[2].strip().strip("\"'") or name
            break
    return name


def locked_out(
    directory: Path, missing: list[str], environ: Mapping[str, str] | None = None
) -> str:
    """`harness.compose_env.locked_out`'s words."""
    name = project(directory)
    shell = os.environ if environ is None else environ
    emptied = [name for name in missing if name in shell]
    unheld = [name for name in missing if name not in shell]
    parts = []
    if unheld:
        parts.append(f"{', '.join(unheld)}, which deployment.env does not hold")
    if emptied:
        names = ", ".join(emptied)
        parts.append(
            f"{names}, which this shell sets empty (Compose reads the shell before "
            f"deployment.env: unset {names} first)"
        )
    named = f" --name {directory.name if directory.parent.name == 'deployments' else 'default'}"
    return (
        f"The compose file needs {'; and '.join(parts)}, so Docker Compose refuses every "
        f"command on this deployment and nothing was changed. Run `ospreyflow apply{named}`: it "
        "renders the compose file again and keeps or mints every value it needs (a backup set "
        "from before the value existed does not hold it). To stop its containers meanwhile: "
        "docker ps -q --filter "
        f"label=com.docker.compose.project={name} | xargs -r docker stop"
    )
