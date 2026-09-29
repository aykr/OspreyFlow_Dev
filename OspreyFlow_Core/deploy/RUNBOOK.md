# Recovery runbook

**Not to be confused with `deploy/generated/<profile>/RUNBOOK.md`**, which the renderer writes per
deployment and which describes *that* deployment — its services, images and ports. This file is
hand-written, checked in, and about **recovery**: it is the same document across every profile
because the procedure is, and only its measured times are `local-lite`'s.

`spec/05_DEPLOYMENT.md` §6 requires this file and requires it to state the recovery time for each
path. Every number below was measured on `local-lite` on 24 September 2026 against the seeded
HMP + Fixture Corp fixture — 1,978 records, a 4.0 MB backup set — on a MacBook with a 9.9 GiB Docker
VM. They are what this machine did, not a service level.

**Read §6's last line before anything else: "A backup nobody has restored is a hypothesis."** These
times come from `tests/harness/test_restore_exit_test.py`, which takes a backup, destroys the
deployment's volumes, restores it and compares the two down to the `SAME_AS` scores. If you change
the backup set, run that test; a runbook that has not been executed is prose.

## Commands

```bash
# Take a set. --require-quiesced refuses unless the Conduit is stopped — see "Consistency" below.
docker compose -f deploy/generated/local-lite/compose.yaml stop api
PYTHONPATH=.:packages .venv/bin/python -m harness.backup --profile local-lite --require-quiesced
docker compose -f deploy/generated/local-lite/compose.yaml start api

# Restore. Without --yes this is a dry run: it prints the projection and writes nothing.
PYTHONPATH=.:packages .venv/bin/python -m harness.restore backups/<set>
PYTHONPATH=.:packages .venv/bin/python -m harness.restore backups/<set> --yes
```

`--yes` is the acknowledgement ADR-049's amendment 11 requires. Read the projection before you give
it: at national scale the replay is measured in days and the point of the dry run is that the
window gets planned rather than discovered.

## Recovery times, measured

| Path | Measured | What dominates it |
| --- | --- | --- |
| **Backup** (quiesced, whole set) | **10s** | ArcadeDB's own `BACKUP DATABASE`, which compressed 2.57 GB of allocated pages to 3.2 MB |
| **Short path** — restore from a set | **8s** | the offline restore tool; the data itself is negligible at this size |
| **Long path** — full rebuild from staging | **35s** | re-running both fixtures' ingest recipes against the staged Parquet |
| Bringing the stack back up, empty | 28s | container start-up and health checks, not data |
| **End to end, destroyed → seeded and verified** | **64s** | of which 28s is start-up and 35s is the replay |

Two things follow from those numbers and neither is about the numbers.

**At this size the short path saves 27 seconds, and that is not why it exists.** §6 is explicit that
the graph store and the search index are rebuildable from staged Parquet and that their backups
"exist to shorten recovery, not to make it possible". The ratio is what matters and it does not hold
still: the short path scales with the size of the stored data, the long path with the *work* that
produced it — every recipe, every resolution pass, every model inference re-run. On a national-scale
deployment they are not minutes apart, they are orders of magnitude apart, which is the case the dry
run's projection exists to make visible before anyone commits to one.

**What is *not* rebuildable is the part the table does not measure.** Audit data, analyst-authored
assessments, confirmations that promoted `inferred` to `confirmed` — none of that came from staged
Parquet and no replay produces it. The long path restores the graph; it does not restore the
casework.

## Consistency: quiesce, or know that you did not

`--require-quiesced` refuses to run while the Conduit is up. Without it a set is still taken, and
the manifest records `"quiesced": false`, and the restore's dry run prints a warning — because the
graph store and the analytics database are captured at different instants and the difference is not
detectable afterwards.

This is not theoretical. Building the exit test, a snapshot and a backup taken seconds apart with
the Conduit running disagreed by eight `mx_PRESENT_AT` edges. That particular disagreement turned
out to be a lagging counter in ArcadeDB rather than a real write (`harness/compare.py`'s
`type_record_counts` has the detail) — but until it was chased down, the evidence pointed squarely
at the restore having lost eight edges. That is what a non-quiesced set costs you, at the worst
possible moment to be spending it.

## What is in a set

