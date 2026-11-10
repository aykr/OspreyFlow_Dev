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
import os
import re
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
from harness.signatures import _as_caller
from harness.site import (
    answer_localhost_with_loopback,
    answer_the_deployment_here,
    deployment_origins,
)
from schemas.deployment import (
    OspreyConfig,
    StorageRoots,
    generated_folder,
    self_contained_small,
)

#: The realm the deployment's people live in (`harness/realm.py`).
REALM = "osprey"

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The schema's default for `components.storage.backups`, which the committed `osprey.yaml` also
#: carries. Off a server of your own nobody ever chose it (before ADR-114 Amendment 37 the backup
#: wrote to the checkout whatever it said), so there it is read as no folder named.
LEGACY_PLACEHOLDER: str = StorageRoots.model_fields["backups"].default


#: The fallback folder as the operator writes it: what setup offers and the runbook prints.
FALLBACK_SPELLING = "~/OspreyFlow/backups"


def fallback_backups_folder() -> Path:
    """`~/OspreyFlow/backups`: what setup offers (Amendment 37 decision 1), and where a set goes
    when the deployment's `osprey.yaml` names no folder (decision 2)."""
    return Path(FALLBACK_SPELLING).expanduser()


def named_backups_folder(config: OspreyConfig) -> str | None:
    """`components.storage.backups` as written, when it names a folder (ADR-114 Amendment 38
    decision 1: the placeholder, or a blank, names none off a server of your own); else `None`."""
    storage = config.components.storage
    value = storage.backups.strip() if "backups" in storage.model_fields_set else ""
    placeholder = value and Path(value) == Path(LEGACY_PLACEHOLDER)
    return value if value and (not placeholder or self_contained_small(config)) else None


def backups_folder(config: OspreyConfig) -> tuple[Path, str | None]:
    """The deployment's backups folder (`components.storage.backups`, ADR-114 Amendment 37
    decision 1, read for every profile), and what to tell the operator when there was none: an
    `osprey.yaml` from before the amendment names none, or names the placeholder."""
    named = named_backups_folder(config)
    if named is not None:
        return Path(named).expanduser(), None
    folder = fallback_backups_folder()
    return folder, (
        f"This deployment's osprey.yaml names no backups folder of its own (none, or the "
        f"placeholder {LEGACY_PLACEHOLDER}), so the set goes to {folder}. Name one as "
        "components.storage.backups (folders.backups in the install answers)."
    )


def default_out_root(config: OspreyConfig, name: str | None = None) -> Path:
    """Where a set is written when `--out-root` is not given: the deployment's own subfolder of its
    backups folder, `<folder>/<deployment name>/` (Amendment 37 decision 3), so two deployments'
    sets never mix (ADR-138). `name` is `--profile`'s, when given; else `generated_folder`."""
    return backups_folder(config)[0] / (name or generated_folder(config))


def checkout_root() -> Path:
    """The git checkout this product is in: the folder above `OspreyFlow_Core` that holds `.git`
    (a file in a worktree), else `OspreyFlow_Core` itself (a published repository, an image)."""
    for candidate in (REPO_ROOT, REPO_ROOT.parent):
        if (candidate / ".git").exists():
            return candidate
    return REPO_ROOT


def is_inside(folder: Path, root: Path) -> bool:
    """Whether `folder`, once made, would be `root` or under it. Compared by the file each existing
    ancestor is (`os.path.samefile`), not by spelling: on a case-insensitive disk
    `ospreyflow_core/backups` is `OspreyFlow_Core/backups`, and a bind mount or link is the folder
    it shows. Resolved as the system resolves it (`..` after a link is the link's own parent), never
    by tidying the spelling first."""
    target = folder.expanduser().resolve()
    for candidate in (target, *target.parents):
        try:
            if candidate.exists() and os.path.samefile(candidate, root):
                return True
        except OSError:
            continue
    return False


def refuse_inside_the_checkout(folder: Path) -> None:
    """Amendment 37 decision 2: no backup is ever written inside the checkout (the git checkout, so
    `OspreyFlow_Build/` and the root too), which is synced, copied and shared with its working
    tree; a set holds the deployment's data and any real-data exception (ADR-035 §C3)."""
    checkout = checkout_root().resolve()
    if is_inside(folder, checkout):
        raise BackupFailed(
            "out-root",
            f"{folder} is inside the checkout ({checkout}); a backup is never written there. "
            "Name a folder outside it with --out-root, or leave it out to use the deployment's "
            "backups folder (components.storage.backups).",
        )


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
    # ADR-120 Amendment 5: stored weights name a version of this file (`parameter_set`).
    ("config/weights.yaml", REPO_ROOT / "packages" / "ontology" / "weights" / "default.yaml"),
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


