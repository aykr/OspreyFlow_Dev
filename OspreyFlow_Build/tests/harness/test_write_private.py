"""`harness.render.write_private` never leaves `deployment.env` half-written (CARRIES, the
orchestrator's review of the upgrade fix, 10 November 2026): it wrote in place (`O_TRUNC`), so a
full disk or a crash mid-write left the deployment's every secret truncated, with no restore. Now a
`600` file beside it is written, flushed to disk, given the old file's owner, and renamed over it.
`deployment.env` is read as an `env_file` when a container is made, never mounted, so its new inode
is what the next container reads.
- `test_a_write_that_fails_part_way_leaves_the_old_file_whole`
- `test_it_is_600_from_the_start_and_leaves_nothing_beside_it`
- `test_the_old_files_owner_is_kept`
"""

from __future__ import annotations

import errno
import io
import os
from pathlib import Path
from typing import Any

import pytest
from harness import render
from harness.render import write_private

OLD = "OSPREY_POSTGRES_PASSWORD=held-for-years\nOSPREY_KEYCLOAK_ADMIN_PASSWORD=also-held\n"


def test_a_write_that_fails_part_way_leaves_the_old_file_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / "deployment.env"
    env.write_text(OLD, encoding="utf-8")
    real_fdopen = os.fdopen

    class FillsUp(io.TextIOWrapper):
        def write(self, text: str) -> int:
            super().write(text[: len(text) // 2])
            self.flush()
            raise OSError(errno.ENOSPC, "No space left on device")

    def fdopen(fd: int, *args: Any, **kwargs: Any) -> io.TextIOWrapper:
        handle = real_fdopen(fd, "wb", buffering=0)
        return FillsUp(handle, encoding="utf-8")  # type: ignore[arg-type]

    monkeypatch.setattr(render.os, "fdopen", fdopen)
    with pytest.raises(OSError, match="No space left"):
        write_private(env, "OSPREY_POSTGRES_PASSWORD=new\n" * 40)
    assert env.read_text(encoding="utf-8") == OLD
    assert sorted(p.name for p in tmp_path.iterdir()) == ["deployment.env"]


def test_it_is_600_from_the_start_and_leaves_nothing_beside_it(tmp_path: Path) -> None:
    env = tmp_path / "deployment.env"
    env.write_text(OLD, encoding="utf-8")
    env.chmod(0o644)
    write_private(env, "X=1\n")
    assert env.read_text(encoding="utf-8") == "X=1\n"
    assert env.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["deployment.env"]
    write_private(tmp_path / "new.env", "Y=2\n")  # a file not there before
    assert (tmp_path / "new.env").stat().st_mode & 0o777 == 0o600


def test_the_old_files_owner_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run under sudo, a rename would leave `deployment.env` root's, and the operator's next
    `ospreyflow` could not read it: the new file takes the old one's owner before the rename."""
    env = tmp_path / "deployment.env"
    env.write_text(OLD, encoding="utf-8")
    old = env.stat()
    given: list[tuple[str, int, int]] = []
    renamed: list[str] = []
    monkeypatch.setattr(render.os, "geteuid", lambda: 0)
    monkeypatch.setattr(render.os, "chown", lambda p, u, g: given.append((Path(p).name, u, g)))
    real_replace = os.replace
    monkeypatch.setattr(
        render.os, "replace", lambda a, b: (renamed.append(Path(a).name), real_replace(a, b))
    )
    write_private(env, "X=1\n")
    assert given and given[0][1:] == (old.st_uid, old.st_gid)
    assert renamed and given[0][0] == renamed[0]  # the new file, before it was renamed
