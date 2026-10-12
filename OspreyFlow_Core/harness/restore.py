"""`python -m harness.restore <dir>` — the half that makes the backup something other than a
hypothesis.

`05_DEPLOYMENT.md` §6 and ADR-049's Stage 2 §4, including its amendments 10 and 11.

## The three refusals, and why each exists

A restore is the one operation in this system that can destroy more than it repairs, so this module
refuses far more readily than it acts.

1. **It refuses a set whose checksums do not match its manifest.** A truncated backup that restores
   most of a graph is worse than one that does not restore at all: the second is obviously a
   failure and the first looks like success.
2. **It refuses to restore into a non-empty store.** ADR-049's amendment to the exit test names
   this directly — §4 step 3 is "launch the new environment empty", and *"nothing in the stated
   test distinguishes a restore into an empty store from a no-op against the source store."* That
   is not only a hole in the test; it is a hole in the operation. Restoring over a live store would
   merge a snapshot into current data and there would be no way afterwards to say which rows came
   from where.
3. **It refuses a set taken under a different ontology version.** The handling markings the adapter
   filters on (`CLAUDE.md` rule 3) and the edge types a traversal walks are both defined by the
   ontology. A graph restored under a different one is not the same graph, and the difference is
   invisible at the multiset level — exactly the class of loss amendment 10's exit test was
   rewritten to catch.

## Amendment 11's dry run

*"Restore opens with a dry run showing the row count and a projected duration, and will not proceed
until that estimate is acknowledged. A national-scale replay is measured in days and must be
planned, not discovered."*

So `--dry-run` is not a flag an operator opts into; it is what happens by default. `--yes`
acknowledges the estimate and proceeds. The projection is deliberately crude — a rate per megabyte
measured on `local-lite` and recorded in `deploy/RUNBOOK.md` — because the number that matters at
national scale is the order of magnitude, and a precise-looking estimate derived from a sample this
small would be a worse lie than an obviously rough one. The projection says which it is.

## What a restore does not bring back, and why that is now a rule rather than a gap

**Secrets, deliberately.** Every credential in a deployment is minted at apply time into the
generated, gitignored environment file (`05_DEPLOYMENT.md` §2.5, §7). A restored deployment is a
*new* deployment with *new* secrets, and the restored PostgreSQL dump contains rows written under
the old ones.

`05_DEPLOYMENT.md` §6.1 settles this (owner's decision, 25 September 2026): **a backup carries no
secrets, a restore re-mints them, and nothing in a backup may ever be encrypted with a
deployment-scoped key.** The last clause is what makes the first two safe, and it is a standing
constraint in §7 rather than a property of this module — there is nothing here to re-supply, so
there is nothing here to get wrong, but only for as long as no future feature encrypts something at
rest with a key that dies with the deployment. A credential that must survive a restore is held by
reference, never as ciphertext in a store.

The `cluster` profile answers this differently — secrets held outside the deployment, in a manager
the restored deployment is pointed at — and that is Phase 8a's, not this module's.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness import identity, keycloak_admin
from harness.backup import (
    REALM,
    BackupFailed,
    _compose,
    _env_value,
    _env_value_or,
    _run,
    arcadedb_request,
    schema_versions,
)
from harness.render import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_OUT_ROOT,
    RECIPE_REPO_DIRNAME,
    load_config,
)

#: Measured on `local-lite` against the seeded HMP + Fixture Corp set and recorded in
#: `deploy/RUNBOOK.md`. Used only to project a duration for the dry run — see the docstring on why
#: it is deliberately crude.
SECONDS_PER_MEGABYTE = 0.35

#: Below this, the projection is noise: container start-up dominates and the answer is "about a
#: minute" regardless of the payload.
MINIMUM_PROJECTED_SECONDS = 20.0


class RestoreRefused(RuntimeError):
    """A refusal, not a failure. The distinction is the point — see the module docstring."""

    def __init__(self, reason: str, remedy: str) -> None:
        super().__init__(f"{reason} — {remedy}")
        self.reason = reason
        self.remedy = remedy


@dataclass(frozen=True)
class DryRun:
    """What amendment 11 requires an operator to acknowledge before anything is written."""

    total_bytes: int
    file_count: int
    projected_seconds: float
    items: dict[str, int]
    audit_statement: str
    quiesced: bool

    def render(self) -> str:
        lines = [
            "restore — DRY RUN. Nothing has been written.",
            "",
            f"  from        {self.file_count} file(s), {self.total_bytes:,} bytes",
        ]
        for item, size in sorted(self.items.items()):
            lines.append(f"    {item:<13} {size:>12,} bytes")
        lines += [
            "",
            f"  projected   about {self.projected_seconds:.0f}s on a local-lite-sized machine.",
            "              A rate measured on one small deployment, extrapolated linearly. At",
            "              national scale this is an order of magnitude, not an estimate — plan",
            "              the window from a rehearsal on data of that size, not from this line.",
        ]
        if not self.quiesced:
            lines += [
                "",
                "  WARNING     this set was taken with the Conduit running. Its graph store and",
                "              its analytics database were captured at different instants.",
            ]
        lines += [
            "",
            f"  audit       {self.audit_statement}",
            "",
            "  Re-run with --yes to acknowledge the estimate and proceed.",
        ]
        return "\n".join(lines)


def load_manifest(directory: Path) -> dict[str, Any]:
    path = directory / "manifest.json"
    if not path.exists():
        raise RestoreRefused(
            f"{directory} has no manifest.json",
            "this is not a backup set produced by `python -m harness.backup`",
        )
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return manifest


def verify_checksums(directory: Path, manifest: dict[str, Any]) -> None:
    """Refusal 1. Every file, every time — a restore is not the moment to save a little IO."""
    problems = []
    for entry in manifest["files"]:
        path = directory / entry["path"]
        if not path.exists():
            problems.append(f"{entry['path']}: missing")
            continue
        sha = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                sha.update(chunk)
        if sha.hexdigest() != entry["sha256"]:
            problems.append(f"{entry['path']}: checksum mismatch")
    if problems:
        raise RestoreRefused(
            f"{len(problems)} file(s) in this set do not match the manifest: "
            + "; ".join(problems[:5]),
            "the set is incomplete or corrupt. A partial restore that looks like a successful one "
            "is worse than no restore, so this stops here",
        )


def dry_run_for(directory: Path, manifest: dict[str, Any]) -> DryRun:
    items: dict[str, int] = {}
    for entry in manifest["files"]:
        items[entry["item"]] = items.get(entry["item"], 0) + entry["bytes"]
    total = sum(items.values())
    projected = max(MINIMUM_PROJECTED_SECONDS, (total / 1_000_000) * SECONDS_PER_MEGABYTE)
    return DryRun(
        total_bytes=total,
        file_count=len(manifest["files"]),
        projected_seconds=projected,
        items=items,
        audit_statement=manifest["audit_disposition"]["statement"],
        quiesced=bool(manifest["quiesced"]),
    )


def graph_store_is_empty(compose_file: Path, *, database: str) -> bool:
    """Refusal 2's measurement.

    A database that does not exist yet counts as empty — that is the "launch the new environment
    empty" case, and creating it is part of the restore. A database that exists with no records
    also counts: a fresh deployment applies its schema at Conduit start-up, so "no database at all"
    is not the only empty shape, and requiring it would make a restore impossible on any stack that
    had ever been started.

    **The first draft of this asked `SELECT count(*) FROM V` and could not have gone red.** ArcadeDB
    has no `V`/`E` supertypes unless something creates them, and this ontology's adapter does not:
    the query fails with `SchemaException: Type with name 'V' was not found`, the error was read as
    "no such database", and the function returned `True` against a store holding 1,109 vertices and
    861 edges. A refusal that always permits is not a refusal. `harness/compare.py`'s
    `type_record_counts` reads the schema's own per-type record counts instead, which is the same
    measurement the exit test's comparison is built on — one way of counting, used by both.
    """
    from harness.compare import total_records

    # `total_records` counts an absent database as zero — the legitimate empty state immediately
    # after a destroy, and the one a restore exists to fill.
    return total_records(compose_file, database) == 0


def restore_graph_store(compose_file: Path, archive: Path, *, database: str) -> None:
    """ArcadeDB's own offline restore tool, `bin/restore.sh`.

    **Not `RESTORE DATABASE` over HTTP, which does not exist.** Two plausible-looking paths were
    tried against a real 24.11.1 server and both were refused: `POST /api/v1/server` with a SQL
    `RESTORE DATABASE` answers `{"error": "Server command not valid"}`, because that endpoint takes
    its own small command language and not SQL; and `POST /api/v1/command/<db>` answers
    `ParseException: Encountered <IDENTIFIER> "RESTORE" at line 1, column 1`, because `RESTORE` is
    not in the SQL grammar at all. Restore is an *offline* operation in ArcadeDB — the engine will
    not overwrite a database it has open — and `bin/restore.sh` is the supported tool.

    So the sequence is: drop the database at the server (closing it), remove the directory, restore
    into it, and re-open it. The drop is allowed to fail — after a `down -v` there is nothing to
    drop, which is the normal case for a restore — but the restore itself is checked, and the
    re-open is what makes the restored data reachable without a container restart.

    Safe only because `graph_store_is_empty` has already refused if the store held anything. The
    ordering is not interchangeable: dropping before the emptiness check would destroy the evidence
    the check is made of.
    """
    password = _env_value(compose_file.parent / "deployment.env", "OSPREY_ARCADEDB_PASSWORD")
    name = f"restore-{int(time.time())}.zip"
    # **The directory has to exist first.** `/home/arcadedb/backups` is created by ArcadeDB's own
    # first `BACKUP DATABASE` and lives in the container filesystem, not in a volume — so after the
    # `down -v` this restore exists to recover from, it is gone, and `docker compose cp` into it
    # fails with "Could not find the file /home/arcadedb/backups in container". Which is to say:
    # the one situation a restore is always run in is the one situation the copy could not work in.
    _run(
        _compose(compose_file)
        + ["exec", "-T", "arcadedb", "mkdir", "-p", "/home/arcadedb/backups"],
        item="graph",
    )
    _run(
        _compose(compose_file) + ["cp", str(archive), f"arcadedb:/home/arcadedb/backups/{name}"],
        item="graph",
    )

    drop = json.dumps({"command": f"drop database {database}"})
    output = _run(
        _compose(compose_file)
        + [
            "exec",
            "-T",
            "arcadedb",
            "sh",
            "-c",
            f"{arcadedb_request(password, '/api/v1/server', drop)} > /dev/null 2>&1 || true; "
            f"rm -rf /home/arcadedb/databases/{database}; "
            f"cd /home/arcadedb && ./bin/restore.sh "
            f"-f file:///home/arcadedb/backups/{name} -d /home/arcadedb/databases/{database}",
        ],
        item="graph",
    )
    if "restore completed" not in output.lower():
        raise BackupFailed("graph", f"the restore tool did not complete: {output.strip()[-400:]}")

    reopen = json.dumps({"command": f"open database {database}"})
    answer = _run(
        _compose(compose_file)
        + [
            "exec",
            "-T",
            "arcadedb",
            "sh",
            "-c",
            arcadedb_request(password, "/api/v1/server", reopen),
        ],
        item="graph",
    )
    if '"error"' in answer:
        raise BackupFailed("graph", f"the restored database would not open: {answer.strip()[:400]}")


def restore_postgres(compose_file: Path, dump: Path) -> None:
    """`psql` with the dump on stdin. The dump was taken `--clean --if-exists`, so it drops and
    recreates each object it owns rather than colliding with a schema the Conduit created at
    start-up."""
    env_path = compose_file.parent / "deployment.env"
    user = _env_value(env_path, "POSTGRES_USER")
    database = _env_value(env_path, "POSTGRES_DB")
    with dump.open("rb") as handle:
        completed = subprocess.run(  # noqa: S603
            _compose(compose_file)
            + ["exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", user, database],
            stdin=handle,
            capture_output=True,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        raise BackupFailed("postgres", (completed.stderr or completed.stdout).strip()[:800])


def _psql(
    compose_file: Path,
    database: str,
    sql: bytes | None = None,
    *,
    stop_on_error: bool = True,
    command: str | None = None,
) -> subprocess.CompletedProcess[Any]:
    user = _env_value(compose_file.parent / "deployment.env", "POSTGRES_USER")
    argv = _compose(compose_file) + ["exec", "-T", "postgres", "psql"]
    argv += (["-v", "ON_ERROR_STOP=1"] if stop_on_error else []) + ["-U", user]
    argv += ["-d", database, "-Atc", command] if command else [database]
    if sql is None:
        return subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603
    import io

    return subprocess.run(argv, stdin=io.BytesIO(sql), capture_output=True, check=False)  # noqa: S603


def restore_postgres_all(compose_file: Path, dumps: list[Path], roles: Path | None) -> None:
    """The roles first — the dumps grant to them — tolerating the ones the fresh install already
    made; then each database, created first when the fresh server does not have it (`superset`);
    `dump.sql` is the deployment's own database (ADR-114 Amendment 3)."""
    main_database = _env_value(compose_file.parent / "deployment.env", "POSTGRES_DB")
    if roles is not None:
        replayed = _psql(compose_file, "postgres", roles.read_bytes(), stop_on_error=False)
        errors = [
            line
            for line in _text(replayed.stderr).splitlines()
            if "ERROR" in line and "already exists" not in line
        ]
        if errors:
            raise BackupFailed("postgres", "replaying the roles: " + "; ".join(errors)[:600])
    present = set(
        _text(
            _psql(compose_file, "postgres", command="select datname from pg_database").stdout
        ).split()
    )
    for dump in dumps:
        database = main_database if dump.name == "dump.sql" else dump.stem
        if database not in present:
            made = _psql(compose_file, "postgres", command=f'CREATE DATABASE "{database}"')
            if made.returncode != 0:
                raise BackupFailed(
                    "postgres", f"creating '{database}': {_text(made.stderr).strip()[:400]}"
                )
        loaded = _psql(compose_file, database, dump.read_bytes())
        if loaded.returncode != 0:
            raise BackupFailed(
                "postgres", f"'{database}': {_text(loaded.stderr or loaded.stdout).strip()[:800]}"
            )


