"""Backup and restore of the object store at the S3 level (ADR-114 Amendment 9 point 3a).

The commands are recorded rather than run: what matters here is that the export and import go
through the Conduit's image inside the deployment's network, never through a store's own data
folder, and that a MinIO-format backup restored into SeaweedFS is refused rather than copied in
wrongly. The transfer itself is proved against real stores (`test_object_transfer.py`, and the
MinIO-to-SeaweedFS rehearsal recorded in `07_BUILD_PLAN.md`).
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
import yaml
from harness import backup, restore


def _deployment(tmp_path: Path, services: dict[str, object]) -> Path:
    out = tmp_path / "deploy" / "local-lite"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text(yaml.safe_dump({"services": services}))
    (out / "deployment.env").write_text("X=1\n")
    return out / "compose.yaml"


def test_the_backup_exports_through_the_conduits_image_not_a_data_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compose = _deployment(tmp_path, {"objectstore": {}, "api": {}})
    ran: list[list[str]] = []

    def run(command: list[str], **_: object) -> str:
        ran.append(command)
        transfer = Path(command[command.index("-v") + 1].split(":")[0])
        (transfer / "objects" / "b").mkdir(parents=True)
        (transfer / "objects" / "b" / "k").write_bytes(b"x")
        (transfer / "manifest.json").write_text(json.dumps({"format": 1, "buckets": ["b"],
                                                           "objects": []}))  # fmt: skip
        return ""

    monkeypatch.setattr(backup, "_run", run)
    archive = backup.backup_object_store(compose, tmp_path / "set" / "objects.tar.gz",
                                         work_dir=tmp_path / "set")  # fmt: skip
    (command,) = ran
    tail = command[command.index("run") :]
    assert tail[:4] == ["run", "--rm", "--no-deps", "--entrypoint"]
    assert tail[4] == "python"
    assert command[-5:] == ["api", "-m", "services.api.object_transfer", "export", "/transfer"]
    assert not any("minio:/data" in part or "objectstore:/data" in part for part in command)
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert "objects-export/manifest.json" in names and "objects-export/objects/b/k" in names


def _archive(tmp_path: Path, members: dict[str, bytes]) -> Path:
    import io

    path = tmp_path / "objects.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_the_restore_imports_through_the_conduits_image_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compose = _deployment(tmp_path, {"objectstore": {}, "api": {}})
    ran: list[list[str]] = []
    monkeypatch.setattr(restore, "_run", lambda command, **_: ran.append(command) or "")
    archive = _archive(tmp_path, {"objects-export/manifest.json": b'{"format": 1}'})
    restore.restore_object_store(compose, archive, work_dir=tmp_path / "work")
    (command,) = ran
    mount = command[command.index("-v") + 1]
    assert mount.endswith(":/transfer:ro")
    assert command[-5:] == ["api", "-m", "services.api.object_transfer", "import", "/transfer"]


def test_a_minio_format_backup_restored_into_seaweedfs_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compose = _deployment(tmp_path, {"objectstore": {}, "api": {}})
    monkeypatch.setattr(restore, "_run", lambda command, **_: pytest.fail("nothing may run"))
    archive = _archive(tmp_path, {"data/.minio.sys/format.json": b"{}"})
    with pytest.raises(restore.RestoreRefused, match="MinIO's own format"):
        restore.restore_object_store(compose, archive, work_dir=tmp_path / "work")


def test_a_minio_format_backup_still_restores_into_minio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backup taken before this change restores into a deployment of that version, as before."""
    compose = _deployment(tmp_path, {"minio": {}, "api": {}})
    ran: list[list[str]] = []
    monkeypatch.setattr(restore, "_run", lambda command, **_: ran.append(command) or "")
    archive = _archive(tmp_path, {"data/.minio.sys/format.json": b"{}"})
    restore.restore_object_store(compose, archive, work_dir=tmp_path / "work")
    assert ran[0][-1] == "minio:/data"


def test_a_minio_backup_is_put_back_at_the_level_it_was_taken_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old backup copied `minio:/data` into a staging folder that already existed, so `docker
    cp` made `staging/data`, and then tarred the staging folder as `data`: every such archive holds
    `data/data/…`. Copied back as it was, each restore buried the buckets one level deeper, out of
    the application's sight (found migrating the owner's deployment, 13 October 2026: three restores
    deep)."""
    compose = _deployment(tmp_path, {"minio": {}, "api": {}})
    ran: list[list[str]] = []
    monkeypatch.setattr(restore, "_run", lambda command, **_: ran.append(command) or "")
    archive = _archive(tmp_path, {"data/data/.minio.sys/format.json": b"{}",
                                  "data/data/ospreyflow-media/a/xl.meta": b"x"})  # fmt: skip
    restore.restore_object_store(compose, archive, work_dir=tmp_path / "work")
    source, target = ran[0][-2:]
    assert target == "minio:/data"
    assert source.endswith("restore-objects/data/data/.")
