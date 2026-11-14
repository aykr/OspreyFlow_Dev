# Step 6 (`v052-r1`) · the install test on the candidate · run sheet

Prepared offline on 14 November 2026 by platform-b, on `lane/platform-b-v052-r1` (main 78564d2 merged in). The day is
**Wed 25 Nov** (`route.tsv` step 6, after step 5's freeze). ROUTE_052's brief: install v0.5.1, upgrade to the
candidate, **verify every manifest entry**, run spec 08's scenarios that apply to the shape, then decommission, with
the operator choosing keep or destroy for the backups. "The full suite runs once, at step 6."

**Tools.** Each is someone else's, used unchanged here:
- R1's kind cluster and runbook runner (`process/lanes/platform/gates/r1_kind.sh`, `r1_kind.py`), from platform;
- the manifest verifier and spec 08's runner (`process/lanes/case-b/v052/`), from case-b;
- this lane's dashboards check (`process/lanes/platform-b/v052/dashboards_check.py`).

Nothing touches osprey-small.

## Where things stand today (14 Nov), offline

| What | State | Evidence |
| --- | --- | --- |
| The verifier's plan on main's manifest | **50 checks, none pending**, so the run needs no `--allow-pending` | `install_verify.py plan` |
| case-b's driver tests | 215 passed, 1 skipped, **1 failed**: `test_an_entry_still_pending_stops_the_run_unless_a_dry_run_allows_it` | see "Carried" below |
| This lane's dashboards check, offline | in the same pytest run; passes | `process/lanes/platform-b/v052/` |
| Spec 08 on poc (`spec08_poc.py table`) | **12 of 27 run, 15 skipped**, all for "no seed path on poc" | see "Waits on the owner" below |
| Entra's signing stand-in (platform's v052-standin) | on main | `progress.tsv` done |
| The OpenSearch domain stand-in (platform's v052-searchkind) | on main | `progress.tsv` done |
| RDS stand-in at the Terraform's `max_connections` | on main (`r1_kind_standins.yaml`, the render's own figure) | — |
| Decommission keep or destroy (audit ruling 3) | in: `DECOMMISSION.md` refuses until `BACKUPS` is `keep` or `destroy` | `runbooks.py:540–562` |

## What has to be true before the day

1. **Rules' index feed (3c) and studio's search service (3d) merged.** `managed.opensearch` fails without them: its
   reader is the api pod's `SEARCH_PROBE` through rules' search client. Both are in review today.
2. **This branch merged**: the dashboards check is how `entra.superset`, `entra.report-sync`, both workloads and
   Superset's own database are exercised before `verify`.
3. **R1's settings switch reporting on (platform's file, not changed here).**
   - `gates/r1_kind_osprey.yaml` has no `reporting` and no `superset_client_id` today.
   - Without them, Superset and the report sync are not rendered on kind, and the manifest's `workloads.superset`,
     `workloads.report-sync`, `entra.superset`, `entra.report-sync` and `managed.rds.databases.superset` all fail.
   - **Carry for platform.**
4. **case-b's pending-entry test fixed** (carried below), so the driver's own suite is green on the day.
5. **The seed path ruled** (`MORNING.md` item 2: ADR-148 Am 14, SECRET items against poc's ceiling).
   - Until it lands, spec 08 runs 12 of its 27 cases on poc.
   - With (a) or (c), the runner's dispositions change: case-b's `spec08_poc.py`, dispositioned both ways, stops the
     run until someone places each newly runnable case.
6. **The v0.5.1 commit to install.** The release is blocked on the owner's trivy decision (Superset's dnspython).
   - Kind does not need the published release: R1's INSTALL pins images from the cluster registry's own copies.
   - It needs the developer-repository commit v0.5.1 was cut from: **477a500**, unless the orchestrator says
     otherwise.
7. **Server memory.**
   - R1's node is capped at 32 GiB, beside osprey-small (about 24) on the 62 GiB server.
   - **Rules' B stack, kept up under a long lease for step 4 (23 Nov), must be down by the 25th**, or the node cannot
     be given its 32.
8. **The lease and the server's Docker.**
   - R1's notes say kind needs no stack lease, and that the server's Docker is the orchestrator's to give.
   - case-b's driver says its live half runs under a lease.
   - The full suite's live jobs do need a stack lease, and **this session's `stack_lease.sh acquire` is refused by its
     permission check** (as for 4c): the owner gives the word or runs that part.

## The run, in order

From the server's copy (`stack_lease.sh remote platform-b …`, from the repository root), with
`G=../OspreyFlow_Build/process/lanes/platform/gates` and `D=../OspreyFlow_Build/process/lanes/case-b/v052`.

