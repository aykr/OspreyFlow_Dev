# Platform · R1, part 1 of 2: prepared on the Mac (12 November 2026), not yet run

Branch `lane/platform-r1` from main `1b317d4`. The paused `wip(platform)` held HANDOFF.md alone: kept on
`backup/platform-p7b-wip-handoff`, `lane/platform-p7b` back at `5585b4e`; HANDOFF.md is not on main.

| Exit (BRIEF.md) | State | Proof |
|---|---|---|
| Both runbooks read as a platform team member; every place wrong or unclear fixed | 7 fixed, red first | `r1/desk-reds.txt`; `test_cloud_platform_poc.py` (variables as bash reads them, the last backup under bash, Entra before step 5, the way back in installs, curl's options, `bash later`, the certificate Secret) |
| Every command and what it needs; the kind cluster's settings; the check list | done | `r1/PREP.md`; `gates/r1_kind.sh`, `r1_kind.py`, `r1_kind_osprey.yaml` |
| Sign-in on kind (the owner's choice: a stand-in issuer) | proven off-cluster | `r1/token-dry-check.txt`: the real resolver accepts the admin's token, refuses five Entra refusals for their own reasons |
| Installed, checked, backed up, restored, decommissioned on kind; node and pod memory recorded | **not run** | waits for the server (from Friday evening, on the orchestrator's word) |
| Gates at the final head | not yet | touched suites 187 passed, 239 skipped (helm absent on the Mac); `make ci` on the server at the final head |

**Commits:** `d2ee577` (runbook fixes 1–5), `9b7e216` (`bash later`; the certificate Secret), `2d2db54` (the kind
tooling, PREP.md), and this report with the friction row and `R1_admin_guide.diff`.

**Requests to the orchestrator:** the server's Docker for R1 from Friday evening; the owner's yes for the run's
downloads (kind, helm, Calico, ingress-nginx, the node image, postgres and valkey from AWS's mirror); apply
`R1_admin_guide.diff` at merge (docs adds the version row). `deploy/RUNBOOK.md`'s upgrade backup scaling
`report-sync` (not rendered here) is a known issue of its owner's, met in R1 only if the run reaches it.

**Questions for the owner:** none open.

**Running:** nothing. No lease, no cluster, no server command. Nothing pushed.