| Item | Mechanism | §6's row |
| --- | --- | --- |
| Graph store | ArcadeDB `BACKUP DATABASE` | "Engine-native snapshot" |
| Object store | the whole `/data` tree, tarred — where staged Parquet lives | "Object store replication" |
| PostgreSQL | `pg_dump --clean --if-exists` | "`pg_basebackup`" — **differs, see below** |
| Analytics | the DuckDB file from the data volume | **not in §6's table at all** |
| Configuration | `osprey.yaml`, the rendered compose file and realm, the ontology, the handling scheme | "Version control" |

`manifest.json` names every file with its SHA-256, the profile, the git sha, the ontology version
and whether the set was quiesced. The restore verifies every checksum before it writes anything.

**Two departures from §6's table, deliberate and recorded rather than quietly made.**

- §6 says `pg_basebackup`; this takes a logical `pg_dump`. `pg_basebackup` is a physical copy tied
  to the server's major version and page layout, and it implies the WAL machinery §6's hourly row
  describes — which `local-lite` has no archive for. A `small` or `cluster` profile should revisit
  this; for one machine, the logical dump is the honest mechanism.
- The analytics DuckDB is in no row of §6's table. It holds every event `/v1/analytics/*` reads —
  266 in the seeded fixture — and it is not rebuildable from the graph store. Omitting it because
  the table omits it would produce a backup that restores a graph with no timeline.

## Audit data — §6 is not satisfied

§6 makes audit data an explicit exception: "not rebuildable and… not deletable. Replicate it
separately, with its own retention policy set by the deployment's legal basis."

**It is not separately replicated.** `services/api/audit.py` writes `audit_log` to the same
PostgreSQL instance as sites, monitors, alerts, the export ledger and the review queue, so on this
profile it is inside the same logical dump as everything else and shares its retention. The manifest
says so in an `audit_disposition` block and the restore's dry run prints it, so nobody can reach the
decision point without being told.

This reaches beyond bookkeeping: `05_DEPLOYMENT.md` §2.4's destroy confirmation is written assuming
audit data survives a destroy. On `local-lite` it does not. A deployment whose legal basis requires
§6's behaviour does not have it yet.

## The three refusals

A restore can destroy more than it repairs, so it refuses readily:

1. **Checksum mismatch.** A truncated set that restores most of a graph is worse than one that does
   not restore at all — the second is obviously a failure and the first looks like success.
2. **A non-empty target.** §4 step 3 is "launch the new environment empty". Restoring over live data
   merges a snapshot into it with no way afterwards to say which rows came from where. Destroy the
   volumes (`docker compose -f <compose> down -v`), bring the stack back up, then restore.
3. **A different ontology version.** The handling markings the adapter filters on and the edge types
   a traversal walks are both defined by the ontology; a graph restored under a different one does
   not mean what it meant, and nothing downstream would notice.

## Secrets are not part of a restore, by decision

Every credential is minted at apply time into the generated, gitignored environment file
(§2.5, §7). A restored deployment is therefore a **new** deployment with **new** secrets, holding
rows written under the old ones. **You do not re-supply anything.**

§6.1 settles this (25 September 2026): a backup carries no secrets, a restore re-mints them, and
**nothing in a backup may ever be encrypted with a deployment-scoped key** — a standing constraint
in §7. Without that last clause the first two would be a silent data-loss path: the restore would
report success and the data would be unreadable. A credential that must survive a restore is held
by reference, never as ciphertext in a store.

On `cluster`, secrets live outside the deployment in a manager the restored deployment is pointed
at. That is Phase 8a's and does not apply here.

## If the restore fails

- **`Could not find the file /home/arcadedb/backups in container`** — the graph container was
  recreated and that directory does not survive it. `harness/restore.py` creates it; if you are
  restoring by hand, `mkdir -p` it first.
- **`Server command not valid` / `ParseException: Encountered <IDENTIFIER> "RESTORE"`** — you are
  trying to restore over HTTP. ArcadeDB has no such SQL and its server endpoint does not take SQL.
  Restore is offline: `bin/restore.sh -f file://<zip> -d /home/arcadedb/databases/<name>`, then
  `open database <name>` at `/api/v1/server`.
- **The restored database is there and the Conduit cannot see it** — restart the Conduit. It opens
  the analytics DuckDB at start-up and holds an exclusive lock on it, which is also why the restore
  needs it stopped.
