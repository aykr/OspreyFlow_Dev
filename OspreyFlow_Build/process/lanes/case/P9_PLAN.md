# P9 (cut) plan — backups on the cloud-platform profile, and one timed restore

**Superseded as to the design by ADR-148 Amendment 7 (as built).** This plan was written before kind: ClickHouse is
not handed the role's credentials in the statement (25.8 refuses a token), it writes as a role of its own by its own
pod; two roles each to its own prefix; a versioned bucket; the claims part; the restore's verify and writers check.
Kept as the plan it was.

From: ADR-148 decisions 5, 13; Amendment 1 (items 4, 5, 9); BRIEF_P9.md; rules 1, 4, 12, 15.

**Shape.**
- **ArcadeDB.** `BACKUP DATABASE` writes its zip into the server's own `backups` folder, which on this profile
  is a scratch folder no other pod can read. The render gives ArcadeDB a `backups` claim instead (platform's
  diff); the CronJob's pod mounts `backups-arcadedb-0` (ReadWriteOnce: placed on that pod's node by a required
  affinity), asks for the backup over HTTP, uploads the zip and removes it.
- **ClickHouse.** `BACKUP DATABASE … TO S3(url, key, secret, token)` with the backup role's temporary
  credentials, which the runner holds by IRSA; ClickHouse itself is given no role and no key.
- **Encryption.** A backups bucket of its own, encrypted by a customer KMS key (SSE-KMS, the bucket's
  default), its policy refusing plain HTTP and any other encryption; a role of its own (`ospreyflow-backup`),
  given that bucket and that key alone (platform's diff: Terraform).
- **Restore.** A Job rendered only when `backups.restore.set` is given (`helm template --show-only`, applied
  with ArcadeDB stopped): the zip fetched, ArcadeDB's `restore.sh` into its claim, ClickHouse `RESTORE`.

**Files (mine).** `deploy/helm/ospreyflow/templates/backups.yaml`; `services/api/platform_backup.py` (the
runner, in the Conduit's image, which has boto3); `tests/fixtures/cloud_platform/s3_standin.py` (S3, STS and
KMS's refusals); tests under `tests/cloud_platform_backup/`; the runbook's section; ADR-148 Amendment 7.
**To platform as a diff.** `harness/cloud_platform/**` (the `backups` values, ArcadeDB's claim, the Terraform),
`values.yaml`'s comment.

**Tests first.** The stand-in refuses (each red first at the boto3 call the runner makes): a wrong signature,
an unknown key, an expired token, a bucket policy's deny, a role without `kms:GenerateDataKey`/`kms:Decrypt`,
an action the role is not given. The runner: a backup set's manifest and checksums; every failure says which
store and why; nothing reported done that the stand-in refused. The template: the CronJob's pod as
cp-policy-check holds it, red on a planted fault. Live (server): real ArcadeDB 26.10.1 and ClickHouse 25.8
against the stand-in. Kind: the round trip, the restore timed under a lease.
