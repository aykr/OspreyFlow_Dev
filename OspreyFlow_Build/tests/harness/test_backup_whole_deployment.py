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
- the identity file readable by anyone, or the dashboards' setting or Superset's key lost —
  `test_the_identity_item_is_the_owners_alone_and_carries_report_syncs_dashboards`;
- a restore refused by a fresh server for a missing role or database, or one that puts the old
  deployment's role passwords over the new one's (found at B2e: the Conduit and Superset were
  refused at sign-in) — `test_restore_replays_roles_first_and_creates_a_missing_database` and
  `test_every_database_is_dumped_and_the_roles_with_them`;
- Superset's dump loaded over the schema the fresh install's Superset made for itself, which a
  `--clean` dump cannot clear because it drops only what it made (found at B4's replacement:
  Superset 6.1 built fresh has `slices_table_id_fkey`, the same revision reached by upgrading from
  4.1 has not, and `DROP CONSTRAINT tables_pkey` was refused) —
  `test_a_database_the_fresh_install_made_is_replaced_whole_before_its_dump_is_loaded`;
- the people not brought back, or their passwords not set again —
  `test_restore_brings_the_identity_back_and_sets_the_dashboards_setting`.

Found taking the owner's backup before the replacement: the data volume holds the Ingest Studio's
published-recipes repository (`<data>/recipes`, a git repository) beside the analytics file, and no
item carried it; and `docker cp` into a container leaves a file owned by the host's user, so a
restored analytics file was read-only to the Conduit, which runs as `osprey`:
- the recipes repository left out of the set — `test_the_published_recipes_repository_is_in_the_set`
  and `test_the_set_names_the_recipes_item`;
