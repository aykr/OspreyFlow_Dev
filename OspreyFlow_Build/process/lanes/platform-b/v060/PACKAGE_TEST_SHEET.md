# v0.6.0 #11 · the package test · run sheet

Prepared offline on 15 November 2026 by platform-b, on `lane/platform-b-v060-package-test` (main 7dd860e). **The
package test runs once, at stage 4**, on the commit the orchestrator names then (`OspreyFlow_Core/VERSION` v0.6.0),
once that commit's CI is green. It replaces v0.5.2's step 6 (`process/lanes/platform-b/v052/R1_RUN_SHEET.md`), which
the owner cancelled on the 15th: **one release, v0.6.0, installed fresh**. No v0.5.1, no upgrade, no survival rows.

**The owner's rulings (15 November).**
- A fresh install of v0.6.0 only, on R1's kind cluster on the test server, with its checks kept: **R1's checks, the
  dashboards check, spec 08's scenarios (with the two seed-free halves and their reds), backup and restore, the
  manifest verify, and both decommission routes**.
- **The images are kept when the cluster is made again** (choice (a)): `r1_kind.sh remake` deletes the kind cluster
  alone and keeps its registry container, what it holds, our `localhost:5001/*` images and the node image, so the
  second install builds and pushes warm. `up` says in the record whether it reused the registry or started an empty
  one. `down` stays the only verb that removes the registry. (Platform agreed that platform-b edit its tooling for
  this, 15 November; `tests/test_r1_kind_remake.py`, red first.)
- **Each container's working set over the run is recorded** (item 23, sizes from measured use, is out of v0.6.0;
  the figures are the owner's): `r1_live.sh memory`, every 15 s, from before the install to before the first
  decommission, reported as each container's peak, p95, median, steady state (from the soak's mark), restarts and
  OOMKills, with the node's peak (`process/lanes/platform-b/v060/memory_sampler.py`,
  `tests/test_v060_memory_sampler.py`). Nothing here changes a size.
- **The full suite stays in the Test stage on main**, not in the package test.

