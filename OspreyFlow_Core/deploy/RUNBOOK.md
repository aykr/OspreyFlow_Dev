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

# The set goes to <backups folder>/<deployment>/ (components.storage.backups, ~/OspreyFlow/backups
# when none is named; ADR-114 Amendment 37), never inside the checkout. List the sets:
PYTHONPATH=.:packages .venv/bin/python -m harness.restore

# Restore one by its name (or its folder). Without --yes this is a dry run: it prints the
# projection and writes nothing.
PYTHONPATH=.:packages .venv/bin/python -m harness.restore <set>
PYTHONPATH=.:packages .venv/bin/python -m harness.restore <set> --yes
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

## The `cloud-platform` profile (ADR-148 decision 13, Amendment 7)

On the client's platform the stores are not containers on one machine and there is no `harness.backup`:
the managed stores (PostgreSQL on RDS, Valkey on ElastiCache, the media and staging buckets) are the
platform's, under its own snapshots and versioning, and **this section covers what the deployment runs
itself**: ArcadeDB, ClickHouse and, in the proof-of-concept shape, the Ingest root's claim
(`ospreyflow-ingest`: uploads and the drop folder). **The restore below is supported for one copy of
each store** (development, and the proof-of-concept shape); the production shape's (three ArcadeDB
copies, ClickHouse ON CLUSTER with two replicas) is not supported yet, and the render refuses it.

**The schedule.** Two CronJobs, daily at 02:15 UTC (their time zone is UTC whatever the cluster's):
`ospreyflow-backup` (ArcadeDB's `BACKUP DATABASE`, then ClickHouse's `BACKUP … TO S3`) and, in the
proof-of-concept shape, `ospreyflow-backup-claims` (each claim of its own, read-only, beside the pods
that mount it). Both write one set, `s3://<prefix>backups/sets/<YYYYMMDDTHHMMSSZ>/`, named by their
schedule slot; `manifest.json` is written last, only once every part is there, with the time the set
finished. A set without it is unfinished and is never restored from. Every object is encrypted by the
backups bucket's own KMS key (`alias/<namespace>-backups`). Two roles write it, each to its own prefix
(ClickHouse's own, for its part; the runner's, for the rest), and no key is stored anywhere. Neither role
can erase a set: the bucket is versioned, so an object overwritten keeps its previous version for 7 days,
and a set's objects expire by the bucket's lifecycle rule 35 days after they were written (the retention
is the total, 35 days). A run killed part-way leaves ArcadeDB's zip on its backups claim; the next run
removes it before it starts.

**Is last night's backup there?** A backup Job that completed wrote a finished set (the manifest is its
last write), and its log names the set:

```bash
kubectl -n <namespace> get jobs -l app.kubernetes.io/name=backup --sort-by=.metadata.creationTimestamp
kubectl -n <namespace> logs job/<the newest> | grep 'backup: set'
```

A failed run is a failed Job, its log naming the store, the step and the refusing service's own words.
No alert is raised on it yet: look each morning. Every set, finished or not, and when each finished, as
the runner sees them:

```bash
kubectl -n <namespace> create job "backup-sets-$(date +%s)" --from=cronjob/ospreyflow-backup --dry-run=client -o json \
  | python3 -c 'import json, sys; j = json.load(sys.stdin); j["spec"]["template"]["spec"]["containers"][0]["command"][-1] = "sets"; print(json.dumps(j))' \
  | kubectl -n <namespace> create -f -
kubectl -n <namespace> logs -f job/<that job>      # <set>  finished  <YYYY-MM-DDTHH:MM:SSZ>, or <set>  unfinished
```

