# Admin lane · T1 part 5 · the up-check and the reaper, after the orchestrator's review (12 November 2026)

`lane/admin-t1p5`, recut from main `e59da4f`. Part 5 was first built on the server's worktree
(`srv-wt/lane/admin-t1p5`, `9cbb457`, on T1 part 4's head `75cbc9b`, now in main) and reviewed there in two
independent rounds (`T1P5_FINDINGS.md`). Its up-check and reaper are ported here file by file, since main's
`stack_lease.sh`, its test, the root conftest and the Makefile have moved since. The wip commit `56cf4f6` and its
HANDOFF.md are not carried (must-fix 1).

**The split ruling.** `reset` (item 4a) is not part of this merge. It waits for its own step, which proves it first
against disposable containers of the real images and narrows what it drops; `T1P5_FINDINGS.md`'s last section is
that step's list. Its code (`af66134`) and plants stay on `srv-wt/lane/admin-t1p5`.

**Ownership** (the orchestrator's rulings, 12 November 2026). `stack_lease.sh` and `tests/test_stack_lease.py` are
the orchestrator's, sent as `stack-lease-T1p5.diff`; the root conftest as `conftest-T1p4.diff`; the Makefile is the
owner's, `makefile-T1p4.diff`, cut to apply after the owner's five patches already queued (MORNING item 38).

## What is merged

**Item 1, the plugin wired** (`tests/test_worker_isolation_wired.py`, `conftest-T1p4.diff`). The per-worker store
plugin is named in the root conftest's `pytest_plugins`, so `stack_lease.sh live`, a lane's own `pytest -n 4` and CI
all load it, not `make test` alone.

**Item 2, the up-check** (`stack_wholly_up`). `remote` and `live` ask the stack's own host for its running
containers and are refused, before anything is copied or selected, unless all are up. The refusal names each
container down and the `up` command; a docker that cannot answer refuses the run.

**Item 3, the reaper.** Each remote, live or offline run's `cmd.sh` exports `OSPREY_RUN_TAG=$HOME/<run folder>` and
traps EXIT with a reaper that ends every process whose environment holds exactly that tag (TERM, then KILL two
seconds later), on INT and TERM too. HUP is not claimed: the run is started under nohup. `reap <lane>` sends the same
reaper for the run `last` points at, when a run's own reaper never ran.

## The review's findings, each with its red

1. **The wip commit and HANDOFF.md** are gone: the branch is recut from main.
2. **`makefile-T1p4.diff`** is regenerated: its one change drops `-p tests.worker_isolation ` from `make test`'s
   pytest line, cut on top of the owner's five (`P12p2_CI`, `P12p2_core_makefile`, `p10p2/ci-yml`,
   `p10p2/makefile`, `make-test-runs-every-part`), and checked in a scratch worktree to apply sixth, in that order,
   and not alone on main (`gates/t1p5_makefile_order.txt`). `ci-yml-T1p4.diff` is removed (main has it). **The
   earlier log's "all three diffs still apply" was wrong** (the Makefile diff did not apply to main: main already
   had `TEST_WORKERS`).
3. **`test_worker_isolation_wired.py` reads the root conftest's own `pytest_plugins`**, which no flag changes: red on
   main's conftest **with `-p tests.worker_isolation` on the command line**, as `make test` passes it; green with the
   conftest diff (`gates/t1p5_wired_red.txt`).
4. **`reap` refuses a run whose pid still answers** (`kill -0`, as a run's start checks), in words, exit 3; **the
   reaper refuses an empty tag**, exit 2, never reading it as every process tagged with nothing. Each a case, each
   planted.
5. **The KILL pass reads each pid's environment again before `-9`**: a case whose process survives TERM (red with
   the KILL pass taken out), and one whose process becomes another program on TERM, with no tag, as a recycled pid
   would hold another process (red when the KILL pass sends -9 without reading again).
6. **Two runs of one lane never share a folder, so never a tag**: the folder takes a random suffix after the second,
   and is made by a plain `mkdir` on the host, which fails rather than reuse one. A case starts two runs within one
   second; planted.
7. **The reaper's cases skip, in words, where there is no `/proc` or no `setsid`** (`_REAPS`): on macOS nine skip
   with the reason; on the Linux server they run. The plants run there, and a case that only skips counts as
   missed, never red.

## The should-fixes

- **The fake routes on the real command**: the reap call is `bash -s -- <meta>`, with no comment for the fake to
  route on.
- **The header's usage block** documents `reap`.
- **INT is tested** beside TERM (exit 130 and 143), and HUP is no longer claimed.
- **The reads audit's counts, corrected**: "not a read" is **10** (the fake client, `test_sql_transform.py`'s **8**
  DuckDB hits, and a docstring), not 6. Today's scan: 28 candidates in 308 live files (`gates/t1p5_reads_audit.txt`).
  The judgement of each is as part 5 gave it (below).
- **`t1/t1p5_plants.py`** is rewritten: it applies `stack-lease-T1p5.diff` first and reverses it, refuses a dirty
  tree, holds the strict verdict (red only on exit 1 with "failed" and no "error"; a skip-only run is missed), and
  drops the reset's plants. Ruff-clean; run at the final head on the server (`gates/t1p5_plants_<head>.txt`).
- **`t1/apply_diff.py` writes all or nothing and matches on line boundaries**: every file to a temporary first, then
  renamed; a hunk matches only whole lines; hunks are read by their `@@` counts. Shown against the old applier on
  four cases (`gates/t1p5_apply_diff.txt`). Two real faults found: the old one wrote a hunk into the middle of a
  longer line (`xbeta` became `xBETA`), and it gave a two-file diff's first hunk to the second file, so it refused
  every diff of two files.
- **The ssh block, fixed**, not carried: the start call backgrounded `cd $HOME && nohup setsid … &` as one list,
  whose subshell kept ssh's output open until the run ended. The subshell is redirected now; a case shows the start
  call returning while the run goes on; planted.
- **A friction fragment**: `process/friction/2026-11-12-admin-t1p5.md`.

## Item 4b, the audit of live tests that read beyond their own rows (part 5's judgement, counts corrected)

`t1/t1p5_reads_audit.py` scans the live files for four shapes: a whole-table count, a graph-wide count, the length of
an unfiltered listing, a whole-table delete. 28 candidates:
- **Not a read of a stack (10):** `adapters/graph_arcadedb/test_client_row_limit.py:47` (a fake client);
  `ingest/test_sql_transform.py`, 8 hits (DuckDB in memory); `resolve/test_trigger.py:1` (a docstring).
- **A before-and-after delta on a shared table (5):** `ingest/test_repoint_journal_callers_live.py:796, 813, 1116`;
  `test_make_home_cases_store.py:54, 57`. Safe on a leased stack run serially.
- **An absolute count on a whole table (11):** `services/api/test_custom_roles_store.py:270, 403`,
  `services/api/test_disable_l38_transfers.py:297`, `test_make_home_cases_store.py:58, 104`,
  `test_migrate_branches_to_views_store.py:216, 224`, `test_migrate_cases_to_one_dataset_store.py:43, 46`,
  `connectors/test_sql_connector_live.py:618`, `services/api/test_investigation_access_store.py:325` (filtered by id:
  a false positive). Each file names a schema of its own; confirming the count runs inside it is the follow-up.
- **A real accumulation risk (1):** `scenarios/test_phase7_stage6c_watch_routes.py:480` counts every connection on
  the server; a carry for its owning lane.
- **A whole-table delete (1):** `services/api/test_audit_section_store.py:463`, safe inside its schema.