def _text(value: str | bytes | None) -> str:
    return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")


def _register_sign_in(env_path: Path) -> None:
    """The demo accounts' passwords again, from the new deployment's own file: passwords never
    travel with the identity."""
    from harness import register_sign_in

    issuer = f"http://127.0.0.1:{_env_value_or(env_path, 'OSPREY_KEYCLOAK_PORT', '8081')}"
    status = register_sign_in.main(
        [
            "--out-root",
            str(env_path.parent.parent),
            "--profile",
            env_path.parent.name,
            "--keycloak-url",
            issuer,
            "--realm",
            REALM,
        ]
    )
    if status != 0:
        raise BackupFailed("identity", "setting the demo accounts' passwords again was refused")


def _set_env_line(env_path: Path, name: str, value: str) -> None:
    lines = [
        line
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if not line.startswith(f"{name}=")
    ]
    env_path.write_text("\n".join([*lines, f"{name}={value}"]) + "\n", encoding="utf-8")


def restore_identity(compose_file: Path, held: Path) -> dict[str, int]:
    """The people and dashboard identities, with their ids (`harness/identity.py`); the demo
    accounts' passwords set again; report-sync's dashboards setting written back."""
    env_path = compose_file.parent / "deployment.env"
    issuer = f"http://127.0.0.1:{_env_value_or(env_path, 'OSPREY_KEYCLOAK_PORT', '8081')}"
    carried = json.loads(held.read_text(encoding="utf-8"))
    try:
        token = keycloak_admin.admin_token(
            issuer=issuer,
            admin_user="admin",
            admin_password=_env_value(env_path, "OSPREY_KEYCLOAK_ADMIN_PASSWORD"),
        )
        summary = identity.import_identity(
            issuer=issuer, realm=REALM, token=token, identity=carried
        )
    except (keycloak_admin.RealmConfigurationFailed, identity.IdentityFailed) as error:
        raise BackupFailed("identity", str(error)) from error
    _register_sign_in(env_path)
    if carried.get("report_sync_dashboards"):
        _set_env_line(env_path, "REPORT_SYNC_DASHBOARDS", carried["report_sync_dashboards"])
    return summary


