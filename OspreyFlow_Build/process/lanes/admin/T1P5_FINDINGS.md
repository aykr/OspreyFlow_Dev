# Admin · T1 part 5 · review findings at 9cbb457 (two independent rounds, 11 November 2026)

Written by the orchestrator. **Queued behind P10 part 2**: start it when P10 part 2 is ready-to-merge, on
`lane/admin-t1p5` rebased onto main. `stack_lease.sh` is the orchestrator's file. Items 2–4 of the part are ratified
here (CARRIES rows 98, 111, 112), on the terms below.

**Ruling: split.** The up-check (item 2) and the reaper (item 3) merge once their findings are fixed. `reset` (item 4)
comes off this merge and waits for its own step. That step proves it first against disposable containers of the real
images (`arcadedata/arcadedb:26.10.1`, `clickhouse/clickhouse-server:25.8.33.6`, the stacks' Postgres and MinIO), never
against a lane stack, and it narrows what it drops to names the tests make (the `_LEFT` pattern), not every database
but the system ones.

## Must fix before the merge
1. **Remove the wip commit 56cf4f6 and HANDOFF.md** (Prompt R).
2. **Regenerate `makefile-T1p4.diff` against main.** Its only change is dropping `-p tests.worker_isolation ` from
   `Makefile:166`; main already has `TEST_WORKERS`. Remove `ci-yml-T1p4.diff`, which is already applied. The log's
   statement that "all three diffs still apply" is wrong; correct it.
3. **`test_worker_isolation_wired.py` must fail if the conftest diff is missed.** It must fail even while `-p` is on
   the command line: assert registration through the conftest's `pytest_plugins`, not just `has_plugin`. Show it
   red. The conftest diff is applied in the same merge.
4. **`reap` refuses a run whose pid is alive** (`kill -0`, as `run_on_host` does), and refuses an empty tag. Red first.
5. **The reaper's KILL pass re-reads each pid's `environ` for the tag before `-9`.** No KILL goes to a recycled pid.
   Include a case where a process survives TERM, so that deleting the `-9` pass goes red.
6. **Two runs of one lane never share a tag.** Make the run folder unique beyond the second (`mktemp -d`, or a random
   suffix), atomically.
7. **The reaper cases skip where there is no `/proc` or no real `setsid`, with the reason in words.** They fail on
   macOS today.

## Should fix in this part
- The `reap` line's trailing `# reaps by OSPREY_RUN_TAG` exists only for the fake's routing. Route the fake on the
  real command instead.
- Document `reset`/`reap` in the header usage block (only `reap`, once reset is split out).
- Claims of "INT, TERM and HUP": test INT too. Drop HUP, which `nohup` ignores.
- Correct the reads-audit counts in the log: "not a read" is 10, and `test_sql_transform.py` has 8 hits.
- Re-run ruff on `t1/t1p5_plants.py`. Run the plants again at the final head and record them.
- `apply_diff.py`: write all files or none (write temporaries, then rename), and match hunks on line boundaries.
- Add a friction fragment for part 5 in `process/friction/`.
- Record the ssh blocking of `remote`/`live` (`stack_lease.sh:174`, the backgrounded list holding stdout) as a CARRIES
  row if it is not fixed.

## For `reset`'s own step (not this merge)
- ArcadeDB's directory comes from `docker inspect` or the server's own HTTP `drop database`; never a guessed path.
  Stop, wipe, start.
- Every store is checked empty after its step. Success is printed only from those checks. A table that fails to
  read is a failure.
- ClickHouse: connect with `--database system`; keep `CLICKHOUSE_DB`.
- Postgres: escape names; keep roles or say why not.
- Leave MinIO's `.minio.sys` alone; refuse `/`, `..` and `//`.
- Refuse while the holder's run is alive.
- Check the container's labels and compose project, not just its name prefix (`osprey-test-idp-*`, and a compose
  project named `osprey-test`).
- Refuse any container with a bind mount.
- The fakes refuse what the real tools refuse: template databases, wrong credentials, a missing folder.
