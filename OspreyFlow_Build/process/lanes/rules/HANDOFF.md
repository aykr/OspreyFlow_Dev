# rules lane: handoff (2026-11-15, about 12:45Z, paused for the switch to sol)

**Step and part:** none open. Every rules item is merged; the lane is idle.

**Last commits:** main 81f96fc. The rules branches merged most recently: ff494d4 (lane/rules-v060-superset-cves at
74e6c25: the Superset PostgreSQL client floor, plus OSPREY_UPGRADE_STAMP on all 9 upgrading images) and #14 (Alert sources
says why a hotlist or watch stopped, user guide 1.70).

**Done today:**
- ADR-124 Am 21 (search_nodes finds candidates by SQL, one lookup per type's flattened field): M9 met, 82–116 ms; 1,200 of
  1,200 the same as the query as built, in two steps.
- Step 4 re-run on the shipping code: M1 61 ms, M3 126 ms, M4 184 ms, M5 144 ms, M6 2.08 s p95, all met; platform has
  RESULTS.md. M10 met; never-join at exactly the 90% floor; the words half rests on sent_at, with a positive control
  5 of 5 (process/lanes/rules/m10-query/README.md).
- v0.6.0 #14, the Superset CVEs (230 to 0 at the gate) and the cached-upgrade trap (harness/upgrade_stamp.py).

**Was running:** nothing. No lease, no QUEUE line. Stack d is down and released, its containers stopped on the server
still holding B's load (570,565 nodes, with M6's 105 drawn ones); `stack_lease.sh up` restores it as it was.

**Next for this lane, on sol (the orchestrator, 15 Nov):** Test-stage REHEARSAL for stage 2 (M10 ids, words, never-join
+ positive control; M3-M6, M9 at client size): check step 4's scripts and stack d still run on today's main (#3, #4,
#5's add-by-ids changed search), fix the tooling offline first, write the one-command-list run sheet. Ask the
orchestrator for a lease window and a QUEUE slot before touching the server.
**Next (owner or orchestrator):**
- The owner applies process/lanes/rules/v060-upgrade-stamp/workflows_upgrade_stamp.diff (ci.yml, release.yml).
  tests/test_upgrade_stamp.py reads the workflows through that diff until it is applied.
- Defect 8, still open: Needs you's fallback for an older schedule notice names no pipeline (schedule_notices.py:56, 65).

**Must not redo:** the Superset red/green (gates/fc179af.superset-red-green.txt), the step 4 runs (results-today/
on the server), Am 21's 1,200-comparison equivalence (2 h 45 min).