def restore_object_store(compose_file: Path, archive: Path, *, work_dir: Path) -> None:
    extracted = work_dir / "restore-objects"
    if extracted.exists():
        shutil.rmtree(extracted)
    extracted.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as tar:
        # `filter="data"` is Python 3.12's own safe extraction: no absolute paths, no `..`, no
        # device or setuid entries. A backup set is operator-supplied input like any other.
        tar.extractall(extracted, filter="data")
    _run(
        _compose(compose_file) + ["cp", str(extracted / "data") + "/.", "minio:/data"],
        item="objects",
    )


def _give_to_conduit(compose_file: Path, container_path: str, *, item: str) -> None:
    """`docker cp` leaves what it copies owned by the host's user (measured: uid 502, gid 0, mode
    644), and the Conduit runs as `osprey`, so a restored file it writes to would be read-only to
    it. A one-off container of the Conduit's own image, as root, on the same volume, hands it back —
    whether or not the Conduit is running."""
    _run(
        _compose(compose_file)
        + ["run", "--rm", "--no-deps", "--user", "root", "--entrypoint", "chown", "api"]
        + ["-R", "osprey:osprey", container_path],
        item=item,
    )


def restore_analytics(compose_file: Path, database_file: Path, *, container_path: str) -> None:
    _run(
        _compose(compose_file) + ["cp", str(database_file), f"api:{container_path}"],
        item="analytics",
    )
    _give_to_conduit(compose_file, container_path, item="analytics")


