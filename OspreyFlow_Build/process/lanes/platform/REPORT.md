# Platform · R1: the client install's acceptance, run on kind (13 November 2026), ready to merge

Branch `lane/platform-r1` on main `627745f`. The poc install, checks, backup, restore and decommission were run on kind on the test server, as P7b's runbooks are written, beside osprey-small (never touched). The cluster is down and the server freed at 18:12.

| Exit (BRIEF.md) | State | Proof |
|---|---|---|
| Install by INSTALL.md, exactly as written | done, every block | `r1/run/…175844Z-INSTALL.log` |
| Checked | 28 of 28 | `r1/run/…180425Z-check.log` (sign-in by the Entra stand-in, the owner's choice: nine refusals) |
| Backed up and restored | the change after the set gone, the set back, the door at once, no stack trace | `r1/run/…180557Z-restored.log` |
| Removed by DECOMMISSION.md | 0 left behind; backups kept with the last set | `r1/run/…181017Z-DECOMMISSION.log` |
| Every place wrong or unclear: a finding, fixed, re-run | 16 (7 by reading, 9 on kind), each red first | `r1/RUN.md` (the owner's plain-words list), `r1/desk-reds.txt` |
| Memory: node and every pod | node 6.3 GiB after the install, 7.8 after the restore, of 32; requests 26.6 GiB | `r1/RUN.md`, `r1/run/*memory.log` |
| Gates at the final head | `make ci` exit 0 (5cdfcd2); `make test` 13176 passed, then the 5 cli-deps errors fixed (1e0049d, 538 passed on the server) | 1 failure not this lane's (GPU preflight on a GPU host) |

**The two serious findings:** no readiness probe on the Conduit or the Glass, so every wait passed before either served (dd3cc99); and 48 Postgres pools, so an update's second Conduit was refused (cae6958: INSTALL asks for `max_connections` ≥ 750).

**Merged ahead:** `lane/platform-cli-deps` (614ec43, the `ospreyflow` command's small install, ADR-114 kept). **Requests to the orchestrator:** apply `R1_admin_guide.diff` at merge; CARRIES: the Conduit's pools (one shared pool, or sizes from settings, for the owner); the GPU preflight test, for its owner.

**Questions for the owner:** none open. **Running:** nothing. No cluster, no lease. Nothing pushed.
