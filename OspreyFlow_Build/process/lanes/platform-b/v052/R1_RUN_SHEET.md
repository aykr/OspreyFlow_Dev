# Step 6 (`v052-r1`) · the install test on the candidate · run sheet

Prepared offline on 14 November 2026 by platform-b, on `lane/platform-b-v052-r1` (main 78564d2 merged in). The day is
**Wed 18 Nov** (the owner's cut moved to Thu 19, 14 November; it was the 25th). ROUTE_052's brief: install v0.5.1, upgrade to the
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
| This lane's dashboards check, offline | 43 tests pass; each access assertion and fix shown red at its own site (14 plants, then 6 for the RLS read) | `r1-review-tests.txt`, `r1-review-red-first.txt`, `r1-rls-red-first.txt` beside this sheet |
| Spec 08 on poc (`spec08_poc.py table`) | **12 of 27 run, 15 skipped**, all for "no seed path on poc" | see "Waits on the owner" below |
| Entra's signing stand-in (platform's v052-standin) | on main | `progress.tsv` done |
| The OpenSearch domain stand-in (platform's v052-searchkind) | on main | `progress.tsv` done |
| RDS stand-in at the Terraform's `max_connections` | on main (`r1_kind_standins.yaml`, the render's own figure) | — |
| Decommission keep or destroy (audit ruling 3) | in: `DECOMMISSION.md` refuses until `BACKUPS` is `keep` or `destroy` | `runbooks.py:540–562` |

## What has to be true before the day

0. **case-b's install-pending branch merged** (lane/case-b-install-pending, b68f4c5): `spec08_live.sh` and
   `spec08_reds.sh`, rows 7b and 7c.
1. **Rules' index feed (3c) and studio's search service (3d) merged.** `managed.opensearch` fails without them: its
   reader is the api pod's `SEARCH_PROBE` through rules' search client. Both are in review today.
2. **This branch merged**: the dashboards check is how `entra.superset`, `entra.report-sync`, both workloads and
   Superset's own database are exercised before `verify`.
3. **R1's settings switch reporting on: done** (platform's r1reporting, 87d1689, on main). The dashboards check
   gives the report sync INSTALL step 6a's own value, `{client_id, secret}`, through the Secret (the run's Terraform
   stand-in holds `[]`).
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
   - **Rules' B stack, kept up under a long lease for step 4 (23 Nov), must be down before the run** (by the evening of
     Tue 17 now that the run is on the 18th: to confirm with the orchestrator), or the node cannot be given its 32.
8. **Platform's two R1 fixes: done** (r1upgrade on main, the fix 326356a, its record e00a09c).
   - `runbook INSTALL` renders the candidate's own copy every time. Another release's kept render is set aside as
     `render.before-upgrade` and never run, and the candidate's render is the kept one after.
   - `BACKUPS=destroy` is modelled, with its refusals before anything is touched: a second destroy, a key already
     pending deletion, no key, a bucket still holding files.
9. **The lease and the server's Docker.**
   - R1's notes say kind needs no stack lease, and that the server's Docker is the orchestrator's to give.
   - case-b's driver says its live half runs under a lease.
   - The full suite's live jobs do need a stack lease, and **this session's `stack_lease.sh acquire` is refused by its
     permission check** (as for 4c): the owner gives the word or runs that part.

## The run, in order

**The cluster and its state are platform-b's for the day.** `osprey-r1` and R1's state folder
(`~/osprey-runs/platform.r1`: `state.json`, the kept render `KEPT`, `records/`) are one per server; another lane's R1
run overwrites `KEPT`, which the verifier's `--candidate auto` reads. The orchestrator gives platform-b both for the
25th, and no other lane runs R1 that day.

**Two copies run it, each named in the table.**
- **Copy A** is a worktree at v0.5.1's tagged commit: **477a500** today. If the owner takes MORNING's option (a), the
  tag moves to a later commit in both repositories, and copy A is made at the commit the tag names on the day.
  ROUTE_052 names 9197ea6 as v0.5.1's cut; the tag sits on 477a500, which is 9197ea6 plus the CHANGELOG's fixes from
  the upgrade rehearsal (7d76022, 477a500).
- **Copy B** is the candidate's worktree.