- a restored file the Conduit cannot write — `test_restored_files_are_handed_to_the_conduits_user`.
"""

from __future__ import annotations

import json
import stat
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import pytest
from harness import backup, restore

ENV = (
    "POSTGRES_USER=osprey\nPOSTGRES_DB=ospreyflow\nOSPREY_KEYCLOAK_PORT=8081\n"
    "OSPREY_KEYCLOAK_ADMIN_PASSWORD=kc-admin-secret\n"
    'REPORT_SYNC_DASHBOARDS=[{"client_id": "osprey-dashboard-c", "secret": "s", "weeks": 12}]\n'
    "SUPERSET_SECRET_KEY=old-superset-key\n"
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
            assert "--no-role-passwords" in tail, "a role's password belongs to the deployment"
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
    # Superset encrypts fields of its own database with this key; restored under a fresh install's
    # new key it could not read them ("Invalid decryption key", found at B2e).
    assert held["superset_secret_key"] == "old-superset-key"


def test_restore_replays_roles_first_and_creates_a_missing_database(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        stdin = kwargs.get("stdin")
        if stdin is not None:
            # What the real `subprocess.run` does with a stdin it is given: asks for its file
            # descriptor. An in-memory buffer has none (`io.UnsupportedOperation: fileno`), which is
            # how the first live restore failed at B2e while this fake read the buffer happily.
            stdin.fileno()
        body = stdin.read() if stdin is not None else kwargs.get("input") or b""
        calls.append((command, body.decode() if isinstance(body, bytes) else body))
        out = "ospreyflow\n" if "-Atc" in command else ""
        return subprocess.CompletedProcess(command, 0, stdout=out, stderr="")

    monkeypatch.setattr(restore.subprocess, "run", run)
    folder = tmp_path / "set" / "postgres"
    folder.mkdir(parents=True)
    (folder / "roles.sql").write_text(
        "CREATE ROLE osprey_reports_reader;\n"
        "ALTER ROLE osprey_reports_reader WITH NOSUPERUSER LOGIN PASSWORD 'SCRAM-SHA-256$4096:old';\n"
        "ALTER ROLE osprey WITH SUPERUSER LOGIN PASSWORD 'md5old';\n",
        encoding="utf-8",
    )
    (folder / "dump.sql").write_text("CREATE TABLE investigations ();\n", encoding="utf-8")
    (folder / "superset.sql").write_text("CREATE TABLE dashboards ();\n", encoding="utf-8")
    restore.restore_postgres_all(deployment, [folder / "dump.sql", folder / "superset.sql"], folder / "roles.sql")
    sent = [body for _c, body in calls]
    assert sent[0].startswith("CREATE ROLE"), "roles before any database"
    # Found at B2e: replaying the old hashes locked the Conduit and Superset out of the fresh
    # server, whose passwords are the new deployment.env's.
    assert "PASSWORD" not in sent[0] and "old" not in sent[0]
    assert "ALTER ROLE osprey_reports_reader WITH NOSUPERUSER LOGIN" in sent[0], "the rest kept"
    created = [c for c, _b in calls if any("CREATE DATABASE" in part for part in c)]
    assert len(created) == 1 and any('"superset"' in part for part in created[0])
    targets = [c[-1] for c, body in calls if body.startswith("CREATE TABLE")]
    assert targets == ["ospreyflow", "superset"]


def test_a_database_the_fresh_install_made_is_replaced_whole_before_its_dump_is_loaded(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Each database's schema: who made it. The fresh install's Superset made its own; Postgres
    # refuses a dump's `--clean` drops over a schema the dump did not make, as the real one did.
    schema = {"ospreyflow": "conduit", "superset": "fresh-superset", "postgres": ""}
    loaded: list[str] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if "-Atc" in command:
            sql = command[-1]
            target = command[command.index("-d") + 1]
            assert target == "postgres", "a database is dropped or made from another one"
            if sql.startswith("DROP DATABASE"):
                assert "WITH (FORCE)" in sql, "the running Superset holds connections to it"
                schema.pop(sql.split('"')[1])
            elif sql.startswith("CREATE DATABASE"):
                schema[sql.split('"')[1]] = ""
            return subprocess.CompletedProcess(command, 0, stdout="\n".join(schema) + "\n", stderr="")
        database = command[-1]
        if schema.get(database) == "fresh-superset":
            return subprocess.CompletedProcess(
                command, 3, stdout=b"", stderr=b"ERROR:  cannot drop constraint tables_pkey on table public.tables"
            )
        loaded.append(database)
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(restore.subprocess, "run", run)
    folder = tmp_path / "set" / "postgres"
    folder.mkdir(parents=True)
    (folder / "dump.sql").write_text("CREATE TABLE investigations ();\n", encoding="utf-8")
    (folder / "superset.sql").write_text("CREATE TABLE dashboards ();\n", encoding="utf-8")
    restore.restore_postgres_all(deployment, [folder / "dump.sql", folder / "superset.sql"], None)
    assert loaded == ["ospreyflow", "superset"]
    # The deployment's own database is the Conduit's, whose schema is this commit's own and which
    # the running Conduit is connected to: it is loaded over, as B2e and B3 proved live, not dropped.
    assert schema["ospreyflow"] == "conduit"


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
    env.write_text("POSTGRES_USER=osprey\nOSPREY_KEYCLOAK_ADMIN_PASSWORD=new\nREPORT_SYNC_DASHBOARDS=[]\n"
                   "SUPERSET_SECRET_KEY=fresh-key\n", encoding="utf-8")  # fmt: skip
    held = tmp_path / "realm.json"
    held.write_text(json.dumps({"format": 1, "realm": "osprey", "people": [], "dashboards": [],
                                "report_sync_dashboards": '[{"client_id": "osprey-dashboard-c"}]',
                                "superset_secret_key": "old-superset-key"}),
                    encoding="utf-8")  # fmt: skip
    summary = restore.restore_identity(deployment, held)
    assert summary["people"] == 4 and imported and registered == [env]
    lines = env.read_text(encoding="utf-8").splitlines()
    assert 'REPORT_SYNC_DASHBOARDS=[{"client_id": "osprey-dashboard-c"}]' in lines
    assert sum(line.startswith("REPORT_SYNC_DASHBOARDS=") for line in lines) == 1
    assert [line for line in lines if line.startswith("SUPERSET_SECRET_KEY=")] == [
        "SUPERSET_SECRET_KEY=old-superset-key"
    ], "the key the restored dashboards were encrypted with"


def test_the_published_recipes_repository_is_in_the_set(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        asked.append(command)
        source, target = command[-2], Path(command[-1])
        if not source.endswith("/var/lib/osprey/data/recipes"):
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="Could not find the file: does not exist")
        (target / ".git").mkdir(parents=True)
        (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (target / "recipes").mkdir()
        (target / "recipes" / "r1.yaml").write_text("id: r1\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(backup.subprocess, "run", run)
    archive = backup.backup_recipes(deployment, tmp_path / "set" / "recipes" / "recipes.tar.gz",
                                    container_path="/var/lib/osprey/data/recipes", work_dir=tmp_path / "set")  # fmt: skip
    assert archive is not None and asked[0][-2] == "api:/var/lib/osprey/data/recipes"
    with tarfile.open(archive, "r:gz") as held:
        names = set(held.getnames())
    assert {"recipes/.git/HEAD", "recipes/recipes/r1.yaml"} <= names, "the history travels too"
    assert not (tmp_path / "set" / ".recipes-staging").exists()
    none = backup.backup_recipes(deployment, tmp_path / "other.tar.gz",
                                 container_path="/elsewhere/recipes", work_dir=tmp_path)  # fmt: skip
    assert none is None, "a deployment that never published has no repository, which is not an error"


def test_the_set_names_the_recipes_item(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def touch(path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return path

    monkeypatch.setattr(backup, "_conduit_is_running", lambda compose_file: False)
    monkeypatch.setattr(backup, "git_sha", lambda: "abc")
    monkeypatch.setattr(backup, "schema_versions", lambda: {"ontology": "13"})
    monkeypatch.setattr(backup, "CONFIGURATION_SOURCES", ())
    monkeypatch.setattr(backup, "backup_graph_store", lambda c, d, **kw: touch(d))
    monkeypatch.setattr(backup, "backup_postgres_all", lambda c, f: [("postgres", touch(f / "dump.sql"))])
    monkeypatch.setattr(backup, "backup_identity", lambda c, d: touch(d))
    monkeypatch.setattr(backup, "backup_object_store", lambda c, d, **kw: touch(d))
    monkeypatch.setattr(backup, "backup_analytics", lambda c, d, **kw: touch(d))
    seen: dict[str, str] = {}
    monkeypatch.setattr(backup, "backup_recipes",
                        lambda c, d, **kw: seen.update(path=kw["container_path"]) or touch(d))  # fmt: skip
    target = backup.run_backup(compose_file=deployment, out_root=tmp_path / "sets", profile="local-lite",
                               database="ospreyflow", analytics_container_path="/var/lib/osprey/data/analytics.duckdb",
                               require_quiesced=False)  # fmt: skip
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert "recipes" in {entry["item"] for entry in manifest["files"]}
    assert seen["path"] == "/var/lib/osprey/data/recipes", "where the renderer puts the repository"


def test_restored_files_are_handed_to_the_conduits_user(
    deployment: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ran: list[list[str]] = []
    monkeypatch.setattr(restore, "_run", lambda command, **kw: ran.append(command) or "")
    database = tmp_path / "analytics.duckdb"
    database.write_bytes(b"duck")
    restore.restore_analytics(deployment, database, container_path="/var/lib/osprey/data/analytics.duckdb")
    staging = tmp_path / "held"
    (staging / "recipes" / ".git").mkdir(parents=True)
    archive = tmp_path / "recipes.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(staging / "recipes", arcname="recipes")
    restore.restore_recipes(deployment, archive, container_path="/var/lib/osprey/data/recipes", work_dir=tmp_path)
    copies = [c for c in ran if "cp" in c]
    owners = [c for c in ran if "chown" in c]
    assert [c[-1] for c in copies] == ["api:/var/lib/osprey/data/analytics.duckdb", "api:/var/lib/osprey/data/recipes"]
    assert len(owners) == 2
    for chown, path in zip(owners, ("/var/lib/osprey/data/analytics.duckdb", "/var/lib/osprey/data/recipes"), strict=True):
        assert chown[chown.index("run"):][:6] == ["run", "--rm", "--no-deps", "--user", "root", "--entrypoint"]
        assert chown[-3:] == ["-R", "osprey:osprey", path]
        assert ran.index(chown) > ran.index(next(c for c in copies if c[-1].endswith(path))), "after the copy"


def test_a_clickhouse_deployment_is_refused_in_words_before_anything_is_written(tmp_path: Path) -> None:
    """ADR-114 decision 9: the set does not yet copy ClickHouse, so a backup of a deployment whose
    events are there is refused, not taken without them (rule 2: never a silent partial)."""
    out_root = tmp_path / "sets"
    with pytest.raises(backup.BackupFailed) as refused:
        backup.run_backup(
            compose_file=tmp_path / "compose.yaml", out_root=out_root, profile="small",
            database="osprey", analytics_container_path="/data/analytics.duckdb",
            require_quiesced=False, analytics_engine="clickhouse",
        )
    assert refused.value.item == "analytics"
    assert "ClickHouse" in refused.value.detail
    assert not out_root.exists()