**A backup now** (before an upgrade, or the decommission's last backup): both runs for one slot, each
Job named as the CronJob names it (`<cronjob>-<minute since 1970>`), since that names the set.

```bash
S=$(( $(date +%s) / 60 ))
kubectl -n <namespace> create job "ospreyflow-backup-$S" --from=cronjob/ospreyflow-backup
if kubectl -n <namespace> get cronjob ospreyflow-backup-claims >/dev/null 2>&1; then
  kubectl -n <namespace> create job "ospreyflow-backup-claims-$S" --from=cronjob/ospreyflow-backup-claims
fi
# Complete or Failed, whichever comes first (a failed Job is never waited on for hours):
kubectl -n <namespace> wait --for=jsonpath='{.status.conditions[0].status}'=True "job/ospreyflow-backup-$S" --timeout=6h
kubectl -n <namespace> get job "ospreyflow-backup-$S" -o jsonpath='{.status.succeeded}'   # 1: the set is finished
```

**Before an upgrade, with the Conduit stopped** (so the parts agree; see *Consistency*). In the
proof-of-concept shape the claims run is placed beside the shared folders' pods, which are then stopped,
so its Job is made without that placement (the claim is free once they are stopped):

```bash
kubectl -n <namespace> scale deployment/api deployment/worker deployment/report-sync --replicas=0
kubectl -n <namespace> wait --for=delete pod -l 'app.kubernetes.io/name in (api,worker,report-sync)' --timeout=10m
S=$(( $(date +%s) / 60 ))
kubectl -n <namespace> create job "ospreyflow-backup-$S" --from=cronjob/ospreyflow-backup
if kubectl -n <namespace> get cronjob ospreyflow-backup-claims >/dev/null 2>&1; then
  kubectl -n <namespace> create job "ospreyflow-backup-claims-$S" --from=cronjob/ospreyflow-backup-claims \
    --dry-run=client -o json \
    | python3 -c 'import json, sys; j = json.load(sys.stdin); j["spec"]["template"]["spec"].pop("affinity", None); print(json.dumps(j))' \
    | kubectl -n <namespace> create -f -
fi
kubectl -n <namespace> wait --for=jsonpath='{.status.conditions[0].status}'=True "job/ospreyflow-backup-$S" --timeout=6h
kubectl -n <namespace> get job "ospreyflow-backup-$S" -o jsonpath='{.status.succeeded}' | grep -qx 1 \
  || echo "the backup did not finish: read its log before upgrading"
# The upgrade itself (the install's runbook), then the Conduit, the workers and the report sync start
# with it; if there is no upgrade after all, start them again:
kubectl -n <namespace> scale deployment/api deployment/worker deployment/report-sync --replicas=1
```

**A restore** of set `<set>` (it replaces what ArcadeDB, ClickHouse and the claims hold), **for one copy of
each store only**. It refuses, touching nothing, while anything that writes still runs, while it cannot see
what runs, or while any part of the set is missing, changed or another set's. *What writes* is the render's
own list (`backups.writers` in `values.yaml`): ArcadeDB, every workload that mounts the set's claims or
writes the stores (directly, or through the Conduit), and the backups' own runs. Each store is replaced
only once its restored copy is proven: ArcadeDB's is restored beside the live database, checked against the
set's zip and opened, then swapped in, the old one removed last; ClickHouse's is restored into a database of
its own, then swapped in by rename. A failure before the swap leaves the live database as it was. It reads
ArcadeDB's zip and each claim twice (the first step checks every part, the next checks its own as it reads
it): a large set's restore takes that much longer.

**The managed database first.** The stores and PostgreSQL must agree: restoring ArcadeDB and ClickHouse to
a set while PostgreSQL stays as it is now would bring back, visible under today's grants, anything withdrawn
or deleted since the set. So before the stores, PostgreSQL (RDS) is restored point in time to the set's
finish time (`sets` prints it), by the platform team's own RDS procedure, and the deployment pointed at it:

```bash
aws rds restore-db-instance-to-point-in-time --source-db-instance-identifier <the deployment's instance> \
  --target-db-instance-identifier <a new name> --restore-time <the set's finish time>
# then the platform team points the namespace's database settings at the new instance (its Terraform)
```