Each copy is sent by `stack_lease.sh remote platform-b …` (from the repository root). Within a copy, commands run
from `OspreyFlow_Core` with `G=../OspreyFlow_Build/process/lanes/platform/gates`,
`L=../OspreyFlow_Build/process/lanes/platform-b/v052` and `D=../OspreyFlow_Build/process/lanes/case-b/v052`.
**Rows 2b to 10 are one `stack_lease.sh remote` command of copy B**, so `--candidate auto` finds the upgrade's commit
(case-b's README). **"After a fix" means rows 4 to 10 again** in one such command (row 2b's snapshot stands, since the
fix is the candidate's). The board's slug is found again on a rerun rather than refused.

My scripts run only through `$L/r1_live.sh`, which gives them R1's own environment (its pinned kubectl, its
kubeconfig, the kind platform's folder, the checkout's Python). Every kubectl call they make names R1's namespace.

| # | Copy | Command | What it shows | Record |
| --- | --- | --- | --- | --- |
| 0 | A | `bash $G/r1_kind.sh tools`, then `up`, then `py platform` | the cluster (a 32 GiB node), the stand-ins, the domain's engine | R1's |
| 1 | A | `bash $G/r1_kind.sh py runbook INSTALL` | v0.5.1 installed by its own runbook | `INSTALL-v051.log` |
| 2 | A | `bash $G/r1_kind.sh py check` | R1's checks on v0.5.1 (34 on 13 Nov: the door, the Entra refusals, the first administrator, a case, a hotlist, a load, its alert). It leaves a case, a hotlist, a load and its alert. | `check-v051.log` |
| 2b | B | `bash $L/r1_live.sh survival snap` | **v0.5.1's own data, read before the upgrade**: the case R1's check saved, its hotlist, what search finds of the load, the alert, the Ingest claim's files. Kept as `v052-pre-upgrade.json` in R1's state folder, where a later `check` cannot overwrite it. | `survival-snap.log` |
| 3 | B | the backup first, as the guide's upgrade paragraph says: the runbook's *Before an upgrade* (the Conduit, the workers and the report sync stopped, each copy count noted), then *A backup now* (`py backup`), then the set's `manifest.json` checked | one finished set before the upgrade | `backup-pre.log` |
| 4 | B | **the upgrade**: `bash $G/r1_kind.sh py runbook INSTALL` again (Q1: the client's way), block by block, then the copy counts from row 3 restored if the install has not | `helm upgrade --install` of the candidate over v0.5.1, then INSTALL's own checks as the guide names them: **section 6's check that the Conduit reads Entra's settings, and section 7's `/healthz` through the Glass** | `UPGRADE.log` (see row 14) |
| 4b | B | `bash $L/r1_live.sh survival verify` | **v0.5.1's data survived**: row 2b's case, hotlist, load (search finds the same), alert and files, each PASS or FAIL. It runs before row 5, whose `check` saves a new case over the old. | `survival.log` |
| 5 | B | `bash $G/r1_kind.sh py check` | R1's checks on the candidate. It makes its own new case: what it shows is that the candidate works, not that v0.5.1's data survived (that is row 4b). | `check-candidate.log` |
| 6 | B | `bash $L/r1_live.sh dashboards run` | Superset's sign-in through Entra for each role; building (Admin and Alpha may, Gamma may not); the report sync's identity and its first pull; the embed. **The board's rows through the guest token** (its row-level security is this read path's access control, rules 3 and 4): a chart on the mart's `figures`; another identity's row (counted at SECRET) planted through the managed PostgreSQL and removed again; the guest token reads the identity's own rows and only them, while an administrator's own session sees both (the control). **Every refusal `may_open` makes is asked**: no reports right (403 for the listing and the token); no level on the identity's case, another unit, and a lower clearance (each offered nothing, 404). | `dashboards.log` |
| 7 | B | `bash $L/r1_live.sh spec08 run` (the module unchanged; dispositions both ways) | 12 of 27 run (or more once the seed path lands) | `spec08.log` |
| 7b | B | `bash $D/spec08_live.sh -k "door_opens or stream_opens_through_the_proxy or unknown_field_name_is_refused"` (case-b's, at the orchestrator's request: spec 08's two seed-free halves on poc) | **3 passed**, the rest deselected (A7's refusal is exactly 422, `{"error": "field_name_refused", "detail": <the field-name rule>}`, the hostile name never echoed, and the same request without it 200: rules-b's analytics-field fix on main): the analyst's door; the stream through the proxy with a ticket (ticket, upgrade, an empty snapshot through the poc ingress, and the first meeting of ADR-148 Am 8's Entra socket check); A7's unknown field name refused, not ignored | `spec08-halves.log` |
| 7c | B | `bash $D/spec08_reds.sh` (case-b's) | **both halves red when planted, green as built**: A7 with the hostile field name made safe goes red, "a field name carrying SQL was not refused in words: 200"; the stream asking `?token=` for its `?ticket=` goes red; then row 7b green again. Each planted copy is written beside the module and removed on exit. | `spec08-reds.log` |
| 8 | B | `py backup`, `py change`, `py restore --set <the set>`, `py restored`; then, for each CronJob the manifest lists as held suspended (`ospreyflow-search-rebuild`, `ospreyflow-search-drift`), `kubectl -n ospreyflow-poc create job --from=cronjob/<name> <name>-r1` and wait on it | a set; a change after it; the restore taking the change away and bringing the set back; and every job the manifest lists run once. The backups' two CronJobs run through `py backup`, and the restore's two Jobs through `py restore`. A bucket nothing wrote fails, by design. | `restore.log`, `jobs.log` |
| 9 | B | `bash $D/verify_live.sh` (`install_verify.py verify --candidate auto`) | **every manifest entry, 50 checks** (see "What verify does not check") | `verify.log` |
| 10 | B | `py memory` | the node's and every pod's working set after all of it | `memory.log` |
| 11a | B | `R1_BACKUPS=unset bash $G/r1_kind.sh py runbook DECOMMISSION`, with `BACKUPS` unset (platform's r1upgrade, 326356a: without `R1_BACKUPS=unset`, R1 still gives `keep` for 30 days, and `R1_BACKUPS=unset` beside a set `BACKUPS` is refused) | **the operator must choose** (audit ruling 3): blocks 1 to 6 run, then step 7 meets the product's own words, "BACKUPS: choose keep or destroy for the backups bucket and its key (there is no default)", and touches nothing of step 7 | `DECOMMISSION-unchosen.log` |
| 11 | B | `BACKUPS=keep BACKUP_RETENTION_DAYS=30 bash $G/r1_kind.sh py runbook DECOMMISSION --from 7` | the keep path: step 8's check names only the kept backups bucket and key | `DECOMMISSION-keep.log` |
| 11b | B | **a fresh install of the candidate, proven as the upgraded one is** (the orchestrator, 14 November: the client may install v0.5.2 directly), as **one `stack_lease.sh remote` command of copy B**, so `--candidate auto` finds this install's commit: the cluster made again (`r1_kind.sh down`, then `up` and `py platform`: a keep leaves the backups bucket and key, and a destroy is final on the stand-in, as on AWS), `py runbook INSTALL`, R1's checks (`py check`), then `bash $D/verify_live.sh` (every manifest entry, 50 checks) and `bash $L/r1_live.sh spec08 run` with rows 7b and 7c's two halves and their reds | the candidate installed fresh passes what the upgraded one passed (rows 5, 7 to 7c and 9) | `INSTALL-fresh.log`, `check-fresh.log`, `verify-fresh.log`, `spec08-fresh.log` |
| 11b′ | B | **the token version, live** (ADR-148 Amendment 18): `R1_ENTRA_TOKEN_VERSION=1.0 bash $G/r1_kind.sh py platform` (the stand-in issues the API's tokens as v1.0, platform's 15f3ea9), then `kubectl -n ospreyflow-poc rollout restart deploy/api` and wait on it (the stand-in's key is new at each start, and a key the Conduit does not hold yet gives the plain refusal, never the words); one Glass sign-in (`py check`, expected to stop at its first sign-in); then INSTALL step 6's token-version block; then `bash $G/r1_kind.sh py platform` without the variable (2.0 again) and the Conduit restarted again | the sign-in refused in Amendment 18's words ("issues v1.0 access tokens … set requestedAccessTokenVersion to 2 …"), and step 6's block stopping with the same words from the Conduit's log; then 2.0 again, a sign-in resolving | `tokver-live.log` |
| 11c | B | one set taken (`py backup`), then `BACKUPS=destroy bash $G/r1_kind.sh py runbook DECOMMISSION` | the destroy path in step 7's own order (platform's model, 326356a): the bucket's policy, every object, then the bucket; the key's policy left to the account's administration alone and its deletion scheduled 30 days out; then the Terraform's removal. Step 8's check then says **"backups: destroyed"**, and the S3 stand-in refuses every use of the key (`KMS.KMSInvalidStateException`). | `DECOMMISSION-destroy.log` |
| 12 | B | `bash $G/r1_kind.sh down` | nothing of the run left | — |
| 13 | B | **the full suite once**, through `stack_lease.sh offline` (Q4): `make ci`'s offline gates and `make test` | "the full suite runs once, at step 6" | `suite.log` |
| 13b | — | what offline cannot run (Q4): CI's `conformance` (ArcadeDB, ClickHouse, Valkey and Postgres; the live store tests, the Entra people and access-store live files among them), `conformance-model` and `-vision`, `six-screen-live-exit-test`, and the nine `trivy-image-*` scans (each builds an image) | CI's run on the candidate's **exact** commit is their evidence (the orchestrator, 14 Nov), recorded here by its run id on the day | `suite-ci-run.txt` (the run id, its commit, each job's result) |
| 14 | — | **with the commit that records `UPGRADE.log`**: the guide's §6a.1 *What will check it.* rewritten from what was planned to what ran (the date, v0.5.1 then the candidate over it, row 4b's result, the record's path), and its "It has not run yet." removed. **Docs commits the guide's sentence** (the guide is docs'); the orchestrator merges the two together. | docs' docs' guide test for §6a.1 (`test_guide_6a_upgrade.py`, on lane/docs-6a-upgrade) goes red the moment any `UPGRADE.log` is under `process/` while the paragraph still says it has not run (docs' correction 1, 14 Nov) | docs' commit, merged with the record |

A failing block stops the run, and its record names it. After a fix, `runbook … --from N` reruns the affected part.
Every record goes to `process/lanes/platform-b/v052-r1/run/`, and every measurement says the lease it was taken
under.

**What verify does not check** (case-b's README), so the day does not claim it:
- **An Entra registration's** `kind`, `redirect`, `grants`, `exposes` and `app_roles`. These are the client
  administrator's words. The stand-in enforces platform's own registrations, not the manifest's.
- **`managed.rds.point_in_time_days`**: only AWS shows it, and the render check holds it.
- **That the candidate came by an upgrade at all.** A fresh install of it passes alike. Rows 2b and 4b are what show
  it did, with v0.5.1's data kept.

**Time, an estimate.** R1's own run of 13 Nov took about 12 minutes from its INSTALL log to its decommission log
(`process/lanes/platform/r1/run/20261113T175844Z-INSTALL.log` to `…/20261113T181017Z-DECOMMISSION.log`, 11 min 33 s, the cluster already up). The
day adds the following:
- a second INSTALL as the upgrade;
- the dashboards check and spec 08;
- the jobs and the verify;
- the unchosen decommission;
- a second platform and install for the destroy path.

So allow **most of the day**, and the full suite on top: about 80 minutes for CI's run, from its recent runs on main,
not measured here.

## The day plan (Wed 18 Nov), in order, with times

**M** is measured: R1's own records of 13 November, `process/lanes/platform/r1/run/`, on a warm cluster with our
images already built (INSTALL 17:58:44 to its check 18:04:25; the check to the restore's record about 1.5 min; the
decommission about 4 min). **E** is an estimate, never measured: chiefly the cold builds of our images, which R1's
records do not time.

| Start (UTC) | Rows | What | Time | Basis |
| --- | --- | --- | --- | --- |
| 08:00 | — | the server checked first: rules' B stack down (Q5), osprey-r1 and R1's state folder ours, the load low, nothing of `osprey-upg` or another lane's R1 left | 10 min | E |
| 08:10 | 0 | copy A: `tools`, `up`, `py platform` (the cluster, Calico, ingress, the stand-ins, the domain's engine image built) | 20–30 min | E |
| 08:40 | 1 | copy A: v0.5.1's INSTALL. Its step 3 builds and pushes our images cold | 35–50 min | E (warm: ≤ 6 min, M) |
| 09:30 | 2 | copy A: R1's checks on v0.5.1 | 3–5 min | E (inside M's 6) |
| 09:35 | 2b–10 | **copy B, one `stack_lease.sh remote` command:** | | |
| | 2b | `survival snap` | < 1 min | E |
| | 3 | *Before an upgrade*, then *A backup now* | 2–3 min | M (backup + restore ≈ 1.5 min) |
| | 4 | the upgrade: INSTALL again. Its step 3 builds the candidate's images cold | 35–50 min | E |
| | 4b | `survival verify` | < 1 min | E |
| | 5 | R1's checks on the candidate | 3–5 min | E |
| | 6 | the dashboards check: the report sync's restart and first pull wait up to 10 min, then sign-ins, building, the chart and RLS reads, the refusals | 15–25 min | E |
| | 7, 7b, 7c | spec 08 (12 cases), its two seed-free halves, and their reds | 20–30 min | E |
| | 8 | backup, change, restore, restored, and the two suspended CronJobs once each | 5–10 min | M for the backup and restore, E for the jobs |
| | 9 | `verify_live.sh`, 50 checks | 5–10 min | E |
| | 10 | memory | 1 min | E |
| ~11:30 | — | copy B's command ends. Its records are read **before going on**: a FAIL anywhere means a fix, then rows 4 to 10 again (another 1.5–2 h) | 15 min | E |
| 11:45 | 11a, 11 | the unchosen decommission (blocks 1 to 6, then the refusal at 7), then keep from 7 | 8–10 min | M (≈ 4 min) + E |
| 12:00 | 11b | **one remote command of copy B:** the cluster made again (down, up, platform), INSTALL fresh from copy B (images cold again, the registry gone with the cluster), R1's checks, then verify (50 checks) and spec 08 with its two halves and their reds on the fresh install | 120–160 min | E (the install and platform as before; verify and spec 08 as rows 7 to 9) |
| 14:30 | 11b′ | the token version live: the stand-in at v1.0, the Conduit restarted, one sign-in refused in the words, step 6's block, then 2.0 again | 15–20 min | E |
| 14:50 | 11c | a set, then destroy | 10 min | M (≈ 4 min for a decommission) + E |
| 15:00 | 12 | `down`, nothing of the run left | 5 min | E |
| 15:05 | 13 | the full suite offline: `make ci`'s gates and `make test`, through `stack_lease.sh offline` | 60–90 min | E (CI's own run on main is about 80 min) |
| 16:35 | 13b, 14 | the CI run on the candidate's exact commit recorded by id; `UPGRADE.log` committed with docs' guide sentence (row 14) | 15 min | E |
| ~16:50 | — | the report to the orchestrator: every row's record, the leases each ran under | 15 min | — |

**Start at 08:00 sharp, and if a fix is needed after about 13:00, tell the orchestrator before rerunning** (the orchestrator, 14 November: a FAIL costs 1.5 to 2 h, and the 15:30 finish has little slack). **About 8.75 h with no fix**, ending about 16:50 (the token version's live row adds about 20 min); the fresh install's verify and spec 08 (row 11b) add about 50 min to the plan of 14 November. A failure in copy B's command costs one more pass of rows 4 to 10,
about 1.5 to 2 h, and the day still ends within it. Row 13 does not touch the cluster, but it is kept until after row
12 because both load one server (a 32 GiB node and the suite's workers). The two cold builds (rows 1 and 4) are the
largest unknowns: their real times go in the record and replace these estimates for the next release's run.

## Answered by the orchestrator (14 November)

- **Q1. The upgrade:** the client upgrades by re-running INSTALL's `helm upgrade --install` from the new release's
  copy, with the backup first. The §6a text started as `guide-6a-upgrade.diff` beside this sheet; **docs owns it
  now** (lane/docs-6a-upgrade, with its corrections and docs' guide test for §6a.1 (`test_guide_6a_upgrade.py`, on lane/docs-6a-upgrade)), to land before the
  freeze (Tue 24).
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
- **platform:** `r1_kind_osprey.yaml` switches reporting on and names `superset_client_id` (item 3). **Done**,
  87d1689.

From the orchestrator's review of this branch (14 November):
- **platform (sent by the orchestrator):** must 1, `render_back`; and the destroy path's stand-in (row 11b). **Done**,
  326356a.
- **docs (for the orchestrator to relay):** the upgrade paragraph's step order. The new release's Terraform is
  rendered with its own copy's render, in step 3 (`terraform/` comes from the unpinned render), so "its pull
  request is applied before the install" belongs after step 3's render, not in step 2. The paragraph in
  `guide-6a-upgrade.diff` was mine, and the order was wrong in it.
- **platform-b, the RLS read: done** (the orchestrator, 14 November: it is a read path, so not a carry). The guest
  token's chart data is read in row 6, with the identity's rows only and another identity's row absent. Built
  red first: `r1-rls-red-first.txt`, six plants.
