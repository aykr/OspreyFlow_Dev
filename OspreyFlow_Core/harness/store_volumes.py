"""The stores' data moved into their named volumes, once (`06_DECISIONS.md` ADR-114 Amendment 35;
build order step 26).

    PYTHONPATH=.:packages python -m harness.store_volumes <deployment>/compose.yaml

**As found on the first server (4 November 2026).** Until v0.4.10 the rendered `compose.yaml` gave
PostgreSQL, ArcadeDB and Valkey only the anonymous volumes their images' `VOLUME` lines make, and
OpenSearch none at all. Compose carries an anonymous volume over when it recreates a container, so
`stop`, `start`, `apply` and `update` kept the data; a new container gets new, empty ones, so
`docker compose down` then `up`, or `uninstall --keep-data` then an install, did not. The render now
gives each store a named volume (`harness.render.STORE_VOLUMES`); this moves a deployment rendered
before into them. It runs before every `up` that follows a re-render, wherever
`harness.ingest_uploads` runs: `harness.apply` (install and `ospreyflow apply`), `scripts.refresh`
(`start --build`), the `ospreyflow` command's `start` and `switch`, and `harness.update` (after its
backup and pull, so a failure rolls back).

**What it does**, for each store whose `compose.yaml` mount is a named volume its container does not
mount yet:

1. Every container of the deployment is stopped, so nothing writes.
2. Each store is started alone on its old data, asked for a figure (below), and stopped.
3. Its named volume is made (or found empty), and the data copied by a one-shot container of
   **the image the old container runs, by ID** (nothing is pulled), as root, with no network:
   `cp -a`, then the top folder's owner and mode set to the original's. PostgreSQL refuses a data
   directory that is not its user's or whose mode is not `0700`/`0750`, so ownership and modes
   must be exact.
4. The copy is checked, not trusted: both sides listed by the same image — every entry's owner,
   group, mode, kind and, for a file, its SHA-256 — and the lists must be identical.
5. Only when every copy is good is each store started on its named volume alone, and asked for its
   figure again: it must be the same.

The figures: PostgreSQL's databases; ArcadeDB's databases; Valkey's keys that do not expire, after
a `SAVE` (a key with a time to live may expire between the readings); OpenSearch's indexes.
OpenSearch's data is never copied: nothing in this version writes an index (ADR-114 Amendment 35
point 2), so it must hold none but its own system indexes, or nothing is moved.

**The old volume is never removed**: the last words name each one and how to remove it. A failure
before any store has started on its named volume removes the named volumes this filled (each was
absent or empty), so nothing is half-moved and the next run starts again; the old containers and
volumes are as they were.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from harness.backup import arcadedb_request
from harness.render import STORE_VOLUMES, StoreVolume

#: `(exit code, what it said)` for a command, as `harness.update` and `harness.ingest_uploads` run.
Run = Callable[[Sequence[str]], tuple[int, str]]

#: The compose volume names, for a test to look for.
VOLUME_NAMES = tuple(row.volume for row in STORE_VOLUMES)

#: Off only in the test suite (`tests/conftest.py`): a test that drives `apply`, `refresh` or
#: `update` for another reason must not ask the machine's own Docker. The move's own tests turn it
#: back on against their stand-in.
ENABLED = True

#: How often, and how long apart, a store just started is asked for its figure.
ATTEMPTS = 60
PAUSE_SECONDS = 5.0

#: Services whose data is checked and never copied (Amendment 35 point 2).
NOT_COPIED = frozenset({"opensearch"})

_LISTING = (
    'cd "$1" && find . | LC_ALL=C sort | while IFS= read -r f; do '
    'if [ -L "$f" ]; then s="link:$(readlink "$f")"; '
    'elif [ -f "$f" ]; then s=$(sha256sum < "$f" | cut -d" " -f1); else s=-; fi; '
    'printf "%s %s %s\\n" "$(stat -c "%u:%g:%a:%F" "$f")" "$s" "$f"; done'
)

_COPY = (
    "set -e; "
    '[ -z "$(ls -A /to)" ] || { echo "the named volume is not empty" >&2; exit 3; }; '
    "cp -a /from/. /to/; "
    'chown "$(stat -c %u:%g /from)" /to; '
    'chmod "$(stat -c %a /from)" /to'
)

_FIGURES: dict[str, str] = {
    "postgres": (
        'psql -U "$POSTGRES_USER" -d postgres -Atc '
        '"SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY 1"'
    ),
    "valkey": "valkey-cli SAVE >/dev/null && valkey-cli INFO keyspace",
    "opensearch": 'curl -fsS "http://127.0.0.1:9200/_cat/indices?h=index"',
}


class StoresNotMoved(Exception):
    """The move stopped. `started`: a store had already started on its named volume, so the
    deployment's own data is no longer only where it was. `made`: the named volumes left filled."""

    def __init__(
        self, why: str, *, started: bool, made: Sequence[str] = (), old: Sequence[str] = ()
    ):
        self.why = why
        self.started = started
        self.made = list(made)
        self.old = list(old)
        super().__init__(self.words())

    def words(self, *, again: bool = True) -> str:
        """What to show. `again`: say the deployment is stopped and to run the command again —
        not for `update`, whose rollback then starts the old version itself."""
        where = ", ".join(self.old) if self.old else "its old volumes"
        if self.started:
            return (
                f"the stores' data could not be moved to named volumes: {self.why}. Nothing was "
                f"removed: the data as it was is still in {where}."
            )
        said = (
            f"the stores' data could not be moved to named volumes: {self.why}. Nothing was "
            f"removed: each store's data is still where it was ({where})."
        )
        if again:
            said += (
                " The deployment is stopped. Run the same command again once the cause is fixed."
            )
        return said