```bash
# 1. No backup during the restore: both CronJobs suspended, and any backup Job still running left to finish.
for c in ospreyflow-backup ospreyflow-backup-claims; do
  kubectl -n <namespace> patch cronjob "$c" -p '{"spec":{"suspend":true}}' 2>/dev/null
done
kubectl -n <namespace> get jobs -l 'app.kubernetes.io/name in (backup,backup-claims)'   # none still Running
# 2. Note each copy count, then stop everything that writes and wait for it to be gone.
W=$(python3 -c 'import sys, yaml; print(",".join(yaml.safe_load(open(sys.argv[1]))["backups"]["writers"]))' <render>/values.yaml)
kubectl -n <namespace> get deployment,statefulset -l "app.kubernetes.io/name in ($W)" \
  -o custom-columns=NAME:.metadata.name,COPIES:.spec.replicas
kubectl -n <namespace> scale deployment,statefulset -l "app.kubernetes.io/name in ($W)" --replicas=0
kubectl -n <namespace> wait --for=delete pod -l "app.kubernetes.io/name in ($W)" --timeout=10m
# 3. The restore's Jobs, rendered for the set by its own name (never `latest`; never by `helm upgrade`,
#    which would start ArcadeDB); a Job of the same name from an earlier attempt removed first.
kubectl -n <namespace> delete job -l 'app.kubernetes.io/name in (restore,restore-claims)' --ignore-not-found --wait
helm template ospreyflow deploy/helm/ospreyflow -n <namespace> -f <render>/values.yaml \
  --set backups.restore.set=<set> --show-only templates/backups.yaml \
  | kubectl -n <namespace> apply -f - --selector='app.kubernetes.io/name in (restore,restore-claims)'
for j in $(kubectl -n <namespace> get jobs -l 'app.kubernetes.io/name in (restore,restore-claims)' -o name); do
  kubectl -n <namespace> wait --for=jsonpath='{.status.conditions[0].status}'=True "$j" --timeout=6h
  kubectl -n <namespace> logs "$j" --all-containers | tail -3     # each step says what it did, or why not
  kubectl -n <namespace> get "$j" -o jsonpath='{.status.succeeded}' | grep -qx 1 \
    || { echo "$j did not finish: start nothing; read its log (below, If it fails)"; break; }
done
# 4. Only when every Job finished: start each again at the copy count noted in step 2, ArcadeDB first,
#    then the backups resumed.
kubectl -n <namespace> scale statefulset/arcadedb --replicas=1
kubectl -n <namespace> rollout status statefulset/arcadedb
kubectl -n <namespace> scale deployment/<each one noted> --replicas=<as noted>
for c in ospreyflow-backup ospreyflow-backup-claims; do
  kubectl -n <namespace> patch cronjob "$c" -p '{"spec":{"suspend":false}}' 2>/dev/null
done
```

**Where the data is if a restore stopped part-way.** Each store keeps its live data until the restored copy
is in place, and says where each is if it stops between:

- **ArcadeDB** (on its `databases-arcadedb-0` claim): the restore writes `<database>.restoring` beside the
  live `<database>`, then renames the live one to `<database>.before` and the restored one into its place,
  and removes `<database>.before` last. A restore that stopped between the two renames leaves
  `<database>.before` holding the old data, and the next restore refuses until it is dealt with: in a pod
  of ArcadeDB's image mounting that claim (as the restore Job does), if `<database>` is missing, rename
  `<database>.before` back to `<database>`; if both are there, the swap finished and `<database>.before` is
  the old copy, to remove.
- **ClickHouse**: the restore writes `<database>_restoring_<set>`, renames the live one to
  `<database>_before_<set>` and the restored one into its place, and drops `<database>_before_<set>` last.
  If the second rename is refused, the live one is renamed back and the restore refuses, naming the
  restored copy it kept (`<database>_restoring_<set>`, to drop); if even that rename back fails, it says the
  live data is in `<database>_before_<set>`: `RENAME DATABASE <database>_before_<set> TO <database>`.
- **The claims**: each claim's old contents are moved into `.osprey-before/` on the claim, then the set's
  moved in from `.osprey-restore/`, and `.osprey-before/` removed last. A failure between says where each
  is, and the next restore refuses while `.osprey-before/` is there: move its contents back, or remove it
  once the set's are all in place.

