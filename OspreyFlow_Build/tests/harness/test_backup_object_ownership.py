"""`ospreyflow backup` once the object store holds files (ADR-114 Amendment 33, as found on the
first server, 4 November 2026: defect 10).

Found on v0.4.8 with the six demo packs loaded: the object store's export ran in a container of the
Conduit's image as the Conduit's user (uid 10001), into a staging folder in the set; it made the
folders under it as uid 10001, mode 755, and the installer (uid 1001) could not delete the files in
them, so the backup failed at its own clean-up (`PermissionError: [Errno 13] Permission denied:
'ed9c30a1….png'`). The failed-backup clean-up added in v0.4.7 failed for the same reason, silently
(`ignore_errors=True`), said "The partial set … was removed", and left it there. Earlier backups
passed because the store was empty, and Docker Desktop on a Mac hides ownership.

The stand-in Docker here writes as Linux Docker does: as the Conduit's user unless it is told to
run as the caller, and a folder another user made (755) is one the caller cannot write. That last
part is the real filesystem's refusal: such a folder is made `555` to the test's own user, which is
what 755 owned by someone else is to the caller. What a mistake would do, and the case that catches
it:
- the stand-in not refusing as Linux does, so nothing here could go red —
  `test_the_stand_in_refuses_as_linux_does`;
- the export run as the Conduit's user, leaving a copy the installer cannot remove —
  `test_a_store_holding_files_backs_up_and_leaves_nothing_behind`;
- a failed backup's set it cannot remove left looking like a set, and called removed —
  `test_a_partial_set_that_cannot_be_removed_is_said_and_marked_incomplete`, and restore refusing
  it — the same case.
"""

from __future__ import annotations

import json
import os
import subprocess
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from harness import backup, restore

CALLER = f"{os.getuid()}:{os.getgid()}"
OBJECT = "ed9c30a1e6b14d0c9a1f2b3c4d5e6f70.png"

pytestmark = pytest.mark.skipif(
    os.geteuid() == 0, reason="root may remove anything, so no refusal can be stood in"
)


def _as_another_user(folder: Path) -> None:
    """What a folder made by uid 10001 with mode 755 is to the installer: it cannot write it."""
    for path in sorted(folder.rglob("*"), reverse=True):
        if path.is_dir():
            path.chmod(0o555)
    folder.chmod(0o555)


@pytest.fixture(autouse=True)
def writable_again(tmp_path: Path) -> Iterator[None]:
    """pytest removes its folders afterwards; give the test's own user its folders back first."""
    yield
    for path in [tmp_path, *tmp_path.rglob("*")]:
        if path.is_dir() and not path.is_symlink():
            path.chmod(0o755)


class Docker:
    """`docker compose run … api -m services.api.object_transfer export /transfer` as Linux Docker
    runs it: the Conduit's image runs as its own user unless `--user` names another, and what it
    writes into the bind-mounted folder is that user's."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        assert command[-2:] == ["export", "/transfer"], command
        mount = command[command.index("-v") + 1]
        transfer = Path(mount.rsplit(":", 1)[0])
        bucket = transfer / "objects" / "osprey-staging" / "media"
        bucket.mkdir(parents=True)
        (bucket / OBJECT).write_bytes(b"\x89PNG")
        (transfer / "manifest.json").write_text(
            json.dumps({"format": 1, "buckets": ["osprey-staging"], "objects": []})
        )
        user = command[command.index("--user") + 1] if "--user" in command else "10001:10001"
        if user != CALLER:
            _as_another_user(transfer / "objects")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


@pytest.fixture
def compose_file(tmp_path: Path) -> Path:
    out = tmp_path / "deploy" / "small"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {api: {}}\n", encoding="utf-8")
    (out / "deployment.env").write_text("X=1\n", encoding="utf-8")
    return out / "compose.yaml"


def test_the_stand_in_refuses_as_linux_does(tmp_path: Path) -> None:
    """Rule 15: written as the Conduit's user, the copy is one the installer cannot remove."""
    transfer = tmp_path / "transfer"
    transfer.mkdir()
    Docker()(["docker", "compose", "run", "-v", f"{transfer}:/transfer", "api", "export",
              "/transfer"])  # fmt: skip
    with pytest.raises(PermissionError):
        (transfer / "objects" / "osprey-staging" / "media" / OBJECT).unlink()


def test_a_store_holding_files_backs_up_and_leaves_nothing_behind(
    compose_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker = Docker()
    monkeypatch.setattr(backup.subprocess, "run", docker)
    target = tmp_path / "set"
    target.mkdir()

    archive = backup.backup_object_store(
        compose_file, target / "objects" / "data.tar.gz", work_dir=target
    )

    assert sorted(p.name for p in target.iterdir()) == ["objects"], "no staging copy left"
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert f"objects-export/objects/osprey-staging/media/{OBJECT}" in names
    # Run as the installer, so what it writes is the installer's; never into a folder every account
    # may write.
    (command,) = docker.commands
    assert command[command.index("--user") + 1] == CALLER
    with tarfile.open(archive) as tar:
        top = tar.getmember("objects-export")
    assert top.mode & 0o002 == 0


def test_a_partial_set_that_cannot_be_removed_is_said_and_marked_incomplete(
    compose_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clean-up of a failed backup, against a set holding something the installer cannot
    remove (as every v0.4.8 backup of a store with files did): it says so in words, and the folder
    is renamed and marked so neither a person, a restore nor an update takes it for a set."""
    monkeypatch.setattr(backup, "_conduit_is_running", lambda compose_file: False)
    monkeypatch.setattr(backup, "git_sha", lambda: "abc")

    def stuck(compose_file: Path, destination: Path, **_: Any) -> Path:
        left = destination.parent.parent / ".objects-staging" / "objects"
        left.mkdir(parents=True)
        (left / OBJECT).write_bytes(b"\x89PNG")
        _as_another_user(left)
        raise backup.BackupFailed("objects", "the copy was refused")

    for name in ("backup_graph_store", "backup_identity"):
        monkeypatch.setattr(backup, name, lambda c, d, **kw: d)
    monkeypatch.setattr(backup, "backup_postgres_all", lambda c, f: [])
    monkeypatch.setattr(backup, "backup_object_store", stuck)
    sets = tmp_path / "sets"

    with pytest.raises(backup.BackupFailed) as failed:
        backup.run_backup(
            compose_file=compose_file, out_root=sets, profile="small", database="ospreyflow",
            analytics_container_path="/var/lib/osprey/data/analytics.duckdb",
            require_quiesced=False,
        )  # fmt: skip

    said = failed.value.detail
    assert "nothing was kept" not in said
    assert "could not be removed" in said and OBJECT in said and "INCOMPLETE" in said
    (left,) = sets.iterdir()
    assert left.name.endswith(".incomplete")
    assert "incomplete" in (left / "INCOMPLETE").read_text(encoding="utf-8")
    with pytest.raises(restore.RestoreRefused) as refused:
        restore.load_manifest(left)
    assert "incomplete" in str(refused.value)