@dataclass
class Moved:
    """What a move did: the services moved, and the old volumes (or host folders) left behind."""

    services: list[str] = field(default_factory=list)
    left: list[str] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)

    def removal_words(self) -> str:
        if not (self.left or self.folders):
            return ""
        lines = []
        if self.left:
            lines.append(
                "The old volumes are left in place: "
                + ", ".join(self.left)
                + ". Once the deployment works as before, remove them with:\n  docker volume rm "
                + " ".join(self.left)
            )
        if self.folders:
            lines.append(
                "The host folders the stores used are left as they were: " + ", ".join(self.folders)
            )
        return "\n".join(lines)


@dataclass
class _Pending:
    row: StoreVolume
    container: str
    image: str
    source: str | None  # a volume's name, a host folder, or None: in the container itself
    source_is_folder: bool
    target: str
    target_exists: bool


def _ok(run: Run, argv: Sequence[str], what: str) -> str:
    code, said = run(argv)
    if code != 0:
        last = [line for line in said.splitlines() if line.strip()]
        raise _Step(f"{what}: {last[-1] if last else f'exit {code}'}")
    return said


class _Step(Exception):
    pass


def _containers(run: Run, project: str, service: str) -> list[str]:
    said = _ok(
        run,
        ["docker", "ps", "-a", "-q",
         "--filter", f"label=com.docker.compose.project={project}",
         "--filter", f"label=com.docker.compose.service={service}"],
        f"find {service}'s container",
    )  # fmt: skip
    return [line.strip() for line in said.splitlines() if line.strip()]


def _target_name(document: dict[str, Any], project: str, volume: str) -> str:
    declared = (document.get("volumes") or {}).get(volume)
    if isinstance(declared, dict) and declared.get("name"):
        return str(declared["name"])
    return f"{project}_{volume}"


def _one_shot(image: str, mounts: Sequence[str], script: str, *args: str) -> list[str]:
    argv = ["docker", "run", "--rm", "--network", "none", "--user", "0:0", "--entrypoint", "sh"]
    for mount in mounts:
        argv += ["-v", mount]
    return [*argv, image, "-c", script, "sh", *args]


def _volume_is_empty(run: Run, image: str, name: str) -> bool:
    said = _ok(run, _one_shot(image, [f"{name}:/to"], "ls -A /to"), f"look in {name}")
    return not said.strip()