**Tools** (each used unchanged but for the two above): R1's kind cluster and runbook runner
(`process/lanes/platform/gates/r1_kind.sh`, `r1_kind.py`, platform's); the manifest verifier and spec 08's runner
(`process/lanes/case-b/v052/`, case-b's); this lane's dashboards check and wrapper
(`process/lanes/platform-b/v052/dashboards_check.py`, `r1_live.sh`) and the sampler.

## Before the run

1. **The candidate**: the orchestrator's message naming the stage 4 commit and its green CI run. One worktree at
   it, clean (`git status` empty): its own `gates/` is main's.
2. **The server**: `/root/osprey-runs/QUEUE` read, platform-b's line first, `pgrep -x make` empty (the owner's rule,
   one full run at a time); nothing of another lane's R1 (`kind get clusters`, `docker ps` for `osprey-r1-*`); the
   load low and the node's 32 GiB free beside osprey-small. **osprey-small is never touched.**
3. **The lease**: platform-b holds a stack (`stack_lease.sh status`); this session cannot run `acquire`, so the owner
   runs it. Every row runs as **`stack_lease.sh remote platform-b -- <command>`** from the candidate's worktree, from
   `OspreyFlow_Core`, with `G=../OspreyFlow_Build/process/lanes/platform/gates`,
   `L=../OspreyFlow_Build/process/lanes/platform-b/v052` and `D=../OspreyFlow_Build/process/lanes/case-b/v052`.
4. **Platform's v060-rf-fresh-only**, if it changes R1's fresh install, merged first (platform is on it).

## The run, in order

**A FAIL anywhere stops the run** (the owner's rule for v0.5.2's step 6, kept): the record is read, the fix made,
and the run starts again from the row the orchestrator names. Every row's output is kept in R1's state folder
(`~/osprey-runs/platform.r1/records/`) and, by `tee`, in this lane's local record of the run.

| # | Command | What it shows | Record |
| --- | --- | --- | --- |
| 0 | `bash $G/r1_kind.sh tools`, `up`, `py platform` | the cluster (a 32 GiB node), the stand-ins, the domain's engine; `registry: osprey-r1-registry started (empty)` | R1's |
| 0m | `bash $L/r1_live.sh memory start` | the sampler running, every 15 s | `memory-sampler.log` |
| 1 | `bash $G/r1_kind.sh py runbook INSTALL`, block by block, then `memory mark installed` | v0.6.0 installed by its own runbook, cold: step 1's fresh-only block passing on the new namespace (platform's `rf`); its step 3 builds and pushes our images; INSTALL's own checks (section 6's Entra settings, section 7's `/healthz` through the Glass) | `INSTALL.log` |
| 2 | `bash $G/r1_kind.sh py check` | R1's checks: the door, the Entra refusals, the first administrator, a case, a hotlist, a load and its alert, and the domain (`search: opensearch`) | `check.log` |
| 3 | `bash $L/r1_live.sh dashboards run` | Superset's sign-in through Entra for each role; building (Admin and Alpha may, Gamma may not); the report sync's identity and its first pull; the embed; the board's rows through the guest token (row-level security, rules 3 and 4), another identity's row never shown | `dashboards.log` |
| 4 | `bash $L/r1_live.sh spec08 run` | spec 08's cases that apply to poc, dispositioned both ways | `spec08.log` |
| 4b | `bash $D/spec08_live.sh -k "door_opens or stream_opens_through_the_proxy or unknown_field_name_is_refused"` | 3 passed (case-b's seed-free halves on poc) | `spec08-live.log` |
| 4c | `bash $D/spec08_reds.sh` | both halves red when planted, green as built | `spec08-reds.log` |
| 5 | `py backup`, `py change`, `py restore --set <the set>`, `py restored`; each CronJob the manifest lists as held suspended (`ospreyflow-search-rebuild`, `ospreyflow-search-drift`) run once by `kubectl -n ospreyflow-poc create job --from=cronjob/<name> <name>-r1` | a set; a change after it; the restore taking the change away; every listed job run once | `backup.log` |
| 6 | `bash $D/verify_live.sh` (`install_verify.py verify --candidate auto`) | every manifest entry (50 checks on 14 November) | `verify.log` |
| 7 | `py memory`; `memory mark soak`; 20 minutes idle; `memory stop`; `memory report --steady-from soak` | the node's and each pod's working set now (R1's snapshot), then the sampler's table over rows 1 to 7: each container's peak, p95, median, steady (the soak), restarts and OOMKills, the node's peak | `memory.log`, `memory-sampled.txt` |
| 8 | `R1_BACKUPS=unset bash $G/r1_kind.sh py runbook DECOMMISSION`, then `BACKUPS=keep BACKUP_RETENTION_DAYS=30 bash $G/r1_kind.sh py runbook DECOMMISSION --from 7` | the operator must choose (audit ruling 3): blocks 1 to 6, then step 7's refusal in the product's words; then the keep path, step 8 naming only the kept bucket and key | `DECOMMISSION-unset.log`, `DECOMMISSION-keep.log` |
| 9 | `bash $G/r1_kind.sh remake`, `py platform`, `py runbook INSTALL`, `py check` | the cluster made again with the registry and images kept (`kept: the registry …`, `registry: osprey-r1-registry kept, reused`); the second INSTALL warm; R1's checks green on it | `remake.log`, `INSTALL-2.log`, `check-2.log` |
| 9b | **the token version, live** (ADR-148 Amendment 18; the orchestrator's ruling, 15 November: a check against a real defect class): `R1_ENTRA_TOKEN_VERSION=1.0 bash $G/r1_kind.sh py entra` (the Entra stand-in alone re-applied, its tokens for the API as v1.0; never `py platform` mid-deployment, which rewrites CoreDNS without the search domain's name and loses OpenSearch until the domain step runs again), then `kubectl -n ospreyflow-poc rollout restart deploy/api` and wait on it (the stand-in's key is new at each start, and a key the Conduit does not hold yet gives the plain refusal, never the words); one Glass sign-in (`py check`, expected to stop at its first sign-in); then INSTALL step 6's token-version block; then `bash $G/r1_kind.sh py entra` without the variable (2.0 again) and the Conduit restarted again, and `py check` green | the sign-in refused in Amendment 18's words ("issues v1.0 access tokens … set requestedAccessTokenVersion to 2 …"), and step 6's block stopping with the same words from the Conduit's log; then 2.0 again, R1's checks green | `tokver-live.log` |
| 10 | `py backup`, then `BACKUPS=destroy bash $G/r1_kind.sh py runbook DECOMMISSION` | the destroy path in step 7's order (the bucket's policy, every object, the bucket; the key's deletion scheduled 30 days out; the Terraform's removal); step 8 says "backups: destroyed" | `DECOMMISSION-destroy.log` |
| 11 | `bash $G/r1_kind.sh down` | nothing of the run left: no `osprey-r1-*` container, the registry and our images gone | — |
| 12 | `memory report` again from the kept record if row 7's was lost; the QUEUE line deleted; the lease released | — | — |

**Not in the package test** (the rulings): the upgrade and survival rows; the full suite (main's Test stage).
The token version's live row came back as row 9b at the orchestrator's ruling (15 November).

## Times

**M** is measured (R1's records of 13 November, `process/lanes/platform/r1/run/`, a warm cluster: INSTALL to its
check about 6 min; the check to the restore about 1.5 min; a decommission about 4 min). **E** is an estimate.

| Rows | What | Time | Basis |
| --- | --- | --- | --- |
| — | the server checked | 10 min | E |
| 0, 0m | tools, the cluster, the platform; the sampler | 20–30 min | E |
| 1 | INSTALL cold (our images built and pushed) | 35–50 min | E (warm ≤ 6 min, M) |
| 2 | R1's checks | 3–5 min | E |
| 3 | the dashboards check (the report sync's first pull waits up to 10 min) | 15–25 min | E |
| 4–4c | spec 08 and case-b's halves and reds | 20–30 min | E |
| 5 | backup, change, restore; the two CronJobs | 5–10 min | M + E |
| 6 | verify | 5–10 min | E |
| 7 | the snapshot, the 20-minute soak, the report | 25 min | — |
| 8 | the unchosen decommission, then keep | 8–10 min | M + E |
| 9 | remake, platform, INSTALL warm, checks | 35–45 min | E (INSTALL warm ≤ 6 min, M) |
| 9b | the token version live: v1.0, the refusal and step 6's block, then 2.0 and the checks | 15–20 min | E |
| 10 | a set, then destroy | 10 min | M + E |
| 11, 12 | down, the queue, the lease | 10 min | E |

**About 4.5 to 5.5 hours with no FAIL.** A FAIL costs its fix and the rows from the one named again. The cold build (row
1) is the largest unknown, and the warm one (row 9) is the first measure of what keeping the images saves: both go in
the record.
