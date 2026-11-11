# P9 round 3: the lane-reviewer's round-2 findings (197d79a), and the orchestrator's when they come

Head at the review: 197d79a; since then b6e8645 (writers check fails closed, no Calico policy of P9's own), and the
kind fail-closed check (`p9_kind.sh restore_refused`): both restore Jobs refused, "cannot confirm the writers are
stopped (… timed out); nothing was touched", stores untouched (the driver's log capture missed the init container's
words: read each pod's `verify` container).

**Must fix**
- [x] 1 BLOCKER: the backup user's password is a key of the shared Secret, which every `envFrom` workload loads
      (api, worker, report-sync, workspace): a Secret of its own (backups.tf: random_password + kubernetes_secret),
      referenced only by ClickHouse and the backup/restore pods; render test over every workload and job; plant.
- [x] 2 the stand-in's KMS ignores the key's own policy: model it (explicit deny wins; a key-policy allow for the
      principal is enough; root's grant delegates to IAM). The missing-KMS red becomes the key policy without the role.
- [x] 3 writers check fails open with no writers named: refuse; tests and plants for main's `verify` and
      `restore-claims`; a kind red with a writer running (a kind-only path to the API, standing for P7b's row); the
      test's missing `urllib` import.
- [x] 4 bucket policy: deny every object action to others (versions too: GetObjectVersion, DeleteObjectVersion,
      PutObjectAcl, ListBucketVersions) but **not ListBucket** (HeadBucket: Terraform's read, the decommission's step
      8); ADR and runbook wording; the render test that asserts no DeleteObjectVersion anywhere.
- [x] 5 decommission diff: key ARN by describe-key (not the alias) for put-key-policy and schedule-key-deletion;
      step 7 module-aware (TF_MODULE); the stray blank line; condition 2's note names runbooks.py too.
- [x] 6 runbook restore as typed: wait for the pods to go; delete a Job of the same name first; check success before
      starting anything; restore each copy count; the upgrade block applies the Terraform first.
- [x] 7 production's restore refused by the render (more than one ArcadeDB or ClickHouse copy), with a test.
- [x] 8 ClickHouse grants: osprey's `GRANT ALL` widens it (access management, named collections); measure SHOW GRANTS
      before and after and match the entrypoint's default less S3, URL, BACKUP; measure RESTORE FROM S3, the S3 table
      engine, s3Cluster, icebergS3 as osprey (refused).
- [x] 9 plants red for the wrong reason (ClickHouse file missing: TypeError; the name guard: message only) and
      refusals with none (verify init containers; main's verify and restore-claims; verify inside fetch_claims and
      restore_analytics; FileNotFoundError; the stand-in's aud).
- [x] 10 gates at the head, REPORT.md.

**Minor**
- [x] 11 retention: 35 days current plus 35 noncurrent is up to 70; say so; expired_object_delete_marker.
- [x] 12 key policy: no kms:Create* (CreateGrant is use); DeleteAlias; the test by action not name.
- [x] 13 the restore reads every part about four times: the init verify is the full one; each step checks its own part.
- [x] 14 the ClickHouse fake refuses BACKUP and RESTORE from any user but `backup` (Code 497).
- [x] 15 the backupPod/podSpec duplication recorded (Left).
- [x] 16 runbook: `sets` runnable; the before-an-upgrade block checks success and guards the claims Job.
- [x] (carried to P9b, Amendment 7's Left) 17 the restore's own service account (the nightly runner holds the pods Role): carry to P9b unless quick.

## The orchestrator's round 2 (197d79a), folded in (O = its numbering)
- [x] O1/1: the password in `ospreyflow-clickhouse-backup` (platform's name), red first. [x] (carried, Left) the backup user's networks
      to ClickHouse's and the runner's pods, not ::/0. [x] kind: RESTORE FROM S3, the S3 engine, s3Cluster, icebergS3,
      deltaLake, remote() as osprey; SHOW GRANTS before/after (measured in a container: `gates/p9_grants_probe2.log`:
      the narrowed set is the entrypoint's default less BACKUP and the S3/URL sources; RESTORE FROM S3 is NOT refused
      by privilege there, only by S3 itself; a dictionary's HTTP source is not gated by URL).
- [x] O2: the Calico policy is gone (b6e8645); the refusal's words name the missing path ("…until P7b's restore row
      lands"); RUNBOOK and ADR say every cloud-platform restore refuses until then.
- [x] O3: writers empty refuses; the chart `required`s it; main's verify and restore-claims tested; plant the except.
- [x] O4: verify_set: manifest["set"] == set_id, every key under sets/<set_id>/, the deployment's claims required.
- [x] O5 RULING: ClickHouse restored into a temporary database, then swapped; the old dropped only after; test a
      refusal leaves the live one intact.
- [x] O6: the stand-in evaluates key_policy(); plant there.
- [x] O7: KEY_ADMIN_ACTIONS with kms:CreateAlias (no Create*); honest wording of the Deny.
- [x] O8 RULING: retention is the total: current expiry = retention, noncurrent 7 days, expired_object_delete_marker;
      ADR, RUNBOOK, docstring, decommission step 7.
- [x] O9: step 8's head-bucket vs BackupRolesOnly's ListBucket deny: exempt administrators or check another way; model.
- [x] O10: step 7 state rm honours TF_MODULE; the guard fails if nothing was removed.
- [x] O11: section 10 concrete, or a platform-team procedure carried to P9b with its steps.
- [x] O12: re-plant 39 (`continue`) and 41 (an existing file); plants for ETag mismatch, verify's claims SHA, main's
      two writers calls, the fail-closed except; the commit named in each log and JSON.
- [x] O13: refuse to render the restore Jobs beyond one ArcadeDB or ClickHouse copy, naming P9b; plant.
- [x] O14: the policy test checks resources, principals, condition values, the trust documents; _trusted checks
      Principal.Federated and the token's issuer; Am 7 says what the stand-in's trust is built from.
- [x] O15: hash while downloading, each part read once (or the count in the RUNBOOK).
- [x] O16: the note's condition 2 corrected (runbooks.py imports the module; the module imports _file/_q/_secret).
- [x] Minors: refuse a shrinking file (no NUL padding); before-an-upgrade scales back and checks; the fake writes
      .backup last; BackupRolesOnly denies the version actions; test the secrets hook; re-check writers in the Job's
      last init step; records (P9_ROUND2.md, ADR_RESERVATIONS:195, the duplication).

## Kind, round 3 (after the above), and what it found
- [x] The backup user refused its own temporary database (`ospreyflow.*`): the prefix `ospreyflow*`, measured in a
      container (`gates/p9_grants_probe3.log`, `x_ospreyflow` refused, the live `ospreyflow` covered); the fake now
      judges by the users file's grant.
- [x] The swap renamed a ClickHouse database that a loss had removed (Code 81): set aside only when there; tests
      both ways; the fake keeps ClickHouse's databases.
- [x] osprey's RESTORE of ClickHouse's own part: the orchestrator's ruling A (listed for the owner); pinned as the
      one acceptance; the bound on a copied backup, red with the role planted wide (`p9_kind_bound.r3.log`).
- [x] Records: `p9_kind*.r3.*`, `p9_reds.r3.log` (68 of 68 red), the timed run under lease c (70.8 s).