def plan(compose_file: Path, *, run: Run) -> list[_Pending]:
    """What a move would do, asking Docker and changing nothing."""
    document = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
    project = str(document.get("name") or "")
    services = document.get("services") or {}
    pending: list[_Pending] = []
    for row in STORE_VOLUMES:
        service = services.get(row.service)
        if not isinstance(service, dict):
            continue
        if f"{row.volume}:{row.path}" not in [str(v) for v in service.get("volumes") or []]:
            continue
        found = _containers(run, project, row.service)
        if not found:
            continue  # nothing installed yet: the named volume is made by the first `up`
        if len(found) > 1:
            raise StoresNotMoved(
                f"{row.service} has {len(found)} containers; one was expected", started=False
            )
        details = json.loads(_ok(run, ["docker", "inspect", found[0]], f"inspect {row.service}"))[0]
        target = _target_name(document, project, row.volume)
        mount = next(
            (m for m in details.get("Mounts") or [] if m.get("Destination") == row.path), None
        )
        if mount is not None and mount.get("Type") == "volume" and mount.get("Name") == target:
            continue  # already moved
        if mount is None:
            source, is_folder = None, False
        elif mount.get("Type") == "bind":
            source, is_folder = str(mount.get("Source")), True
        else:
            source, is_folder = str(mount.get("Name")), False
        if source is None and row.service not in NOT_COPIED:
            raise StoresNotMoved(
                f"{row.service} keeps {row.path} inside its container, not in a volume; it was "
                "not moved",
                started=False,
            )
        image = str(details.get("Image"))
        exists = run(["docker", "volume", "inspect", target])[0] == 0
        if exists and not _volume_is_empty(run, image, target):
            raise StoresNotMoved(
                f"{row.service}: both its current {'folder' if is_folder else 'volume'} "
                f"({source or 'its container'}) and the named volume {target} hold data, so "
                f"neither was touched. If {target} is left from an earlier attempt, remove it "
                f"(docker volume rm {target}) and run this again",
                started=False,
            )
        pending.append(_Pending(row, found[0], image, source, is_folder, target, exists))
    return pending


def _figure(
    run: Run, service: str, container: str, password: str, sleep: Callable[[float], None]
) -> str:
    if service == "arcadedb":
        command = arcadedb_request(password, "/api/v1/databases")
    else:
        command = _FIGURES[service]
    said = ""
    for attempt in range(ATTEMPTS):
        code, said = run(["docker", "exec", container, "sh", "-c", command])
        if code == 0:
            return _read_figure(service, said)
        if attempt + 1 < ATTEMPTS:
            sleep(PAUSE_SECONDS)
    last = [line for line in said.splitlines() if line.strip()]
    raise _Step(f"{service} did not answer ({last[-1] if last else 'no answer'})")


def _read_figure(service: str, said: str) -> str:
    if service == "postgres":
        names = [line.strip() for line in said.splitlines() if line.strip()]
        return "the databases " + ", ".join(names) if names else "no databases"
    if service == "arcadedb":
        start = said.find("{")
        names = sorted(str(n) for n in json.loads(said[start:])["result"])
        return "the databases " + ", ".join(names) if names else "no databases"
    if service == "valkey":
        kept = [
            f"db{db}: {int(keys) - int(expires)}"
            for db, keys, expires in re.findall(r"db(\d+):keys=(\d+),expires=(\d+)", said)
        ]
        return "keys that do not expire " + ", ".join(kept) if kept else "no keys"
    indexes = sorted(
        line.strip()
        for line in said.splitlines()
        if line.strip() and not line.strip().startswith(".")
    )
    return "the indexes " + ", ".join(indexes) if indexes else "no index of its own"


def _env_value(env_file: Path, name: str) -> str:
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.partition("=")[2].strip()
    except OSError:
        pass
    return ""


def _listing(run: Run, image: str, mount: str, what: str) -> str:
    return _ok(run, _one_shot(image, [f"{mount}:/v:ro"], _LISTING, "/v"), f"list {what}")