def restore_recipes(
    compose_file: Path, archive: Path, *, container_path: str, work_dir: Path
) -> None:
    """The published-recipes repository back where the renderer points the Conduit, history and
    all, owned by the Conduit so the next publish can commit to it."""
    extracted = work_dir / "restore-recipes"
    if extracted.exists():
        shutil.rmtree(extracted)
    extracted.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(extracted, filter="data")
    _run(
        _compose(compose_file) + ["cp", str(extracted / "recipes") + "/.", f"api:{container_path}"],
        item="recipes",
    )
    shutil.rmtree(extracted)
    _give_to_conduit(compose_file, container_path, item="recipes")


def check_schema_compatibility(manifest: dict[str, Any]) -> None:
    """Refusal 3. The git sha is reported but not enforced: code moves, and a restore into a later
    build is the normal case. The ontology version is enforced, because it changes what the data
    *means*."""
    recorded = manifest["schema_versions"]
    current = schema_versions()
    if recorded["ontology"] != current["ontology"]:
        raise RestoreRefused(
            f"this set was taken under ontology version {recorded['ontology']!r} and this "
            f"deployment runs {current['ontology']!r}",
            "the handling markings the adapter filters on and the edge types a traversal walks are "
            "both defined by the ontology, so the restored graph would not mean what it meant when "
            "it was backed up — and nothing downstream would notice",
        )


