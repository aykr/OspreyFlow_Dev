# P9 round 2: the orchestrator's review (f8885da) and the lane-reviewer's, fixed in one pass

Working list; each line is closed by a commit naming its test. O = orchestrator's item, R = reviewer's.

**Measured first (osprey-p9, 11 Nov, as `osprey`, ClickHouse holding the backup role):** `s3()` read a set's
manifest (4) and ArcadeDB's zip (87,479 bytes), `INSERT INTO FUNCTION s3()` wrote over a set, `url()` reached
another host. All accepted.

## Access (blocker)
- [ ] O1a: ClickHouse user `backup` (BACKUP, RESTORE, S3 source; password its own Secret key) used by the runner
      alone; `osprey` refused S3 and URL sources and the s3/url table functions (users.d XML via the render's
      files, from my module). Kind: osprey's s3() refused, red first; the backup user's BACKUP passes.
- [ ] O1b: two roles. ClickHouse's (`ospreyflow-backup-clickhouse`): put/get/list on `sets/*/clickhouse/*` and
      the lock's delete only. The runner's (`ospreyflow-backup`): ArcadeDB, claims and manifest prefixes. Each
      its own service account; the bucket policy admits both, each to its own prefix.
- [ ] O2/R5: versioning on, noncurrent-version expiry = retention; no DeleteObjectVersion; "erases no set"
      corrected (an overwrite is recoverable).
- [ ] O7/R17: explicit KMS key policy: account admins administer (no ScheduleKeyDeletion outside the
      decommission), the two roles use it with kms:ViaService s3.<region>.amazonaws.com. Rendered-policy test.
- [ ] R4: bucket policy refuses aws:kms with no key id (aws/s3); the stand-in models aws/s3; plant ItsOwnKey.
- [ ] O9: the stand-in's trust from the rendered backup_trust document; plants: the three bucket-policy denies,
      the trust's :sub and :aud, the stand-in's signature, aud, KMS and TLS checks; R6: fetch checks, name guard,
      unfinished-set refusal.

## Restore
- [ ] O3/R2: the manifest records ClickHouse's part (its backup's file list, sizes, SHA-256); a `verify` init
      step in both Jobs checks every part before any rm, DROP or claim replacement; missing or expired part:
      refused, nothing touched. Test: a missing ClickHouse part leaves ArcadeDB and ClickHouse untouched.
- [ ] O4: the restore Jobs' service account may get/list pods; refused in words while ArcadeDB, the Conduit,
      workers or report-sync run. ADR and RUNBOOK: stopped, in every shape.
- [ ] O5/R7: proven for single-replica shapes (development, poc); production's procedure is P9b's (Left).
- [ ] O10: the fake keeps no expired session (ClickHouse renews); R6: kind's unrenewable case shows the STS
      refusal for ClickHouse's pod, by the runner's own clickhouse_backup.

## Claims, decommission, runbook
- [ ] R9: a file vanishing mid-tar is skipped and counted, not a failed part; test.
- [ ] O11/R8: backup before an upgrade in poc: the claims run's affinity allows the claim free (shared pods
      stopped); RUNBOOK says how. 64.6 s excludes stopping/starting the Conduit, workers, report-sync. Lease from
      stack_lease.sh. R12: claims job guarded; failed Jobs not waited 6 h; the runner's `sets` documented; date -d.
- [ ] O6/R3: decommission replaces expire-sets with the client's retention (or removes it); restoring a kept
      set once the role is gone (the bucket and key policies, who may). P9_decommission.diff, R11 lint, its test
      from backups_terraform.
- [ ] Platform's five conditions, checked, in P9_render.diff's note; roles/SAs/Secrets not kept.

## Minor
- [ ] stand-in refuses a wrong-region signature; tofu fmt/validate on backups.tf; take() refuses a finished slot;
      backoffLimit; _said names the service (R13); friction/P9_PLAN figures; R16 weak assertions; R17 backupPod
      duplication; duplication with harness/backup.py and conduit_common/s3.py (say or carry).
- [ ] O8: gates at the final head, offline, recorded; REPORT.md; lane-reviewer round 2.

## Progress (uncommitted work in the tree, 11 Nov evening)
- Grants measured on a throwaway ClickHouse 25.8.33.6 on the server (gates/p9_grants_probe/, delete after):
  `REVOKE S3, URL, BACKUP` in osprey's users.d `<grants>` works beside the entrypoint's file (url and BACKUP
  refused); the S3 rerun was still retrying at a closed port when last seen (task bcl4hz542).
- Module rewritten (harness/cloud_platform_backups.py): add_backups hook, two roles + trust_policy, key_policy,
  NoKeyNamed, versioning + noncurrent expiry, ClickHouse users file + backup user. rendered.py uses the hook.
- Stand-in: trust documents (`_trusted`), kms:ViaService, aws/s3 key; conftest: two roles, per-role tokens,
  `Running.token` override, ClickHouse fake on its own role (renews on ExpiredToken; anonymous on STS refusal).
- test_s3_standin.py green (31). Next: test_backups_render, test_platform_backup(+claims), then runner B items.