def _run(command: list[str], *, item: str, capture: bool = True, input: str | None = None) -> str:
    completed = subprocess.run(  # noqa: S603 - a fixed argv, never a shell string
        command,
        capture_output=capture,
        text=True,
        check=False,
        input=input,
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


#: The gateway's own database (ADR-135 Amendment 2 decision 3).
GATEWAY_DATABASE = "litellm"
#: Its tables whose rows hold a key or a value sealed under the deployment's encryption key:
#: the credentials, the model entries (every parameter sealed) and its stored settings.
#: `05_DEPLOYMENT.md` §6.1: "A backup carries no secrets … Nothing in a backup may ever be
#: encrypted with a deployment-scoped key." Their schema is kept, their rows are not, so every
#: restore brings the engines back from the models file and asks for each key again (the owner's
#: ruling, 8 November 2026).
GATEWAY_SEALED_TABLES = (
    '"LiteLLM_CredentialsTable"',
    '"LiteLLM_ProxyModelTable"',
    '"LiteLLM_Config"',
    # ADR-135 Amendment 3: each engine's own gateway key (its hash, last four and spend). Restored
    # elsewhere it would keep the old deployment's engine key working there; a restore's first
    # start makes each engine's key afresh (its budget's spend so far starts again).
    '"LiteLLM_VerificationToken"',
    # ADR-135 Amendment 3, as built in P3: a deleted engine key (an engine removed, or revoked at a
    # reconcile after the master key changed) keeps its hash, its name's last four and its metadata
    # here. A restore has no use for a deleted key, so none of it is carried.
    '"LiteLLM_DeletedVerificationToken"',
)


def _without_secrets(database: str) -> list[str]:
    if database != GATEWAY_DATABASE:
        return []
    return [f"--exclude-table-data=public.{table}" for table in GATEWAY_SEALED_TABLES]


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
            on_postgres
            + [
                "pg_dump",
                "--clean",
                "--if-exists",
                *_without_secrets(database),
                "-U",
                user,
                database,
            ],
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
    # **Run as the caller, so the copy is the caller's to remove** (defect 10, ADR-114 Amendment
    # 33, as found on the first server, 4 November 2026). As the Conduit's own user (uid 10001) the
    # export made its folders 10001's, mode 755, and the installer could not delete the files in
    # them, so every backup of a store holding files failed at this `rmtree`; Docker Desktop hides
    # ownership. As cosign's container is run (`harness.signatures._as_caller`). The folder is the
    # caller's own, so it is no longer opened to every account; 755 so a restore's import, as
    # whichever user, can read the tree it comes back as.
    staging.chmod(0o755)
    _run(
        _compose(compose_file) + [
            "run", "--rm", "--no-deps", *_as_caller(), "--entrypoint", "python",
            "-v", f"{staging.resolve()}:/transfer",
            "api", "-m", "services.api.object_transfer", "export", "/transfer",
        ],
        item="objects",
    )  # fmt: skip
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(staging, arcname="objects-export")
    left = remove_tree(staging)
    if left:
        raise BackupFailed("objects", f"its staging copy {staging} could not be removed: {left}")
    return destination


def remove_tree(folder: Path) -> str:
    """Removes `folder` and everything in it; returns, in words, what could not be removed (empty
    when everything was). Never raises for what it cannot remove: a clean-up that fails silently
    left a partial set that looked removed (defect 10)."""
    refused: list[str] = []

    def note(_function: object, path: str, error: BaseException) -> None:
        refused.append(f"{path} ({getattr(error, 'strerror', None) or error})")

    if folder.exists():
        shutil.rmtree(folder, onexc=note)
    if not refused:
        return ""
    more = f", and {len(refused) - 3} more" if len(refused) > 3 else ""
    return "; ".join(refused[:3]) + more


#: How Docker refuses a `cp` from a path the container does not have: the daemon's words since
#: Engine 1.13 ("Could not find the file <path> in container <name>"), and the client's older ones.
#: Matched on these alone, so a container that is not running still fails the backup.
_NOTHING_TO_COPY = ("could not find the file", "no such container:path")


def found_nothing_to_copy(copied: subprocess.CompletedProcess[str]) -> bool:
    """Whether a failed `docker compose cp` failed only because the path is absent: on a fresh
    deployment the analytics file and the recipes repository do not exist yet, which is an empty
    item, not a failed backup (ADR-114 Amendment 33, as found on the first server, 4 November
    2026). This looked for "not exist", which Docker never says, so the first backup of a fresh
    Small failed on 'recipes'."""
    said = f"{copied.stderr or ''}{copied.stdout or ''}".lower()
    return any(words in said for words in _NOTHING_TO_COPY)


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
        if found_nothing_to_copy(listing):
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
        if found_nothing_to_copy(copied):
            return None
        raise BackupFailed("recipes", (copied.stderr or copied.stdout).strip()[:400])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(staging, arcname="recipes")
    shutil.rmtree(staging)
    return destination


def schema_versions(*, include_weights: bool = True) -> dict[str, str]:
    """What the restored data must be read back under.

    `harness/restore.py` refuses a restore whose ontology version does not match the target
    deployment's. A graph restored under a different ontology is not the same graph: the handling
    markings the adapter filters on are defined by the scheme, and the edge types a traversal walks
    are defined by the ontology.

    A backup records the weights file's latest version too (`weights`, ADR-120 Amendment 6) and
    fails loudly, `BackupFailed` naming the file, if it is missing or malformed. A restore does not
    read the weights file (`include_weights=False`): it compares the ontology only, and a restore
    that refuses on the weights is its own record.
    """
    from ontology.errors import OntologyError
    from ontology.handling import load_uk_le_scheme
    from ontology.loader import load_default_ontology

    scheme = load_uk_le_scheme()
    versions = {
        "ontology": str(load_default_ontology().version),
        "handling_scheme": getattr(scheme, "name", "uk-le"),
        "git_sha": git_sha(),
    }
    if include_weights:
        from ontology import weights as weights_module

        try:
            versions["weights"] = str(weights_module.load_weight_rules().version)
        except (OSError, OntologyError) as error:
            raise BackupFailed(
                "weights", f"{weights_module._DEFAULT_PATH} cannot be read: {error}"
            ) from error
    return versions


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


#: A set's folder name, `<UTC stamp>-<deployment>-<sha>` (`new_set_folder`).
#: The sha is letters and digits only, so a failed backup's `<set>.incomplete` never matches.
SET_NAME = re.compile(r"^(?P<stamp>\d{8}T\d{6}Z)-(?P<name>.+)-(?P<sha>[0-9A-Za-z]+)$")


@dataclass(frozen=True)
class FoundSet:
    """A deployment's set, where it is. `belongs_in` is the deployment's own folder when the set is
    still in an old place (ADR-114 Amendment 37 decision 3), else None."""

    path: Path
    belongs_in: Path | None = None

    def move_command(self) -> str | None:
        """The one command that moves it to where it belongs; the operator runs it, never us."""
        if self.belongs_in is None:
            return None
        to = shlex.quote(str(self.belongs_in))
        return f"mkdir -p {to} && mv {shlex.quote(str(self.path))} {to}/"


def sets_in(folder: Path, name: str | None = None) -> list[Path]:
    """The sets directly in `folder` (named as `new_set_folder` names one; never a failed backup's
    `.incomplete`), only `name`'s when it is given."""
    if not folder.is_dir():
        return []
    found = []
    for child in folder.iterdir():
        matched = SET_NAME.match(child.name)
        if child.is_dir() and matched and (name is None or matched["name"] == name):
            found.append(child)
    return found


def old_places(config: OspreyConfig, name: str) -> list[tuple[Path, str | None]]:
    """Where `name`'s sets were written before Amendment 37, each with the name its sets must carry
    to be this deployment's (None: every set there is): the checkout's `backups/` (every install
    off a server), a named deployment's own `backups/` (ADR-138), and the top of the backups folder
    (Amendment 33's server)."""
    return [
        (REPO_ROOT / "backups", name),
        (Path.home() / ".ospreyflow" / "deployments" / name / "backups", None),
        (backups_folder(config)[0], name),
    ]


def find_sets(config: OspreyConfig, name: str) -> list[FoundSet]:
    """`name`'s sets, newest first: its own folder's, then any still in an old place, each with
    where it belongs."""
    home = backups_folder(config)[0] / name
    found = [FoundSet(path) for path in sets_in(home)]
    seen = {home.resolve()}
    for folder, carrying in old_places(config, name):
        if folder.resolve() in seen:
            continue
        seen.add(folder.resolve())
        found += [FoundSet(path, home) for path in sets_in(folder, carrying)]
    return sorted(found, key=lambda s: (s.path.name, s.belongs_in is None), reverse=True)


def new_set_folder(out_root: Path, profile: str) -> Path:
    """A new set's folder under `out_root`, readable by its owner only: it holds the case data and
    the people's identities with the dashboards' client secrets (ADR-114 Amendment 33 decision 5
    puts it in a folder of its own on a server). Never inside the checkout (Amendment 37)."""
    if Path(profile).name != profile or profile in ("", ".", ".."):
        raise BackupFailed(
            "out-root", f"{profile!r} cannot name a set: a deployment's name is one folder's name"
        )
    refuse_inside_the_checkout(out_root)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = out_root / f"{stamp}-{profile}-{git_sha()}"
    target.mkdir(parents=True, exist_ok=False)
    target.chmod(0o700)
    return target


def backup_configuration(compose_file: Path, target: Path) -> list[tuple[str, Path]]:
    """The deployment's settings and rendered files, by name: `CONFIGURATION_SOURCES`, then the
    rendered `compose.yaml` and `realm.json`. **Only these:** never `deployment.env` (its secrets
    are the deployment's own, §6.1), and never the organisation's certificate or key, which the
    proxy mounts from where they are and the set only names, in `compose.yaml` (ADR-114 Amendment
    33 decision 5)."""
    written: list[tuple[str, Path]] = []
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
    return written


def run_backup(
    *,
    compose_file: Path,
    out_root: Path,
    profile: str,
    database: str,
    analytics_container_path: str,
    require_quiesced: bool,
    analytics_engine: str = "duckdb",
    managed_postgres: str | None = None,
) -> Path:
    """Writes the set and its manifest. Returns the directory."""
    if managed_postgres is not None:
        # 05 §3a: a managed database is the cloud's to back up; there is no container to dump from.
        raise BackupFailed(
            "postgres",
            f"This deployment's database is the cloud's managed server ({managed_postgres}), "
            "which the cloud's own backups protect (AWS Backup and RDS snapshots, or Azure "
            "Backup); `ospreyflow backup` does not take a second copy of it. Restore from the "
            "cloud's console.",
        )
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

    target = new_set_folder(out_root, profile)
    try:
        return _take_set(
            compose_file, target, profile=profile, database=database,
            analytics_container_path=analytics_container_path, quiesced=quiesced,
        )  # fmt: skip
    except BaseException as failure:
        # A set is good only once its manifest is written, and `restore` refuses a folder without
        # one; but a half-written folder beside the good sets is still one a person can take for a
        # set, so it is removed (as found on the first server, 4 November 2026) — or, where some of
        # it cannot be, marked incomplete and said so (defect 10).
        said = _set_aside(target)
        if isinstance(failure, BackupFailed):
            raise BackupFailed(failure.item, f"{failure.detail}\n{said}") from failure
        raise


#: The file that marks a set a failed backup could not remove whole; `harness.restore` refuses it.
INCOMPLETE = "INCOMPLETE"


def _set_aside(target: Path) -> str:
    """A failed backup's set removed; what could not be removed renamed `<set>.incomplete`, with an
    `INCOMPLETE` file in it, so no person, restore or update takes it for a set. Returns what was
    done, in words."""
    left = remove_tree(target)
    if not left:
        return f"The partial set {target} was removed; nothing was kept."
    marked = target.with_name(f"{target.name}.incomplete")
    try:
        target.rename(marked)
    except OSError:
        marked = target
    try:
        (marked / INCOMPLETE).write_text(
            "This backup set is incomplete: the backup failed and some of it could not be "
            f"removed ({left}). It is not a backup; restore refuses it. Remove it as root: "
            f"sudo rm -rf {marked}\n",
            encoding="utf-8",
        )
    except OSError:
        pass  # the name still says so
    return (
        f"The partial set could not be removed whole: {left}. It was renamed {marked} and marked "
        f"incomplete ({INCOMPLETE} in it), so restore refuses it and it is not a backup. Remove it "
        f"as root: sudo rm -rf {marked}"
    )


MODELS_FILE_IN_CONDUIT = "/run/osprey/model-settings/models.yaml"


def backup_models_file(compose_file: Path, destination: Path) -> Path | None:
    """The models file (ADR-135 Amendment 2 decision 2), from the Conduit's own volume: engines,
    defaults and each key's record, never a key. Read through the running Conduit, or, when it is
    stopped (a quiesced backup), a one-off container of its image on the same volume. None only
    where *Models* has changed nothing yet; a file that cannot be read stops the backup in words,
    never a set silently without it (`05_DEPLOYMENT.md` §6, rule 2)."""
    read = f"cat {MODELS_FILE_IN_CONDUIT} 2>/dev/null || true"
    compose = _compose(compose_file)
    try:
        text = _run([*compose, "exec", "-T", "api", "sh", "-c", read], item="models")
    except BackupFailed:
        text = _run(
            [*compose, "run", "--rm", "--no-deps", "-T", "--entrypoint", "sh", "api", "-c", read],
            item="models",
        )
    if not text.strip():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination


MAPS_FILE_IN_CONDUIT = "/run/osprey/map-settings/maps.yaml"


def backup_maps_file(compose_file: Path, destination: Path) -> Path | None:
    """The maps file (ADR-147 decision 1), from the Conduit's own volume: the providers, the
    default, the prefetch areas and the ids of the providers whose key is set, never a key. The map
    key file beside it is never read: only this file is named. Read as the models file is."""
    read = f"cat {MAPS_FILE_IN_CONDUIT} 2>/dev/null || true"
    compose = _compose(compose_file)
    try:
        text = _run([*compose, "exec", "-T", "api", "sh", "-c", read], item="maps")
    except BackupFailed:
        text = _run(
            [*compose, "run", "--rm", "--no-deps", "-T", "--entrypoint", "sh", "api", "-c", read],
            item="maps",
        )
    if not text.strip():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination


def _take_set(
    compose_file: Path,
    target: Path,
    *,
    profile: str,
    database: str,
    analytics_container_path: str,
    quiesced: bool,
) -> Path:
    written: list[tuple[str, Path]] = []
    empty: list[str] = []
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
    else:
        empty.append("analytics")
    recipes = backup_recipes(
        compose_file,
        target / "recipes" / "recipes.tar.gz",
        container_path=f"{analytics_container_path.rpartition('/')[0]}/{RECIPE_REPO_DIRNAME}",
        work_dir=target,
    )
    if recipes is not None:
        written.append(("recipes", recipes))
    else:
        empty.append("recipes")
    written.extend(backup_configuration(compose_file, target))
    models_file = backup_models_file(compose_file, target / "config" / "models.yaml")
    if models_file is not None:
        written.append(("models", models_file))
    maps_file = backup_maps_file(compose_file, target / "config" / "maps.yaml")
    if maps_file is not None:
        written.append(("maps", maps_file))

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
        # Items the deployment did not have yet, so the set holds nothing for them: a restore
        # leaves them as the fresh deployment has them, and says so.
        "empty": sorted(empty),
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
    parser.add_argument(
        "--out-root",
        type=Path,
        default=None,
        help="the folder the set is written in, never inside the checkout; default: "
        "<components.storage.backups>/<deployment name>/",
    )
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
    # ADR-114 Amendment 33 decision 2: on a server, its own names here, its certificate trusted
    # (the identity export reaches the deployment's identity provider).
    answer_the_deployment_here(config)
    # ADR-132 Amendment 1: the deployment's own folder, `deployment.name` or the profile.
    profile = args.profile or generated_folder(config)
    if args.out_root is not None:
        out_root = args.out_root
    else:
        out_root = default_out_root(config, profile)
        notice = backups_folder(config)[1]
        if notice:
            print(f"backup: {notice}")
    try:
        refuse_inside_the_checkout(out_root)
    except BackupFailed as refused:
        print(f"backup: REFUSED\n  {refused.detail}", file=sys.stderr)
        return 1
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
            out_root=out_root,
            profile=profile,
            database=args.database,
            analytics_container_path=f"{config.components.storage.data}/analytics.duckdb",
            require_quiesced=args.require_quiesced,
            analytics_engine=config.components.analytics_engine.value,
            managed_postgres=(
                config.external.postgres.host if config.external.postgres is not None else None
            ),
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
    for item in manifest["empty"]:
        print(f"  {item:<13} empty: this deployment has none yet, so the set holds none")
    if not manifest["quiesced"]:
        print(
            "\n  Taken with the Conduit running. The graph store and the analytics database were "
            "captured at different instants; use --require-quiesced for a consistent set."
        )
    print(f"\n  audit data: {AUDIT_DISPOSITION['where_it_is']} — NOT separately replicated (§6).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