def run_restore(
    *,
    directory: Path,
    compose_file: Path,
    database: str,
    analytics_container_path: str,
    acknowledged: bool,
) -> DryRun:
    manifest = load_manifest(directory)
    verify_checksums(directory, manifest)
    check_schema_compatibility(manifest)
    plan = dry_run_for(directory, manifest)
    if not acknowledged:
        return plan

    if not graph_store_is_empty(compose_file, database=database):
        raise RestoreRefused(
            f"the graph store '{database}' on this deployment is not empty",
            "§4 step 3 is 'launch the new environment empty'. Restoring over live data would merge "
            "a snapshot into it with no way afterwards to say which rows came from where. Destroy "
            f"the deployment's volumes first (`docker compose -f {compose_file} down -v`) and "
            "bring it back up, then restore into it",
        )

    by_item: dict[str, list[Path]] = {}
    for entry in manifest["files"]:
        by_item.setdefault(entry["item"], []).append(directory / entry["path"])

    for archive in by_item.get("graph", []):
        restore_graph_store(compose_file, archive, database=database)
    roles = by_item.get("postgres-roles", [None])[0]
    restore_postgres_all(compose_file, by_item.get("postgres", []), roles)
    for objects in by_item.get("objects", []):
        restore_object_store(compose_file, objects, work_dir=directory)
    for analytics in by_item.get("analytics", []):
        restore_analytics(compose_file, analytics, container_path=analytics_container_path)
    for recipes in by_item.get("recipes", []):
        restore_recipes(
            compose_file,
            recipes,
            container_path=f"{analytics_container_path.rpartition('/')[0]}/{RECIPE_REPO_DIRNAME}",
            work_dir=directory,
        )
    for held in by_item.get("identity", []):
        restore_identity(compose_file, held)
    return plan


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m harness.restore",
        description=(
            "Restores a backup set into an empty deployment (05_DEPLOYMENT.md §6). Shows a dry run "
            "and refuses to proceed until it is acknowledged with --yes."
        ),
    )
    parser.add_argument("directory", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--generated-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--database", default="ospreyflow")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Acknowledge the projected duration and proceed. Without it, this is a dry run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    config = load_config(args.config)
    profile = args.profile or config.profile.value
    compose_file = args.generated_root / profile / "compose.yaml"
    if not compose_file.exists():
        print(f"restore: no rendered deployment at {compose_file}.", file=sys.stderr)
        return 1

    started = time.monotonic()
    try:
        plan = run_restore(
            directory=args.directory,
            compose_file=compose_file,
            database=args.database,
            analytics_container_path=f"{config.components.storage.data}/analytics.duckdb",
            acknowledged=args.yes,
        )
    except RestoreRefused as refusal:
        print(f"restore: REFUSED\n  {refusal.reason}\n  {refusal.remedy}", file=sys.stderr)
        return 2
    except BackupFailed as failure:
        print(f"restore: FAILED on '{failure.item}'\n  {failure.detail}", file=sys.stderr)
        return 1

    if not args.yes:
        print(plan.render())
        return 0
    print(
        f"restore: {plan.file_count} file(s), {plan.total_bytes:,} bytes restored in "
        f"{time.monotonic() - started:.0f}s (projected {plan.projected_seconds:.0f}s)."
    )
    print("  The Conduit must be restarted to pick up the restored analytics database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
