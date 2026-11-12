# P9 round 4: the orchestrator's review of 7916044 (12 November)

One pass, then rebase onto main (L1.9 part 2 at 184b798, records 6331d87), refresh the diffs, re-gate, "built at".

**Must fix**
- [ ] 1 ArcadeDB's restore never removes the live graph first: restore into `<db>.restoring`, check it opens, swap
      by `mv` (live to `<db>.before`), remove the old only after; on failure the live one untouched, refused in words.
      Test and plant. RUNBOOK's restore steps to match, and where ClickHouse's data is if its second RENAME fails
      (`<db>_before_…`).

**Should fix**
- [ ] 2 ClickHouse's user and password to `backup` and `restore-analytics` alone; a test tying each container's
      Secret keys to its commands (as `test_backups_rows.py` does for egress); a plant.
- [ ] 3 A stale `*.zip` in `<folder>/<db>/` (a killed run's) deleted before ArcadeDB's backup; red first.
- [ ] 4 Kind (rule 15): a restore beside a live database changed since the set, under the lease: back as the set;
      a planted failure part-way leaves the live database (ArcadeDB's swap and ClickHouse's RENAME swap).
- [ ] 5 The writers derived from the rendered workloads that mount the claims or write the stores, the backup
      CronJobs' Jobs among them; a test that a new such workload is caught; RUNBOOK suspends both CronJobs first and
      resumes them after.
- [ ] 6 `.set` must match `YYYYMMDDTHHMMSSZ` in the template (no `latest` resolved twice); a test.
- [ ] 7 The two plants caught by a default refusal (r4.log 262-267, 345-350): the escape path resolving to a real
      file, the outside-the-set object existing; each red for its own reason; the count corrected.
- [ ] 8 Stand-in: CompleteMultipartUpload's InvalidPart (missing part, wrong ETag) a 400; EntityTooSmall; a pods
      list 403 (RBAC) from the Kubernetes fake refused in words; versioning not modelled said in Am 7 and on the
      live-checks CARRIES row.

**Rulings**
- [ ] 9 RDS restored point-in-time to the set's finish, before the stores: an Am 7 point, a RUNBOOK step, a CARRIES
      row (automating it is P9b's).
- [ ] 10 P9_rows.diff's Am 5 point 21 hunk dropped.

**Notes**
- [ ] RUNBOOK for the client's operator: no build jargon (P7b, P9b, kind, lanes, stack leases); measurements stay
      in the gates records.
- [ ] RUNBOOK 287: stack c, not b. "until P7b's restore row lands" removed (RUNBOOK 320, 06_DECISIONS 33889).
- [ ] The CronJobs' `timeZone: Etc/UTC`.
- [ ] The database names from the render's environment.
- [ ] A malformed manifest refused in words, not a KeyError.
- [ ] `fetch_claims`' finally never removes restored entries once the old contents are gone.
- [ ] P9_decommission.diff re-cut as a git diff with index lines against current main.
- [ ] Every record at the final head with the three diffs and L1.9 applied: the merged cp-policy-check
      (development-sources.yaml too), tests/cloud_platform_backup, the plants.
- [ ] Carries (no fix): a writer starting between the writers check and restore-graph; IAM `*` matching `/`;
      harness/cloud_platform_backups.py to platform afterwards.
