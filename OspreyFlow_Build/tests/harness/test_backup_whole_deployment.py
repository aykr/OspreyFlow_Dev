"""The backup carries the whole deployment (`06_DECISIONS.md` ADR-114 Amendment 3, B2e): every Postgres
database — the dashboards' own `superset` beside `ospreyflow` — with the roles they grant to, and the
realm's people and dashboard identities with their ids; the restore brings each back in an order a
fresh server accepts.

Found before this was written: the backup dumped one database, so a restore would have lost every
Superset dashboard; and Keycloak runs with no persistent store, so no backup held anyone's account —
restoring the cases without the people who hold their grants locks everyone out.

What a mistake would do, and the case that catches it:
- a database left out of the set — `test_every_database_is_dumped_and_the_roles_with_them`;
- a database that dumped nothing passed as a backup — `test_an_empty_dump_of_any_database_is_refused`;
- the identity file readable by anyone, or the dashboards' setting lost —
  `test_the_identity_item_is_the_owners_alone_and_carries_report_syncs_dashboards`;
- a restore refused by a fresh server for a missing role or database —
  `test_restore_replays_roles_first_and_creates_a_missing_database`;
- the people not brought back, or their passwords not set again —
  `test_restore_brings_the_identity_back_and_sets_the_dashboards_setting`.
"""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
from harness import backup, restore

ENV = (
    "POSTGRES_USER=osprey\nPOSTGRES_DB=ospreyflow\nOSPREY_KEYCLOAK_PORT=8081\n"
    "OSPREY_KEYCLOAK_ADMIN_PASSWORD=kc-admin-secret\n"
    'REPORT_SYNC_DASHBOARDS=[{"client_id": "osprey-dashboard-c", "secret": "s", "weeks": 12}]\n'
)


@pytest.fixture
def deployment(tmp_path: Path) -> Path:
    out = tmp_path / "deploy" / "local-lite"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text(ENV, encoding="utf-8")
    return out / "compose.yaml"


def _fake_postgres(databases: dict[str, str], seen: list[list[str]]) -> Any:
    def run(command: list[str], *, item: str, capture: bool = True) -> str:
        seen.append(command)
        tail = command[command.index("postgres") + 1 :] if "postgres" in command else command
        if tail[:1] == ["pg_dumpall"]:
            return "CREATE ROLE osprey_reports_reader;\n"
        if tail[:1] == ["psql"]:
            return "\n".join(databases) + "\n"
        if tail[:1] == ["pg_dump"]:
            return databases[tail[-1]]
        raise AssertionError(command)

    return run


def test_every_database_is_dumped_and_the_roles_with_them(deployment: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    dbs = {"ospreyflow": "CREATE TABLE investigations ();\n", "superset": "CREATE TABLE dashboards ();\n"}
    monkeypatch.setattr(backup, "_run", _fake_postgres(dbs, seen))
    written = backup.backup_postgres_all(deployment, deployment.parent / "set" / "postgres")
    assert sorted(p.name for _item, p in written) == ["dump.sql", "roles.sql", "superset.sql"]
    assert {item for item, _p in written} == {"postgres", "postgres-roles"}
    assert (deployment.parent / "set" / "postgres" / "superset.sql").read_text() == dbs["superset"]


def test_an_empty_dump_of_any_database_is_refused(deployment: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dbs = {"ospreyflow": "CREATE TABLE investigations ();\n", "superset": "-- nothing\n"}
    monkeypatch.setattr(backup, "_run", _fake_postgres(dbs, []))
    with pytest.raises(backup.BackupFailed, match="superset"):
        backup.backup_postgres_all(deployment, deployment.parent / "set" / "postgres")


def test_the_identity_item_is_the_owners_alone_and_carries_report_syncs_dashboards(
    deployment: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: dict[str, str] = {}

    def token(*, issuer: str, admin_user: str, admin_password: str) -> str:
        asked.update(issuer=issuer, password=admin_password)
        return "t"

    monkeypatch.setattr(backup.keycloak_admin, "admin_token", token)
    monkeypatch.setattr(backup.identity, "export_identity",
                        lambda **kw: {"format": 1, "realm": kw["realm"], "people": [], "dashboards": []})  # fmt: skip
    path = backup.backup_identity(deployment, deployment.parent / "set" / "identity" / "realm.json")
    assert asked == {"issuer": "http://127.0.0.1:8081", "password": "kc-admin-secret"}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    held = json.loads(path.read_text(encoding="utf-8"))
    assert held["realm"] == "osprey"
    assert json.loads(held["report_sync_dashboards"])[0]["client_id"] == "osprey-dashboard-c"


def test_restore_replays_roles_first_and_creates_a_missing_database(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        stdin = kwargs.get("stdin")
        calls.append((command, stdin.read().decode() if stdin else kwargs.get("input") or ""))
        out = "ospreyflow\n" if "-Atc" in command else ""
        return subprocess.CompletedProcess(command, 0, stdout=out, stderr="")

    monkeypatch.setattr(restore.subprocess, "run", run)
    folder = tmp_path / "set" / "postgres"
    folder.mkdir(parents=True)
    (folder / "roles.sql").write_text("CREATE ROLE osprey_reports_reader;\n", encoding="utf-8")
    (folder / "dump.sql").write_text("CREATE TABLE investigations ();\n", encoding="utf-8")
    (folder / "superset.sql").write_text("CREATE TABLE dashboards ();\n", encoding="utf-8")
    restore.restore_postgres_all(deployment, [folder / "dump.sql", folder / "superset.sql"], folder / "roles.sql")
    sent = [body for _c, body in calls]
    assert sent[0].startswith("CREATE ROLE"), "roles before any database"
    created = [c for c, _b in calls if any("CREATE DATABASE" in part for part in c)]
    assert len(created) == 1 and any('"superset"' in part for part in created[0])
    targets = [c[-1] for c, body in calls if body.startswith("CREATE TABLE")]
    assert targets == ["ospreyflow", "superset"]


def test_restore_brings_the_identity_back_and_sets_the_dashboards_setting(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    imported: list[dict[str, Any]] = []
    registered: list[Path] = []
    monkeypatch.setattr(restore.keycloak_admin, "admin_token", lambda **kw: "t")
    monkeypatch.setattr(restore.identity, "import_identity",
                        lambda **kw: imported.append(kw["identity"]) or {"people": 4, "dashboards": 1, "replaced": 4})  # fmt: skip
    monkeypatch.setattr(restore, "_register_sign_in", lambda env_path: registered.append(env_path))
    env = deployment.parent / "deployment.env"
    env.write_text("POSTGRES_USER=osprey\nOSPREY_KEYCLOAK_ADMIN_PASSWORD=new\nREPORT_SYNC_DASHBOARDS=[]\n",
                   encoding="utf-8")  # fmt: skip
    held = tmp_path / "realm.json"
    held.write_text(json.dumps({"format": 1, "realm": "osprey", "people": [], "dashboards": [],
                                "report_sync_dashboards": '[{"client_id": "osprey-dashboard-c"}]'}),
                    encoding="utf-8")  # fmt: skip
    summary = restore.restore_identity(deployment, held)
    assert summary["people"] == 4 and imported and registered == [env]
    lines = env.read_text(encoding="utf-8").splitlines()
    assert 'REPORT_SYNC_DASHBOARDS=[{"client_id": "osprey-dashboard-c"}]' in lines
    assert sum(line.startswith("REPORT_SYNC_DASHBOARDS=") for line in lines) == 1
