"""The Ingest Studio's upload folder made writable by the Conduit before the stack starts (ADR-114
Amendment 33, "as found on the first server, 4 November 2026").

    PYTHONPATH=.:packages python -m harness.ingest_uploads <deployment>/compose.yaml

The renderer bind-mounts `<components.storage.ingest>/uploaded` into the Conduit, writable, over
the read-only ingest root (ADR-067). Nothing made that folder, so Docker made it at the first `up`,
owned by root and `755`; the Conduit runs as `osprey` (`CONDUIT_USER`), so on Linux every upload,
and every demo pack that writes its files there, was refused (`PermissionError: [Errno 13]`). Docker
Desktop on a Mac or Windows lets a container's user write a shared folder whoever owns it, which is
why it never showed there.

So before every `up` (`harness.apply` for install and `ospreyflow apply`, `scripts.refresh` for
`start --build`, `harness.update`, and the `ospreyflow` command's `start` and `switch`), this makes
the folder and, when the Conduit cannot write it, gives it to the Conduit's user: a one-off
container of the Conduit's own image, as root — the way `harness.restore` hands a restored file back
to the Conduit, so there is no further image to pin or trust. Ownership is changed only when the
Conduit cannot write the folder, so an operator's own arrangement (a group of the Conduit's, say)
stays. The folder is never made writable by every account.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import yaml

from harness.render import INGEST_CONTAINER_PATH, INGEST_UPLOAD_SUBDIR

#: **The Conduit's user, as `services/api/Dockerfile` makes it**: `useradd --create-home --uid 10001
#: osprey`, which also makes the group `osprey`, 10001 (checked with `docker exec … id` on the first
#: server, 4 November 2026). `test_ingest_uploads.py` fails if the Dockerfile's uid moves.
CONDUIT_USER = (10001, 10001)

#: Where the Conduit sees the upload folder.
UPLOAD_CONTAINER_PATH = f"{INGEST_CONTAINER_PATH}/{INGEST_UPLOAD_SUBDIR}"

#: Docker Engine on Linux enforces the host folder's owner and mode on a container's user; Docker
#: Desktop's file sharing (macOS, Windows) does not, so there nothing is done, as before.
DOCKER_ENFORCES_OWNERSHIP = sys.platform.startswith("linux")

#: The filesystem, as this module reads and writes it (a test stands in a Linux one).
_stat: Callable[[Path], os.stat_result] = os.stat


def _make(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)


#: `(exit code, what it said)` for a command.
Run = Callable[[Sequence[str]], tuple[int, str]]


class UploadFolderRefused(Exception):
    """The Conduit cannot write the upload folder and it could not be given to it."""


def _compose_argv(compose_file: Path) -> list[str]:
    return [
        "docker", "compose", "--env-file", str(compose_file.parent / "deployment.env"),
        "-f", str(compose_file),
    ]  # fmt: skip


def upload_folder(compose_file: Path) -> Path | None:
    """The host folder the rendered Conduit mounts at `UPLOAD_CONTAINER_PATH`, read as Compose reads
    a bind source (a relative one from the compose file's folder); `None` when it mounts none, or
    when there is no compose file (the `up` after this then says so by name)."""
    if not compose_file.is_file():
        return None
    document = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
    api = (document.get("services") or {}).get("api")
    if not isinstance(api, dict):
        return None
    for volume in api.get("volumes") or []:
        source, target = _bind(volume)
        if target == UPLOAD_CONTAINER_PATH and source:
            return Path(os.path.normpath(compose_file.parent / source))
    return None


def _bind(volume: Any) -> tuple[str, str]:
    if isinstance(volume, dict):
        return str(volume.get("source", "")), str(volume.get("target", ""))
    parts = str(volume).split(":")
    return (parts[0], parts[1]) if len(parts) >= 2 else ("", "")


def conduit_can_write(found: os.stat_result) -> bool:
    """Whether the Conduit's user may make files in a folder, as Linux decides it: the owner's bits
    if it owns the folder, else the group's if the folder is its group's, else everyone's."""
    uid, gid = CONDUIT_USER
    mode = found.st_mode
    if not stat.S_ISDIR(mode):
        return False
    if found.st_uid == uid:
        wanted = stat.S_IWUSR | stat.S_IXUSR
    elif found.st_gid == gid:
        wanted = stat.S_IWGRP | stat.S_IXGRP
    else:
        wanted = stat.S_IWOTH | stat.S_IXOTH
    return mode & wanted == wanted


def give_to_conduit_argv(compose_file: Path) -> list[str]:
    """A one-off container of the deployment's own Conduit image, as root, with the Conduit's own
    mounts, changing the upload folder's owner and nothing else. `--no-deps` starts nothing more."""
    uid, gid = CONDUIT_USER
    return _compose_argv(compose_file) + [
        "run", "--rm", "--no-deps", "--user", "0", "--entrypoint", "chown", "api",
        f"{uid}:{gid}", UPLOAD_CONTAINER_PATH,
    ]  # fmt: skip


def prepare(compose_file: Path, *, run: Run) -> str:
    """Make the upload folder writable by the Conduit, or raise `UploadFolderRefused` saying why and
    what to do. Returns what was done, for the caller's record."""
    folder = upload_folder(compose_file)
    if folder is None:
        return "the Conduit mounts no upload folder"
    if not DOCKER_ENFORCES_OWNERSHIP:
        return f"{folder}: Docker here lets the Conduit write it whoever owns it"
    try:
        _make(folder)
    except OSError:
        # The folder's parent is not this account's to write. The one-off container below mounts
        # it, so Docker makes it (as root, as `up` would have) and the container gives it over.
        pass
    try:
        found: os.stat_result | None = _stat(folder)
    except OSError:  # not there yet, or behind a folder this account may not enter
        found = None
    if found is not None and conduit_can_write(found):
        return f"{folder}: the Conduit can already write it"
    code, said = run(give_to_conduit_argv(compose_file))
    if code != 0:
        uid, gid = CONDUIT_USER
        raise UploadFolderRefused(
            f"the Conduit (uid {uid}) cannot write {folder}, where the Ingest Studio's uploads and "
            f"the demo packs' files go, and giving it to the Conduit failed: "
            f"{said.strip() or f'exit {code}'}. Nothing was started. Give it to the Conduit "
            f"yourself (sudo mkdir -p {folder} && sudo chown {uid}:{gid} {folder}) and run this "
            "again."
        )
    return f"{folder}: given to the Conduit (uid {CONDUIT_USER[0]})"


def _subprocess(argv: Sequence[str]) -> tuple[int, str]:
    done = subprocess.run(list(argv), capture_output=True, text=True, check=False)
    return done.returncode, (done.stderr or done.stdout)


def main(argv: Sequence[str] | None = None, *, run: Run = _subprocess) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m harness.ingest_uploads <deployment>/compose.yaml", file=sys.stderr)
        return 2
    try:
        prepare(Path(args[0]), run=run)
    except UploadFolderRefused as refused:
        print(f"ospreyflow: {refused}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