**An upgrade that brings the backups in.** First the namespace's Terraform, with `backups.tf`, is applied
(the platform team's pull request): ClickHouse cannot start without its backup role's service account and
the `ospreyflow-clickhouse-backup` Secret it makes. Then: the render gives ArcadeDB's StatefulSet a third
claim template (`backups`), which Kubernetes refuses to change in place, so before the `helm upgrade` that
brings it the StatefulSet is orphaned and its pods restarted one at a time:

```bash
kubectl -n <namespace> delete statefulset arcadedb --cascade=orphan
helm upgrade …   # as the install's runbook says
kubectl -n <namespace> delete pod arcadedb-0      # in production, then arcadedb-1 and arcadedb-2, each once ready
```

### Measured

Measured on a two-node test cluster (4 GB a node, Calico enforcing the policies, the platform's storage
class) against a stand-in for S3, STS and KMS that refuses what they refuse, on 11 November 2026. The data
is synthetic: 5,000 vertices and 1,000 edges, 200,000 ClickHouse rows, and 301 files (7.7 MB) on the
Ingest claim; the set was 9.6 MB in 17 objects. These are what that cluster did, not a service level: the
platform's disks, network and S3 differ, and a real database is larger.

| Path | Measured | What dominates it |
| --- | --- | --- |
| **Backup** (both runs of one slot) | **7.1 s** | the Jobs' start; ArcadeDB's and ClickHouse's own work took about 1.4 s |
| Stopping ArcadeDB and the claims' pod | 31.3 s | ArcadeDB's graceful stop |
| **The restore's two Jobs** (in parallel, `verify` first in each) | **16.5 s** | the pods' start and the verify; the restore itself under a second |
| Starting ArcadeDB and the claims' pod again | 23.0 s | ArcadeDB's start and readiness |
| **End to end, destroyed → restored and compared** | **70.8 s** | stopping and starting, not data |

**What the 70.8 s leaves out.** One pod stood for the Conduit and the workers; the real Conduit, workers
and report sync are stopped and started around the restore too, and their start (the Conduit's above all)
adds to it, as does the managed database's point-in-time restore. At this size the data is negligible and
the restore is the stores' stop and start; a real restore's time grows with the set. Measure it again on
the client's development namespace (decision 13's rehearsal) before production holds real data.

**Consistency.** The CronJob does not stop the Conduit: ArcadeDB's backup is consistent within the graph
and ClickHouse's within each table, but the parts are taken minutes apart. A load running across 02:15
can be in one part and not another. Take a backup with the Conduit stopped where that matters (before an
upgrade, above).

### If it fails

- **`restore: see what runs: … still running`**: stop every writer it names first (step 2); nothing was
  touched.
- **`restore: see what runs: cannot confirm the writers are stopped`**: the restore's pods could not ask the
  cluster's API which pods run (its answer is in the message: a 403 is the Role not bound to the backups'
  service account, a timeout the namespace's egress to the API), or no writers were named; nothing was
  touched. It never proceeds unconfirmed.
- **`restore: verify set …: … is missing` or `is not the file the set wrote`**: a part of that set has
  expired or changed; restore another set. Nothing was touched.
- **`restore: read set …: its manifest is malformed`**: the manifest is not one the runner wrote; restore
  another set. Nothing was touched.
- **`restore-graph refused: …; the live database … was not touched`**: ArcadeDB's restore of the zip
  failed, or the restored copy was not the set's (the check names the file); ArcadeDB's database is as it
  was. Restore another set, or the same one again once the cause is fixed (a full claim, say).
- **`restore-graph refused: <database>.before is there`**: a restore stopped between its renames; see
  *Where the data is* above before restoring again.
- **`Backup S3 requires 1 or 3 arguments`**: a statement handing ClickHouse a session token. ClickHouse
  25.8 takes none; it writes as its own role by its own pod (`ospreyflow-backup-clickhouse`).
- **ClickHouse `Access Denied` at once, its log showing `sts.us-east-1`**: its pod lacks
  `AWS_DEFAULT_REGION`, so its web identity client asked the wrong region's STS, outside the namespace's
  egress, and wrote anonymously.
- **`claims: wait for set …'s claims part: none after … s`**: the claims run for that slot failed or
  never ran; the set is unfinished. Read `ospreyflow-backup-claims-<slot>`'s log.
- **A Job pending, `didn't match pod affinity rules`**: the backup runs beside `arcadedb-0` (its backups
  claim) and the claims run beside the shared pods; neither starts while those are down (above, for the
  claims run when they are stopped on purpose).
