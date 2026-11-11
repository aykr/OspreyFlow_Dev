"""A file replaced whole or not at all (CARRIES, 10 November 2026; ADR-114 Amendment 39 decision 5:
"an interruption leaves whole files and the secrets as they were").

`replace_whole` is the one way a deployment's secrets file reaches its place, from `apply`, `restore`'s
put-back, refresh and `write_private`. It writes a temporary file beside the real target, sets its mode
before any byte, flushes it to disk, gives it the old file's owner when run as root (a run under sudo
leaves it the operator's), renames it over the target and flushes the folder. **A symlink is followed**:
the link stays a link and its target is replaced, so an operator's linked `deployment.env` is neither
turned into a regular file nor written in place. A failure at any point leaves the old file whole and
no temporary file.

Not for a file a container mounts on its own (`./glass.json:…`): a rename gives it a new inode, which
the running container would not see. Those are written in place, and hold no secret.
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


def _as_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _fsync_folder(folder: Path) -> None:
    """The rename itself made durable; a platform with no folder handles (Windows) skips it."""
    try:
        descriptor = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _owner_of(target: Path) -> tuple[int, int]:
    held = target.stat()
    return held.st_uid, held.st_gid


def replace_whole(path: Path, data: bytes, *, mode: int | None = None) -> None:
    """`data` into `path` whole or not at all. `mode`: the file's mode (default: the old file's, else
    `644`). The old file's owner is kept when run as root."""
    target = path.resolve() if path.is_symlink() else path
    folder = target.parent
    old = target.stat() if target.exists() else None
    wanted = mode if mode is not None else (stat.S_IMODE(old.st_mode) if old else 0o644)
    owner = _owner_of(target) if old is not None and _as_root() else None
    descriptor, staged = tempfile.mkstemp(dir=folder, prefix=f".{target.name}.", suffix=".writing")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), wanted)
            if owner is not None:
                os.fchown(handle.fileno(), *owner)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, target)
    except BaseException:
        Path(staged).unlink(missing_ok=True)
        raise
    _fsync_folder(folder)
