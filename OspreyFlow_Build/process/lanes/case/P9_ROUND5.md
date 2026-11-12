# P9 round 5: the orchestrator's second review of afc1a5f (12 November)

**Must fix**
- [x] 1 The runbook's restore step 2 waits for every pod named a writer's, the backup Jobs' kept pods among them
      (history limit 3): wait for the Deployments' and StatefulSets' pods alone. Then walk the runbook's restore,
      copy-pasted, on osprey-p9 under a lease after a backup Job has completed, and record it (rule 15).

**Should fix**
- [x] 2 A failure part-way leaves the parts mixed: say so in Am 7 point 8 and in "If it fails", per refusal (which
      parts are at the set already; re-running the same set is the way out).
- [x] 3 RDS: the point-in-time restore may start first; the deployment re-pointed only after step 2.
- [x] 4 An interrupted swap: the recovery pod's actual command; decided by whether `<database>.restoring` is there;
      the warning that starting the Conduit or the workers makes an empty database (`create_database_if_absent`).
- [x] 5 The free space needed before step 1: a second full copy on ArcadeDB's claim and in ClickHouse.
- [x] 6 restore-graph.sh's words: "put back" only when it was; never "not touched" once the live one moved; say
      when there was no live database; check `rm -rf "$old"` and say so if it failed; a scenario for a failed
      put-back.
- [x] 7 Rule 12: CheckDatabase's page-multiple branch and its no-entries branch, each reached by a scenario red
      for it (or the claim dropped from Am 7).
- [ ] 8 The plants and the merged record at the final head (the finish-time plant re-anchored); ROUND4's last tick
      corrected.

**Notes**
- [x] writers read `values["jobs"]` too, with a planted Job.
- [x] A restore clears another set's stale `_restoring_` copy, or names it; the set-aside RENAME's refusal names
      the fresh copy.
- [x] The drop-the-old refusal after a finished swap in "If it fails".
- [x] P9_render.diff's token-test exception narrowed to ClickHouse's pod alone.
- [x] The runbook's remaining build words; step 2 needs python3 with PyYAML.
- [x] Carries: whether ClickHouse frees a Replicated database's Keeper path on DROP (live-checks row); the check's
      time and memory on a real-sized graph (the client's install).
