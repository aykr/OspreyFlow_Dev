# P9 round 4: the orchestrator's review of 7916044 (12 November)

One pass, then rebase onto main (L1.9 part 2 at 184b798, records 6331d87), refresh the diffs, re-gate, "built at".

**Must fix**
- [x] 1 ArcadeDB's restore never removes the live graph first: restore into `<db>.restoring`, check it opens, swap
      by `mv` (live to `<db>.before`), remove the old only after; on failure the live one untouched, refused in words.
      Test and plant. RUNBOOK's restore steps to match, and where ClickHouse's data is if its second RENAME fails
      (`<db>_before_…`).

**Should fix**
- [x] 2 ClickHouse's user and password to `backup` and `restore-analytics` alone; a test tying each container's
      Secret keys to its commands (as `test_backups_rows.py` does for egress); a plant.
- [x] 3 A stale `*.zip` in `<folder>/<db>/` (a killed run's) deleted before ArcadeDB's backup; red first.
- [x] 4 Kind (rule 15): a restore beside a live database changed since the set, under the lease: back as the set;
      a planted failure part-way leaves the live database (ArcadeDB's swap and ClickHouse's RENAME swap).
- [x] 5 The writers derived from the rendered workloads that mount the claims or write the stores, the backup
      CronJobs' Jobs among them; a test that a new such workload is caught; RUNBOOK suspends both CronJobs first and
      resumes them after.
- [x] 6 `.set` must match `YYYYMMDDTHHMMSSZ` in the template (no `latest` resolved twice); a test.
- [x] 7 The two plants caught by a default refusal (r4.log 262-267, 345-350): the escape path resolving to a real
      file, the outside-the-set object existing; each red for its own reason; the count corrected.
- [x] 8 Stand-in: CompleteMultipartUpload's InvalidPart (missing part, wrong ETag) a 400; EntityTooSmall; a pods
      list 403 (RBAC) from the Kubernetes fake refused in words; versioning not modelled said in Am 7 and on the
      live-checks CARRIES row.

**Rulings**
- [x] 9 RDS restored point-in-time to the set's finish, before the stores: an Am 7 point, a RUNBOOK step, a CARRIES
      row (automating it is P9b's).
- [x] 10 P9_rows.diff's Am 5 point 21 hunk dropped.

**Notes**
- [x] RUNBOOK for the client's operator: no build jargon (P7b, P9b, kind, lanes, stack leases); measurements stay
      in the gates records.
- [x] RUNBOOK 287: stack c, not b. "until P7b's restore row lands" removed (RUNBOOK 320, 06_DECISIONS 33889).
- [x] The CronJobs' `timeZone: Etc/UTC`.
- [x] The database names from the render's environment.
- [x] A malformed manifest refused in words, not a KeyError.
- [x] `fetch_claims`' finally never removes restored entries once the old contents are gone.
- [x] P9_decommission.diff re-cut as a git diff with index lines against current main.
- [x] (corrected in round 5: the merged record ran at a06b145, not at the gated head afc1a5f; afc1a5f changed a
      variable's name and the finish-time plant's anchor, re-run in round 5) Every record at the final head with the three diffs and L1.9 applied: the merged cp-policy-check
      (development-sources.yaml too), tests/cloud_platform_backup, the plants.
- [x] Carries (no fix): a writer starting between the writers check and restore-graph; IAM `*` matching `/`;
      harness/cloud_platform_backups.py to platform afterwards.

## As done (12 November)
- 1: `deploy/backups/restore-graph.sh` and `CheckDatabase.java` (the check held to the set's zip: ArcadeDB opens a short
  or missing bucket or an empty schema with only a warning, `gates/p9_restore_graph_probe.log`); `test_restore_graph.py`
  in ArcadeDB's own image; ClickHouse's swap puts the live one back if the second RENAME is refused, naming both.
- 5: writers transitive over profile.yaml's rows (the report sync and the Glass write through the Conduit).
- 7: the escape path and the outside object now real; plants red for their own check.
- 9: each manifest records `finished`; `sets` prints it; Am 7 point 10; the runbook's first step; a CARRIES row.
- Plants named by function where a parameter id with spaces would not select; four re-anchored on this round's code.