def move(
    compose_file: Path,
    *,
    run: Run,
    say: Callable[[str], None] = print,
    up_extra: Sequence[str] = (),
    sleep: Callable[[float], None] = time.sleep,
) -> Moved:
    """Moves what `plan` finds; does nothing (and asks Docker only to look) when nothing is found.
    Raises `StoresNotMoved` with the words to show."""
    if not ENABLED:
        return Moved()
    try:
        pending = plan(compose_file, run=run)
    except _Step as failed:
        raise StoresNotMoved(str(failed), started=False) from failed
    if not pending:
        return Moved()
    document = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
    project = str(document.get("name") or "")
    password = _env_value(compose_file.parent / "deployment.env", "OSPREY_ARCADEDB_PASSWORD")
    services = list(dict.fromkeys(p.row.service for p in pending))
    old = [p.source for p in pending if p.source and not p.source_is_folder]
    say(
        "The stores' data moves to named volumes, once: "
        + ", ".join(services)
        + ". The deployment is stopped while it moves; the old volumes are kept."
    )
    made: list[str] = []
    before: dict[str, str] = {}
    alone: str | None = None  # a store started on its old data, to stop again if this fails
    try:
        running = _ok(
            run,
            ["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={project}"],
            "find the deployment's containers",
        ).split()
        if running:
            _ok(run, ["docker", "stop", *running], "stop the deployment")
        for service in services:
            mine = [p for p in pending if p.row.service == service]
            container = mine[0].container
            alone = container
            _ok(run, ["docker", "start", container], f"start {service} on its old data")
            before[service] = _figure(run, service, container, password, sleep)
            _ok(run, ["docker", "stop", container], f"stop {service}")
            alone = None
            if service in NOT_COPIED:
                if before[service] != "no index of its own":
                    raise _Step(
                        f"{service} holds {before[service]}, which OspreyFlow does not write; they "
                        "are kept in its container, which the move would replace, so nothing was "
                        "moved. Snapshot or remove them first"
                    )
                say(f"  {service}: holds no index of its own, so nothing is copied; it starts "
                    "on its named volume empty.")  # fmt: skip
                continue
            say(f"  {service}: {before[service]}.")
            for pending_row in mine:
                _copy(run, pending_row, project, made, say)
    except _Step as failed:
        if alone is not None:
            run(["docker", "stop", alone])
        removed = _remove(run, made)
        raise StoresNotMoved(str(failed) + removed, started=False, made=[], old=old) from failed
    compose = [
        "docker", "compose", "--env-file", str(compose_file.parent / "deployment.env"),
        "-f", str(compose_file),
    ]  # fmt: skip
    try:
        for service in services:
            _ok(run, [*compose, "up", "-d", "--no-deps", "--wait", *up_extra, service],
                f"start {service} on its named volume")  # fmt: skip
            found = _containers(run, project, service)
            after = _figure(run, service, found[0] if found else service, password, sleep)
            if after != before[service]:
                raise _Step(
                    f"{service} on its named volume answers with {after}, where before it "
                    f"answered with {before[service]}"
                )
            say(f"  {service}: started on its named volume with {after}, as before.")
    except _Step as failed:
        raise StoresNotMoved(str(failed), started=True, made=made, old=old) from failed
    moved = Moved(
        services=services,
        left=old,
        folders=[p.source for p in pending if p.source and p.source_is_folder],
    )
    say("The stores now keep their data in named volumes.")
    words = moved.removal_words()
    if words:
        say(words)
    return moved


def _copy(
    run: Run, pending: _Pending, project: str, made: list[str], say: Callable[[str], None]
) -> None:
    row, target = pending.row, pending.target
    if not pending.target_exists:
        _ok(
            run,
            ["docker", "volume", "create",
             "--label", f"com.docker.compose.project={project}",
             "--label", f"com.docker.compose.volume={row.volume}", target],
            f"make {target}",
        )  # fmt: skip
    made.append(target)
    assert pending.source is not None
    say(f"  {row.service}: copying {row.path} from {pending.source} to {target}…")
    original = _listing(run, pending.image, pending.source, f"{row.service}'s old data")
    _ok(
        run,
        _one_shot(pending.image, [f"{pending.source}:/from:ro", f"{target}:/to"], _COPY),
        f"copy {row.service}'s {row.path} to {target}",
    )
    copied = _listing(run, pending.image, target, target)
    if copied != original:
        first = next(
            (f"{a!r} became {b!r}" for a, b in zip(original.splitlines(), copied.splitlines(),
                                                    strict=False) if a != b),
            f"{len(original.splitlines())} entries became {len(copied.splitlines())}",
        )  # fmt: skip
        raise _Step(
            f"the copy of {row.service}'s {row.path} is not the same as the original "
            f"(owner, mode or content): {first}"
        )
    entries = len([line for line in original.splitlines() if line.strip()])
    say(f"  {row.service}: {row.path} copied and checked ({entries} entries, the same owners, "
        "modes and contents).")  # fmt: skip


def _remove(run: Run, made: Sequence[str]) -> str:
    """The named volumes this move filled removed (each was absent or empty before); what could
    not be removed is said."""
    kept = [name for name in made if run(["docker", "volume", "rm", name])[0] != 0]
    if kept:
        return (
            f". The named volumes {', '.join(kept)} hold a partial copy and could not be "
            f"removed; remove them (docker volume rm {' '.join(kept)}) before trying again"
        )
    return ""


def remove_made(run: Run, made: Sequence[str]) -> None:
    """For `update`'s rollback: the named volumes a move made, once the stores are emptied."""
    for name in made:
        run(["docker", "volume", "rm", name])


def _subprocess(argv: Sequence[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(list(argv), capture_output=True, text=True, check=False, timeout=7200)
    except (OSError, subprocess.SubprocessError) as failed:
        return 1, str(failed)
    return done.returncode, (done.stdout + done.stderr).strip()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m harness.store_volumes <deployment>/compose.yaml", file=sys.stderr)
        return 2
    try:
        move(Path(args[0]), run=_subprocess)
    except StoresNotMoved as failed:
        print(f"ospreyflow: {failed.words()}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
