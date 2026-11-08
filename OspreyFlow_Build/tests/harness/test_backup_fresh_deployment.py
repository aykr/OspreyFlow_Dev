"""`ospreyflow backup` on a deployment nothing has been loaded into yet (ADR-114 Amendment 33, as
found on the first server, 4 November 2026).

Found installing v0.4.6 as Small on an Ubuntu 24.04 server: the first backup failed on 'recipes'
with Docker's own refusal, "Could not find the file /var/lib/osprey/data/recipes in container
osprey-small-api-1", and left its half-written set folder behind. The repository does not exist
until a recipe is published, and the analytics file not until an event is written. The module
looked for "not exist" in the refusal, which Docker never says; the stand-in it was tested against
said "does not exist", so the test passed against a refusal no real Docker gives (rule 15).

The stand-in here answers a `cp` of a missing path as Docker does: exit 1, and "Error response from
daemon: Could not find the file <path> in container <name>". What a mistake would do, and the case
that catches it:
- the first backup of a fresh deployment refused for a folder that is legitimately absent —
  `test_a_fresh_deployment_backs_up_with_no_recipes_and_no_analytics_file`;
- a different `cp` failure (Docker cannot reach the container) taken for an empty folder —
  `test_any_other_cp_failure_still_fails_the_backup`;
- a failed backup's half-written set left beside the good ones —
  `test_a_failed_backup_leaves_no_partial_set_behind`;
- a set with an empty item restored as though it were missing, or the restore trying to copy it —
  `test_a_set_with_empty_items_restores_without_them_and_says_so`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from harness import backup, restore

CONTAINER = "osprey-small-api-1"
ENV = "POSTGRES_USER=osprey\nPOSTGRES_DB=ospreyflow\n"


def docker_cp_of(present: set[str]) -> Any:
    """`docker compose cp api:<path> <dest>` as Docker answers it: the paths in `present` are
    copied, any other is refused with the daemon's own words and a non-zero exit."""

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "exec" in command and any("model-settings/models.yaml" in w for w in command):
            # ADR-135 Amendment 2: a fresh deployment's Conduit holds no models file yet.
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        assert "cp" in command, command
        source, target = command[-2], Path(command[-1])
        path = source.partition(":")[2]
        if path not in present:
            return subprocess.CompletedProcess(
                command, 1, stdout="",
                stderr=f"Error response from daemon: Could not find the file {path} in container "
                f"{CONTAINER}\n",
            )  # fmt: skip
        if path.endswith(".duckdb"):
            target.write_bytes(b"duck")
        else:
            (target / ".git").mkdir(parents=True)
            (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    return run


@pytest.fixture
def compose_file(tmp_path: Path) -> Path:
    out = tmp_path / "deploy" / "small"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text(ENV, encoding="utf-8")
    return out / "compose.yaml"


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def _other_stores_faked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backup, "_conduit_is_running", lambda compose_file: False)
    monkeypatch.setattr(backup, "git_sha", lambda: "abc")
    monkeypatch.setattr(backup, "schema_versions", lambda: {"ontology": "13"})
    monkeypatch.setattr(backup, "CONFIGURATION_SOURCES", ())
    monkeypatch.setattr(backup, "backup_graph_store", lambda c, d, **kw: _touch(d))
    monkeypatch.setattr(
        backup, "backup_postgres_all", lambda c, f: [("postgres", _touch(f / "dump.sql"))]
    )
    monkeypatch.setattr(backup, "backup_identity", lambda c, d: _touch(d))
    monkeypatch.setattr(backup, "backup_object_store", lambda c, d, **kw: _touch(d))


def _backup(compose_file: Path, out_root: Path) -> Path:
    return backup.run_backup(
        compose_file=compose_file, out_root=out_root, profile="small", database="ospreyflow",
        analytics_container_path="/var/lib/osprey/data/analytics.duckdb", require_quiesced=False,
    )  # fmt: skip


def test_a_fresh_deployment_backs_up_with_no_recipes_and_no_analytics_file(
    compose_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _other_stores_faked(monkeypatch)
    monkeypatch.setattr(backup.subprocess, "run", docker_cp_of(set()))

    target = _backup(compose_file, tmp_path / "sets")

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    items = {entry["item"] for entry in manifest["files"]}
    assert not items & {"recipes", "analytics"}
    assert manifest["empty"] == ["analytics", "recipes"], "the set says which items were empty"
    assert not (target / ".recipes-staging").exists()


def test_a_present_recipes_folder_is_still_carried(
    compose_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _other_stores_faked(monkeypatch)
    present = {"/var/lib/osprey/data/recipes", "/var/lib/osprey/data/analytics.duckdb"}
    monkeypatch.setattr(backup.subprocess, "run", docker_cp_of(present))

    manifest = json.loads((_backup(compose_file, tmp_path / "sets") / "manifest.json").read_text())

    assert {"recipes", "analytics"} <= {entry["item"] for entry in manifest["files"]}
    assert manifest["empty"] == []


@pytest.mark.parametrize("item", ["analytics", "recipes"])
def test_any_other_cp_failure_still_fails_the_backup(
    item: str, compose_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 1, stdout="", stderr='service "api" is not running\n'
        )

    monkeypatch.setattr(backup.subprocess, "run", unreachable)
    with pytest.raises(backup.BackupFailed) as failed:
        if item == "analytics":
            backup.backup_analytics(
                compose_file, tmp_path / "a.duckdb", container_path="/var/lib/osprey/data/a"
            )
        else:
            backup.backup_recipes(
                compose_file, tmp_path / "r.tar.gz", container_path="/var/lib/osprey/data/r",
                work_dir=tmp_path,
            )  # fmt: skip
    assert failed.value.item == item and "not running" in failed.value.detail


def test_a_failed_backup_leaves_no_partial_set_behind(
    compose_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _other_stores_faked(monkeypatch)
    monkeypatch.setattr(backup.subprocess, "run", docker_cp_of(set()))

    def refused(compose_file: Path, destination: Path) -> Path:
        raise backup.BackupFailed("identity", "the identity provider refused the admin token")

    monkeypatch.setattr(backup, "backup_identity", refused)
    sets = tmp_path / "sets"
    with pytest.raises(backup.BackupFailed) as failed:
        _backup(compose_file, sets)
    assert list(sets.iterdir()) == [], "nothing a restore or an update could take for a set"
    assert "nothing was kept" in failed.value.detail


def test_a_set_with_empty_items_restores_without_them_and_says_so(
    compose_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _other_stores_faked(monkeypatch)
    monkeypatch.setattr(backup.subprocess, "run", docker_cp_of(set()))
    target = _backup(compose_file, tmp_path / "sets")

    monkeypatch.setattr(restore, "check_schema_compatibility", lambda manifest: None)
    monkeypatch.setattr(restore, "graph_store_is_empty", lambda c, **kw: True)
    called: list[str] = []
    for name in ("restore_graph_store", "restore_postgres_all", "restore_object_store",
                 "restore_analytics", "restore_recipes", "restore_identity"):  # fmt: skip
        monkeypatch.setattr(restore, name, lambda *a, _n=name, **kw: called.append(_n))
    plan = restore.run_restore(
        directory=target, compose_file=compose_file, database="ospreyflow",
        analytics_container_path="/var/lib/osprey/data/analytics.duckdb", acknowledged=True,
    )  # fmt: skip

    assert "restore_recipes" not in called and "restore_analytics" not in called
    assert plan.empty == ("analytics", "recipes")
    assert "analytics, recipes: empty when the set was taken" in plan.render()
