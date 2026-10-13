"""`python -m harness.backup` — the backup half of ADR-049's Stage 2 §4.

`05_DEPLOYMENT.md` §6 is the specification and its last line is the reason this module exists:
**"A backup nobody has restored is a hypothesis."** So the deliverable is not this file. It is this
file plus `harness/restore.py` plus the exit test that takes a seeded deployment, destroys it, and
proves the restored one carries the same data down to its `SAME_AS` scores and handling markings.

## What is in the backup set, and why each item is in it

ADR-049's amendment 10 names it: "staged Parquet, **object store contents**, Postgres dump,
ontology, handling scheme, and `osprey.yaml`." Object store contents is a separate named item from
configuration, and the graph store and the analytics database are here too:

| Item | How | §6's own row |
| --- | --- | --- |
| Graph store | ArcadeDB `BACKUP DATABASE` | "Engine-native snapshot" |
| Object store | the whole `/data` tree, where staged Parquet lives | "Object store replication" |
| PostgreSQL | `pg_dump --clean --if-exists` | "`pg_basebackup`" — see below |
| Analytics | the DuckDB file off the data volume | **not in §6's table at all** |
| Configuration | `osprey.yaml`, compose, realm, ontology, scheme | "Version control" |

**Two honest departures from §6's table, both recorded rather than papered over.**

- §6 says `pg_basebackup`. This takes a `pg_dump` instead. `pg_basebackup` is a physical, binary
  copy tied to the server's major version and page layout; a logical dump restores into a fresh
  container of the same image without the WAL machinery §6's hourly-WAL row implies, and
  `local-lite` has no WAL archive to ship. For a profile whose entire purpose is one machine, the
  logical dump is the honest mechanism. A `small` or `cluster` profile should revisit it, and
  `deploy/RUNBOOK.md` says so.
- **The analytics DuckDB is in no row of §6's table.** It holds every event the Conduit's
  `/v1/analytics/*` routes read — 266 of them in the seeded fixture alone — and it is not
  rebuildable from the graph store. Leaving it out because the table does not name it would produce
  a backup that restores a graph with no timeline. It is included, and the omission is recorded as
  a gap against §6.

## Audit data, which §6 makes an explicit exception

§6: audit data "is not rebuildable and it is not deletable. Replicate it separately, with its own
retention policy set by the deployment's legal basis."

`services/api/audit.py` puts `audit_log` in the **same** PostgreSQL instance as sites, monitors,
alerts, the export ledger and the review queue. So on `local-lite` it is inside the same `pg_dump`
as everything else, which is *not* separate replication and does *not* give it its own retention
policy. This module does not pretend otherwise: the manifest carries an explicit
`audit_disposition` block saying exactly that, and `deploy/RUNBOOK.md` repeats it. A deployment with
a legal basis that requires the §6 behaviour does not have it yet.

This matters beyond bookkeeping, because `05_DEPLOYMENT.md` §2.4's destroy confirmation is written
on the assumption that audit data is separately replicated and therefore survives a destroy. On
`local-lite` it does not.

## What this module does not do

It does not stop the deployment. A backup taken while the Conduit is writing can catch the graph
store and the analytics database at different instants. §6 asks for nightly snapshots, not for a
quiesced cluster-wide checkpoint, and building the latter is not Stage 2's scope — but a restore is
only as consistent as the backup, so `--require-quiesced` refuses to run unless the Conduit is
stopped, and the manifest records which of the two it was.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness import identity, keycloak_admin
from harness.render import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_OUT_ROOT,
    RECIPE_REPO_DIRNAME,
    git_sha,
    load_config,
)
from harness.site import answer_localhost_with_loopback, deployment_origins

#: The realm the deployment's people live in (`harness/realm.py`).
REALM = "osprey"

REPO_ROOT = Path(__file__).resolve().parent.parent

#: `05_DEPLOYMENT.md` §2.1's Components screen names `backups` as a storage root. This is the
#: repository-local default for a `local-lite` machine; the rendered `OSPREY_BACKUP_ROOT` is what a
#: real deployment uses, and `--out-root` is how an operator points at it.
DEFAULT_BACKUP_ROOT = REPO_ROOT / "backups"

#: The files that make a restore reproducible rather than merely possible. Each is copied verbatim
#: and checksummed; `harness/restore.py` compares the ontology and handling scheme against the
#: running deployment's own and refuses a mismatch, because a graph restored under a different
#: ontology is a graph whose handling markings mean something else.
CONFIGURATION_SOURCES: tuple[tuple[str, Path], ...] = (
    ("config/osprey.yaml", REPO_ROOT / "osprey.yaml"),
    ("config/ontology.yaml", REPO_ROOT / "packages" / "ontology" / "default.yaml"),
    (
        "config/handling-uk-le.yaml",
        REPO_ROOT / "packages" / "ontology" / "handling" / "uk-le.yaml",
    ),
)


class BackupFailed(RuntimeError):
    """Named so the CLI can report the stage rather than a traceback."""

    def __init__(self, item: str, detail: str) -> None:
        super().__init__(f"{item}: {detail}")
        self.item = item
        self.detail = detail


@dataclass(frozen=True)
class BackupEntry:
    """One file in the set. `sha256` is what makes a restore verifiable rather than hopeful."""

    path: str
    bytes: int
    sha256: str
    item: str


def _compose(compose_file: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(compose_file.parent / "deployment.env"),
        "-f",
        str(compose_file),
    ]


def _run(command: list[str], *, item: str, capture: bool = True) -> str:
    completed = subprocess.run(  # noqa: S603 - a fixed argv, never a shell string
        command,
        capture_output=capture,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[:800]
        raise BackupFailed(
            item, f"{' '.join(command[:6])}… exited {completed.returncode}\n{detail}"
        )
    return completed.stdout if capture else ""


def _env_value(env_path: Path, name: str) -> str:
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.partition("=")[2].strip()
    raise BackupFailed("environment", f"{name} is not in {env_path.name}")


def _env_value_or(env_path: Path, name: str, default: str) -> str:
    try:
        return _env_value(env_path, name)
    except BackupFailed:
        return default


def _digest(path: Path) -> tuple[int, str]:
    sha = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            sha.update(chunk)
            size += len(chunk)
    return size, sha.hexdigest()


def arcadedb_request(password: str, path: str, body: str | None = None) -> str:
    """A shell command, run inside the ArcadeDB container, that asks the server's HTTP API on its
    loopback and prints the answer; it exits non-zero on an HTTP error.

    Busybox `wget`, because that is what the pinned image has: ArcadeDB 26.10.1 (ADR-101) ships no
    `curl`, and every `curl` here failed with `sh: curl: not found` until the B2e backup found it
    (`tests/harness/test_arcadedb_shell.py`). The password travels as a Basic header, quoted for the
    shell like the body, so neither a quote nor a dollar in it can break the command; it reaches the
    container's own shell and no further (05_DEPLOYMENT.md §2.5/§7).
    """
    token = base64.b64encode(f"root:{password}".encode()).decode()
    words = ["wget", "-q", "-O", "-", "--header", f"Authorization: Basic {token}"]
    if body is not None:
        words += ["--header", "Content-Type: application/json", "--post-data", body]
    return shlex.join([*words, f"http://127.0.0.1:2480{path}"])


def _conduit_is_running(compose_file: Path) -> bool:
    return bool(_run(_compose(compose_file) + ["ps", "-q", "api"], item="quiesce").strip())


def backup_graph_store(compose_file: Path, destination: Path, *, database: str) -> Path:
    """§6's "engine-native snapshot", taken through ArcadeDB's own `BACKUP DATABASE`.

    Deliberately not a copy of the database directory. ArcadeDB writes pages lazily and a
    file-level copy of a live database is a copy of an arbitrary mid-write state — it would restore,
    and it would restore something that was never a consistent database. The engine's own backup
    takes the read lock and produces a zip it knows how to read back.
    """
    password = _env_value(compose_file.parent / "deployment.env", "OSPREY_ARCADEDB_PASSWORD")
    command = json.dumps({"language": "sql", "command": "BACKUP DATABASE"})
    raw = _run(
        _compose(compose_file)
        + [
            "exec",
            "-T",
            "arcadedb",
            "sh",
            "-c",
            # The password is not printed and not written into the manifest.
            arcadedb_request(password, f"/api/v1/command/{database}", command),
        ],
        item="graph",
    )
    try:
        backup_file = json.loads(raw)["result"][0]["backupFile"]
    except (json.JSONDecodeError, KeyError, IndexError) as error:
        raise BackupFailed(
            "graph", f"ArcadeDB did not report a backup file: {raw[:300]}"
        ) from error

    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        _compose(compose_file)
        + [
            "cp",
            f"arcadedb:/home/arcadedb/backups/{database}/{backup_file}",
            str(destination),
        ],
        item="graph",
    )
    return destination


def backup_postgres(compose_file: Path, destination: Path) -> Path:
    """A logical dump — see this module's docstring for why, not `pg_basebackup`.

    `--clean --if-exists` so the dump restores over an existing empty database without a manual
    drop, which is what the restore's own "launch the new environment empty" step needs.
    """
    env_path = compose_file.parent / "deployment.env"
    user = _env_value(env_path, "POSTGRES_USER")
    database = _env_value(env_path, "POSTGRES_DB")
    dump = _run(
        _compose(compose_file)
        + ["exec", "-T", "postgres", "pg_dump", "--clean", "--if-exists", "-U", user, database],
        item="postgres",
    )
    if "CREATE TABLE" not in dump and "COPY " not in dump:
        # An empty dump is a real outcome (a deployment nothing has written to) but it is far more
        # often a silent authentication or database-name failure that `pg_dump` exited 0 on.
        raise BackupFailed(
            "postgres",
            "the dump contains no schema and no data — check POSTGRES_USER/POSTGRES_DB against the "
            f"running container (got {len(dump)} bytes)",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(dump, encoding="utf-8")
    return destination


def _dump_or_refuse(dump: str, database: str) -> str:
    if "CREATE TABLE" not in dump and "COPY " not in dump:
        # An empty dump is far more often a silent authentication or database-name failure that
        # `pg_dump` exited 0 on than a database nothing has written to.
        raise BackupFailed(
            "postgres",
            f"the dump of '{database}' contains no schema and no data (got {len(dump)} bytes)",
        )
    return dump


#: Keycloak's own database (ADR-114 Amendment 5). Not dumped: the identity item carries the people
#: and dashboard identities with their ids, and a fresh install's Keycloak makes its own realm —
#: loading both would put every person in twice.
KEYCLOAK_DATABASE = "keycloak"


def databases_to_dump(listed: list[str]) -> list[str]:
    return [name for name in listed if name and name != KEYCLOAK_DATABASE]


def backup_postgres_all(compose_file: Path, folder: Path) -> list[tuple[str, Path]]:
    """Every database on the deployment's Postgres, and the roles they grant to (ADR-114
    Amendment 3). One dump was not the deployment: the dashboards keep their own `superset`
    database beside `ospreyflow`, and the reporting mart grants to a role the Conduit's database
    does not create. The deployment's own database keeps the name `dump.sql`; each other is
    `<name>.sql`; the roles are `roles.sql`, replayed first."""
    env_path = compose_file.parent / "deployment.env"
    user = _env_value(env_path, "POSTGRES_USER")
    main_database = _env_value(env_path, "POSTGRES_DB")
    on_postgres = _compose(compose_file) + ["exec", "-T", "postgres"]
    folder.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, Path]] = []
    # No passwords: a role's password is the deployment's own secret (`deployment.env`), and a fresh
    # install has minted new ones; carrying the old hashes locked the Conduit out at B2e.
    roles = _run(
        on_postgres + ["pg_dumpall", "--roles-only", "--no-role-passwords", "-U", user],
        item="postgres",
    )
    (folder / "roles.sql").write_text(roles, encoding="utf-8")
    written.append(("postgres-roles", folder / "roles.sql"))
    listed = _run(
        on_postgres
        + [
            "psql",
            "-U",
            user,
            "-d",
            "postgres",
            "-Atc",
            "select datname from pg_database where not datistemplate and datname <> 'postgres' "
            "order by datname",
        ],
        item="postgres",
    )
    for database in databases_to_dump(listed.split()):
        dump = _run(
            on_postgres + ["pg_dump", "--clean", "--if-exists", "-U", user, database],
            item="postgres",
        )
        target = folder / ("dump.sql" if database == main_database else f"{database}.sql")
        target.write_text(_dump_or_refuse(dump, database), encoding="utf-8")
        written.append(("postgres", target))
    return written


def backup_identity(compose_file: Path, destination: Path) -> Path:
    """The realm's people and dashboard identities, with their ids (`harness/identity.py`), and
    report-sync's dashboards setting and Superset's key. Keycloak keeps no data of its own past a
    restart on this profile, so this is the only copy of who holds a grant. It carries client
    secrets: written readable by its owner only."""
    env_path = compose_file.parent / "deployment.env"
    issuer = deployment_origins(env_path)[1]
    try:
        token = keycloak_admin.admin_token(
            issuer=issuer,
            admin_user="admin",
            admin_password=_env_value(env_path, "OSPREY_KEYCLOAK_ADMIN_PASSWORD"),
        )
        held = identity.export_identity(issuer=issuer, realm=REALM, token=token)
    except (keycloak_admin.RealmConfigurationFailed, identity.IdentityFailed) as error:
        raise BackupFailed("identity", str(error)) from error
    dashboards = _env_value_or(env_path, "REPORT_SYNC_DASHBOARDS", "")
    if dashboards:
        held["report_sync_dashboards"] = dashboards
    # Superset encrypts fields of its own database (`superset.sql`) with this key, so it belongs to
    # the data, not to the deployment: restored under a fresh install's new key, Superset could not
    # read its own records ("Invalid decryption key", found at B2e).
    superset_key = _env_value_or(env_path, "SUPERSET_SECRET_KEY", "")
    if superset_key:
        held["superset_secret_key"] = superset_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.touch(mode=0o600, exist_ok=True)
    destination.chmod(0o600)
    destination.write_text(json.dumps(held, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def backup_object_store(compose_file: Path, destination: Path, *, work_dir: Path) -> Path:
    """Every object in the object store, as plain files with their checksums, tarred.

    §6 has two rows that both land here — "Staged Parquet / Object store replication" and the
    staging bucket itself — because on `local-lite` the object store *is* where the staged Parquet
    lives. **Exported at the S3 level** (ADR-114 Amendment 9 point 3a), through the Conduit's own
    image inside the deployment's network (`services.api.object_transfer`), never as a copy of one
    store's private data folder, which no other store can read: so a backup taken on MinIO restores
    into SeaweedFS. Empty buckets are in the manifest, so they survive the round trip.
    """
    # **Not `work_dir / "objects"`.** That is the directory `destination` lives in, and the
    # `rmtree` below then deleted the tar that had just been written into it — the backup reported
    # success and the set was missing its object store. Caught by the exit test's own checksum
    # verification on the first run, which is the point of checksumming every file.
    staging = work_dir / ".objects-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    # The Conduit's image runs as its own user, which must be able to write here.
    staging.chmod(0o777)
    _run(
        _compose(compose_file) + [
            "run", "--rm", "--no-deps", "--entrypoint", "python",
            "-v", f"{staging.resolve()}:/transfer",
            "api", "-m", "services.api.object_transfer", "export", "/transfer",
        ],
        item="objects",
    )  # fmt: skip
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(staging, arcname="objects-export")
    shutil.rmtree(staging)
    return destination


def backup_analytics(compose_file: Path, destination: Path, *, container_path: str) -> Path | None:
    """The analytics DuckDB file. Returns `None` when there is none yet, which is not an error.

    In no row of §6's table, and included anyway — see this module's docstring. A deployment that
    has never seeded or ingested has no file, and a backup of a fresh deployment is a legitimate
    thing to take.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    listing = subprocess.run(  # noqa: S603
        _compose(compose_file) + ["cp", f"api:{container_path}", str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    if listing.returncode != 0:
        if "not exist" in (listing.stderr + listing.stdout).lower():
            return None
        raise BackupFailed("analytics", (listing.stderr or listing.stdout).strip()[:400])
    return destination


def backup_recipes(
    compose_file: Path, destination: Path, *, container_path: str, work_dir: Path
) -> Path | None:
    """The Ingest Studio's published-recipes repository, tarred with its git history. Returns
    `None` when the deployment has never published, which is not an error.

    It lives on the data volume beside the analytics file (the renderer's
    `OSPREY_RECIPE_REPO_ROOT`, `09_INGEST_STUDIO.md` §6), so `down -v` destroys it with everything
    else. Found taking the owner's backup before the B2e replacement: no item carried it.
    """
    staging = work_dir / ".recipes-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.parent.mkdir(parents=True, exist_ok=True)
    copied = subprocess.run(  # noqa: S603
        _compose(compose_file) + ["cp", f"api:{container_path}", str(staging)],
        capture_output=True,
        text=True,
        check=False,
    )
    if copied.returncode != 0:
        if "not exist" in (copied.stderr + copied.stdout).lower():
            return None
        raise BackupFailed("recipes", (copied.stderr or copied.stdout).strip()[:400])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(staging, arcname="recipes")
    shutil.rmtree(staging)
    return destination


def schema_versions() -> dict[str, str]:
    """What the restored data must be read back under.

    `harness/restore.py` refuses a restore whose ontology version does not match the target
    deployment's. A graph restored under a different ontology is not the same graph: the handling
    markings the adapter filters on are defined by the scheme, and the edge types a traversal walks
    are defined by the ontology.
    """
    from ontology.handling import load_uk_le_scheme
    from ontology.loader import load_default_ontology

    scheme = load_uk_le_scheme()
    return {
        "ontology": str(load_default_ontology().version),
        "handling_scheme": getattr(scheme, "name", "uk-le"),
        "git_sha": git_sha(),
    }


#: §6's audit exception, stated as data so the manifest carries it and `harness/restore.py` can
#: print it rather than a reader having to know to look for it.
AUDIT_DISPOSITION: dict[str, Any] = {
    "separately_replicated": False,
    "statement": (
        "05_DEPLOYMENT.md §6 requires audit data to be replicated separately, with its own "
        "retention policy. It is not. services/api/audit.py writes audit_log to the same "
        "PostgreSQL instance as sites, monitors, alerts, the export ledger and the review queue, "
        "so on this profile it is inside the same logical dump as everything else and shares its "
        "retention. §2.4's destroy confirmation assumes audit data survives a destroy; on "
        "local-lite it does not."
    ),
    "where_it_is": "postgres/dump.sql, table audit_log",
}


def run_backup(
    *,
    compose_file: Path,
    out_root: Path,
    profile: str,
    database: str,
    analytics_container_path: str,
    require_quiesced: bool,
    analytics_engine: str = "duckdb",
) -> Path:
    """Writes the set and its manifest. Returns the directory."""
    if analytics_engine != "duckdb":
        store = "ClickHouse" if analytics_engine == "clickhouse" else analytics_engine
        # ADR-114 decision 9: the events of a ClickHouse deployment are not in the DuckDB file this
        # set copies. Taking the set without them would restore a deployment with no events, so it
        # is refused before anything is written.
        raise BackupFailed(
            "analytics",
            f"This deployment keeps its events in {store}, "
            "which `ospreyflow backup` does not copy yet; a set without them would restore a "
            "deployment with no events. Back ClickHouse up with its own BACKUP command until "
            "then.",
        )
    if require_quiesced and _conduit_is_running(compose_file):
        raise BackupFailed(
            "quiesce",
            "--require-quiesced was given and the Conduit is running. A backup taken while it "
            "writes can catch the graph store and the analytics database at different instants. "
            f"Stop it first: docker compose -f {compose_file} stop api",
        )
    quiesced = not _conduit_is_running(compose_file)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = out_root / f"{stamp}-{profile}-{git_sha()}"
    target.mkdir(parents=True, exist_ok=False)

    written: list[tuple[str, Path]] = []
    written.append(
        (
            "graph",
            backup_graph_store(
                compose_file, target / "graph" / "arcadedb-backup.zip", database=database
            ),
        )
    )
    written.extend(backup_postgres_all(compose_file, target / "postgres"))
    written.append(("identity", backup_identity(compose_file, target / "identity" / "realm.json")))
    written.append(
        (
            "objects",
            backup_object_store(compose_file, target / "objects" / "data.tar.gz", work_dir=target),
        )
    )
    analytics = backup_analytics(
        compose_file,
        target / "analytics" / "analytics.duckdb",
        container_path=analytics_container_path,
    )
    if analytics is not None:
        written.append(("analytics", analytics))
    recipes = backup_recipes(
        compose_file,
        target / "recipes" / "recipes.tar.gz",
        container_path=f"{analytics_container_path.rpartition('/')[0]}/{RECIPE_REPO_DIRNAME}",
        work_dir=target,
    )
    if recipes is not None:
        written.append(("recipes", recipes))
    for relative, source in CONFIGURATION_SOURCES:
        if not source.exists():
            raise BackupFailed("configuration", f"{source} does not exist")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        written.append(("configuration", destination))
    for name in ("compose.yaml", "realm.json"):
        rendered = compose_file.parent / name
        if rendered.exists():
            destination = target / "config" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rendered, destination)
            written.append(("configuration", destination))

    entries = []
    for item, path in written:
        size, sha = _digest(path)
        entries.append(
            BackupEntry(path=str(path.relative_to(target)), bytes=size, sha256=sha, item=item)
        )

    manifest: dict[str, Any] = {
        "format": 1,
        "taken_at": datetime.now(UTC).isoformat(),
        "profile": profile,
        "database": database,
        "quiesced": quiesced,
        "schema_versions": schema_versions(),
        "audit_disposition": AUDIT_DISPOSITION,
        "files": [entry.__dict__ for entry in sorted(entries, key=lambda e: e.path)],
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m harness.backup",
        description=(
            "Takes a backup of a running OspreyFlow deployment (05_DEPLOYMENT.md §6). Restore it "
            "with `python -m harness.restore <dir>`."
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--generated-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--database", default="ospreyflow")
    parser.add_argument(
        "--require-quiesced",
        action="store_true",
        help="Refuse to run unless the Conduit is stopped. See this module's docstring.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    # ADR-114 Amendment 4 decision 7: the deployment's names reach its proxy on this machine.
    answer_localhost_with_loopback()
    config = load_config(args.config)
    profile = args.profile or config.profile.value
    compose_file = args.generated_root / profile / "compose.yaml"
    if not compose_file.exists():
        print(
            f"backup: no rendered deployment at {compose_file}. Run `python -m harness.apply "
            f"--profile {profile}` first.",
            file=sys.stderr,
        )
        return 1

    try:
        target = run_backup(
            compose_file=compose_file,
            out_root=args.out_root,
            profile=profile,
            database=args.database,
            analytics_container_path=f"{config.components.storage.data}/analytics.duckdb",
            require_quiesced=args.require_quiesced,
            analytics_engine=config.components.analytics_engine.value,
        )
    except BackupFailed as failure:
        print(f"backup: FAILED on '{failure.item}'\n  {failure.detail}", file=sys.stderr)
        return 1

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    total = sum(entry["bytes"] for entry in manifest["files"])
    print(f"backup: {target}")
    for entry in manifest["files"]:
        print(f"  {entry['item']:<13} {entry['path']:<34} {entry['bytes']:>12,} bytes")
    print(f"  {'total':<13} {len(manifest['files']):>2} file(s){'':<26}{total:>12,} bytes")
    if not manifest["quiesced"]:
        print(
            "\n  Taken with the Conduit running. The graph store and the analytics database were "
            "captured at different instants; use --require-quiesced for a consistent set."
        )
    print(f"\n  audit data: {AUDIT_DISPOSITION['where_it_is']} — NOT separately replicated (§6).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
