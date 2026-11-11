# Case · brief P9 (cut) · backups on the `cloud-platform` profile, and one timed restore

Written by the orchestrator, 11 November 2026, when P7 merged (c73e4f1). P9 moved from platform to case
(ADR-142 Amendment 8 decision 10). Binds: `process/CLAUDE.md` rules 1–15, `process/lanes/PROMPT_L.md`, ADR-142
Amendments 6–8, ADR-148 decisions 5 and 13, and ADR-148 Amendment 1 (the profile as built).

**What (cut to what a proof of concept needs, Amendment 8 decision 4).**
- A scheduled, encrypted backup of ArcadeDB (`BACKUP DATABASE`) and ClickHouse (`BACKUP … TO S3`) to S3: a CronJob
  rendered by the profile, using the namespace's IAM role, with no stored key.
- One restore rehearsed and timed, with its section in the recovery runbook, giving the measured times and the lease
  they were taken under (rule 14).
- Moved to P9b, after the client's install: the alerts, the PodDisruptionBudgets' drain test and the volume-expansion
  procedure.

**Ownership.**
- Your own template file(s) for the CronJob under `deploy/helm/ospreyflow/templates/`.
- Changes to `values.yaml`, the profile's settings model, `render.py`'s profile entry or `harness/cloud_platform/**` go
  to platform as a diff (Amendment 8 decision 3).
- P10 and P9 merge first in the chain.

**Exit.**
- The backup and the restore round-trip on kind with an S3 stand-in that refuses what S3 refuses (rule 15's second
  example): a wrong bucket policy, a missing KMS permission, an expired role.
- `cp-policy-check` green on the render with your template, and red on a planted fault in it.
- The restore's time measured under a lease.
- Every refusal red first at its real call site.
- Gates once at the head through `stack_lease.sh offline case`.

Write the as-built record as ADR-148 Amendment 7 (reserved). Send "built" and "ready-to-merge" to the orchestrator.