| # | Command | What it shows | Record |
| --- | --- | --- | --- |
| 0 | `bash $G/r1_kind.sh tools`, then `up`, then `py platform` | the cluster (32 GiB node), the stand-ins, the domain's engine | R1's |
| 1 | **from a copy at v0.5.1 (477a500, its tagged commit)**: `bash $G/r1_kind.sh py runbook INSTALL` | v0.5.1 installed by its own runbook | `INSTALL-v051.log` |
| 2 | v0.5.1's `bash $G/r1_kind.sh py check` | R1's 28 checks on v0.5.1; leaves a case, a hotlist, a load and its alert to find after the upgrade | `check-v051.log` |
| 3 | *A backup now* before the upgrade (the guide §6a.8: Conduit and workers stopped, copy counts noted): `py backup` | one finished set before the upgrade | `backup-pre.log` |
| 4 | **the upgrade, from the candidate's copy**: `bash $G/r1_kind.sh py runbook INSTALL` again (Q1: the client's way) | `helm upgrade --install` of the candidate over v0.5.1 | `UPGRADE.log` |
| 5 | `py check` on the candidate | step 2's case, hotlist, load and alert still there; R1's 28 again | `check-candidate.log` |
| 6 | `python ../OspreyFlow_Build/process/lanes/platform-b/v052/dashboards_check.py run` | Superset's own browser sign-in through Entra, the embed, the report sync's identity | `dashboards.log` |
| 7 | `python $D/spec08_poc.py` (the module unchanged; dispositions both ways) | 12 of 27 run (or more once the seed path lands) | `spec08.log` |
| 8 | `py backup`, a change, `py restore`; then `kubectl create job --from=cronjob/<name>` for each CronJob held suspended | a set, a restore, and every job run once (a bucket nothing wrote fails by design) | `restore.log`, `jobs.log` |
| 9 | `bash $D/verify_live.sh` (`install_verify.py verify --candidate auto`) | **every manifest entry, 50 checks**; must run in the **same** `stack_lease.sh remote` command as step 4, so `auto` finds the candidate | `verify.log` |
| 10 | `py memory` | the node's and every pod's working set after all of it | `memory.log` |
| 11 | `py runbook DECOMMISSION` with `BACKUPS=keep` | the decommission as written; its check names only the kept bucket and key | `DECOMMISSION-keep.log` |
| 11b | the platform again, a fresh install (`py platform`, `py runbook INSTALL` from the candidate's copy), a set taken, then `py runbook DECOMMISSION` with `BACKUPS=destroy` | the other path of audit ruling 3: the bucket and key destroyed, the check naming nothing left (Q3: both proven) | `DECOMMISSION-destroy.log` |
| 12 | `bash $G/r1_kind.sh down` | nothing of the run left | — |
| 13 | **the full suite once**, on the candidate, through `stack_lease.sh offline` (Q4): `make ci`'s offline gates and `make test` | "the full suite runs once, at step 6" | `suite.log` |
| 13b | what offline cannot run (Q4): CI's `conformance` (ArcadeDB, ClickHouse, Valkey, Postgres: the live store tests, the Entra people and access-store live files among them), `conformance-model` and `-vision`, `six-screen-live-exit-test`, and the nine `trivy-image-*` scans (each builds an image) | named to the orchestrator; CI's run on the candidate's commit is their record unless a stack is given | — |

A failing block stops the run, and its record names it. After a fix, `runbook … --from N` reruns the affected part.
Every record goes to `process/lanes/platform-b/v052-r1/run/`, and every measurement says the lease it was taken
under.

**Time.** R1's own run (13 Nov) took about an hour from INSTALL to the decommission. With a second INSTALL as the
upgrade, the dashboards, spec 08, the jobs, the verify and a second install for the destroy path, allow **most of the day**, and the full suite on top (about
80 minutes on CI's runners).

## Answered by the orchestrator (14 November)

- **Q1. The upgrade:** the client upgrades by re-running INSTALL's `helm upgrade --install` from the new release's
  copy, with the backup first. The §6a text is `guide-6a-upgrade.diff` beside this sheet, for docs to land before
  the freeze (Tue 24).
- **Q2. The v0.5.1 commit:** 477a500, v0.5.1's tagged commit.
- **Q3. Keep or destroy:** both are proven, on two decommissions (rows 11 and 11b): audit ruling 3 requires the
  choice and its record.
- **Q4. The full suite:** offline on the server through `stack_lease.sh offline`, which needs no acquire. The parts
  that need a stack or Docker are named in row 13b.
- **Q5. Rules' B stack:** up for step 4 (Mon 23) and the freeze (Tue 24), down by Tue 24 evening.

## Carried (other lanes' files: diffs or words, never changed here)

Both carries were taken by the orchestrator on 14 November, which told case-b and platform.

- **case-b:** `test_install_verify.py::test_an_entry_still_pending_stops_the_run_unless_a_dry_run_allows_it` asserts
  that *main's* manifest still has pending entries. It stopped being true when step 3b landed (14 Nov), so it fails
  whatever the code does. It should plant a pending entry in a copy of the manifest, as the module's other plants do,
  and keep its two asserts.
- **platform:** `r1_kind_osprey.yaml` switches reporting on and names `superset_client_id` (item 3).
