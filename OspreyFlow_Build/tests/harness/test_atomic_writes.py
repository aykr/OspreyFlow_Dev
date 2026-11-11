"""A deployment's secrets file replaced whole or not at all, at every place that writes it
(`harness/atomic.py`; CARRIES, 10 November 2026; ADR-114 Amendment 39 decision 5).

What a mistake would do, and the case that catches it (rule 12), each planted at its call site:
- a write that truncates and rewrites the live file (`copytree`, `write_bytes`, `O_TRUNC`): a crash
  part way leaves torn secrets — the hard-link cases (a link made to the old file still holds the old
  bytes only if the file was replaced, not rewritten) for `apply.move_into_place`, `write_private`
  and `FilesHeld.put_back`;
- a symlinked `deployment.env` turned into a regular file, or written in place —
  `test_a_symlinked_file_stays_a_link_and_its_target_is_replaced`;
- the owner taken from the runner or the new file rather than the old one, under sudo —
  `test_under_sudo_the_old_file_s_owner_is_kept` (the old file given an owner the runner is not);
- a failure part way leaving a torn file or a temporary file holding secrets —
  `test_a_failure_part_way_leaves_the_old_file_whole_and_nothing_beside_it`.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from harness import atomic
from harness.apply import move_into_place
from harness.render import write_private
from harness.store_volumes import FilesHeld

OLD = b"OSPREY_POSTGRES_PASSWORD=old-secret\n"
NEW = b"OSPREY_POSTGRES_PASSWORD=new-secret\n"


def _kept_link(path: Path) -> Path:
    """A second name for the file as it is now: if the file is later rewritten in place, this
    name sees the new bytes; if it is replaced, it keeps the old."""
    link = path.with_name(path.name + ".old-inode")
    os.link(path, link)
    return link


def test_a_symlinked_file_stays_a_link_and_its_target_is_replaced(tmp_path: Path) -> None:
    real = tmp_path / "elsewhere" / "deployment.env"
    real.parent.mkdir()
    real.write_bytes(OLD)
    link = tmp_path / "deployment.env"
    link.symlink_to(real)
    before = _kept_link(real)
    atomic.replace_whole(link, NEW, mode=0o600)
    assert link.is_symlink() and link.resolve() == real
    assert real.read_bytes() == NEW and before.read_bytes() == OLD
    assert stat.S_IMODE(real.stat().st_mode) == 0o600


def test_write_private_keeps_a_symlink_a_link(tmp_path: Path) -> None:
    real = tmp_path / "real.env"
    real.write_bytes(OLD)
    link = tmp_path / "deployment.env"
    link.symlink_to(real)
    write_private(link, NEW.decode())
    assert link.is_symlink() and real.read_bytes() == NEW


def test_under_sudo_the_old_file_s_owner_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "deployment.env"
    path.write_bytes(OLD)
    given: list[tuple[int, int]] = []
    monkeypatch.setattr(atomic, "_as_root", lambda: True)
    # The old file is the operator's (4242), not the runner's (root, or this test's own user).
    monkeypatch.setattr(atomic, "_owner_of", lambda _target: (4242, 4343))
    monkeypatch.setattr(atomic.os, "fchown", lambda _fd, uid, gid: given.append((uid, gid)))
    atomic.replace_whole(path, NEW, mode=0o600)
    assert given == [(4242, 4343)]


def test_a_failure_part_way_leaves_the_old_file_whole_and_nothing_beside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "deployment.env"
    path.write_bytes(OLD)

    def disk_full(_fd: int) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(atomic.os, "fsync", disk_full)
    with pytest.raises(OSError):
        atomic.replace_whole(path, NEW, mode=0o600)
    assert path.read_bytes() == OLD
    assert sorted(p.name for p in tmp_path.iterdir()) == ["deployment.env"]


def test_write_private_replaces_rather_than_rewrites(tmp_path: Path) -> None:
    path = tmp_path / "deployment.env"
    path.write_bytes(OLD)
    before = _kept_link(path)
    write_private(path, NEW.decode())
    assert path.read_bytes() == NEW and before.read_bytes() == OLD


def test_apply_s_move_into_place_replaces_deployment_env_rather_than_rewriting_it(
    tmp_path: Path,
) -> None:
    out, stage = tmp_path / "deployment", tmp_path / "stage"
    out.mkdir()
    stage.mkdir()
    (out / "deployment.env").write_bytes(OLD)
    (out / "deployment.env").chmod(0o600)
    before = _kept_link(out / "deployment.env")
    (stage / "deployment.env").write_bytes(NEW)
    (stage / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    move_into_place(stage, out)
    assert (out / "deployment.env").read_bytes() == NEW and before.read_bytes() == OLD
    assert stat.S_IMODE((out / "deployment.env").stat().st_mode) == 0o600
    assert (out / "compose.yaml").read_text(encoding="utf-8") == "services: {}\n"


def test_put_back_replaces_deployment_env_rather_than_rewriting_it(tmp_path: Path) -> None:
    folder = tmp_path / "deployment"
    folder.mkdir()
    (folder / "deployment.env").write_bytes(OLD)
    held = FilesHeld(folder)
    (folder / "deployment.env").write_bytes(NEW)
    before = tmp_path / "witness"  # outside the folder, which put_back clears of what it did not hold
    os.link(folder / "deployment.env", before)
    held.put_back()
    assert (folder / "deployment.env").read_bytes() == OLD and before.read_bytes() == NEW
