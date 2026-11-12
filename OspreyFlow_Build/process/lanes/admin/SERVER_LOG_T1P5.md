# Admin lane · T1 part 5 · the up-check and the reaper, after the orchestrator's review (12 November 2026)

`lane/admin-t1p5`, recut from main `e59da4f` and rebased onto `bb1c897` (the owner's five patches applied). Part 5 was first built on the server's worktree
(`srv-wt/lane/admin-t1p5`, `9cbb457`, on T1 part 4's head `75cbc9b`, now in main) and reviewed there in two
independent rounds (`T1P5_FINDINGS.md`). Its up-check and reaper are ported here file by file, since main's
`stack_lease.sh`, its test, the root conftest and the Makefile have moved since. The wip commit `56cf4f6` and its
HANDOFF.md are not carried (must-fix 1).

**The split ruling.** `reset` (item 4a) is not part of this merge. It waits for its own step, which proves it first
against disposable containers of the real images and narrows what it drops; `T1P5_FINDINGS.md`'s last section is
that step's list. Its code (`af66134`) and plants stay on `srv-wt/lane/admin-t1p5`.

**Ownership** (the orchestrator's rulings, 12 November 2026). `stack_lease.sh` and `tests/test_stack_lease.py` are
the orchestrator's, sent as `stack-lease-T1p5.diff`; the root conftest as `conftest-T1p4.diff`; the Makefile is the
owner's, `makefile-T1p4.diff`, cut against main with the owner's five patches applied.

## What is merged

**Item 1, the plugin wired** (`tests/test_worker_isolation_wired.py`, `conftest-T1p4.diff`). The per-worker store
plugin is named in the root conftest's `pytest_plugins`, so `stack_lease.sh live`, a lane's own `pytest -n 4` and CI
all load it, not `make test` alone.

**Item 2, the up-check** (`stack_wholly_up`). `remote` and `live` ask the stack's own host for its running
containers and are refused, before anything is copied or selected, unless all are up. The refusal names each
container down and the `up` command; a docker that cannot answer refuses the run.

**Item 3, the reaper.** Each remote, live or offline run's `cmd.sh` exports `OSPREY_RUN_TAG=$HOME/<run folder>` and
traps EXIT with a reaper that ends every process whose environment holds exactly that tag (TERM, then KILL two
seconds later), on TERM too. `reap <lane>` sends the same reaper for the run `last` points at, when a run's own reaper
never ran. **INT and HUP are not claimed** (below).

## The review's findings, each with its red

1. **The wip commit and HANDOFF.md** are gone: the branch is recut from main.
2. **`makefile-T1p4.diff`** is regenerated against main `bb1c897`, where the owner's five patches are applied
   (`44ec30d`; the orchestrator's simpler ruling 2): its one change drops `-p tests.worker_isolation ` from `make
   test`'s pytest part, `( $(IN_CORE) $(PYTEST) … ) || touch $(TEST_FAILED)`, and applies to main as it stands. (Cut
   first on top of the five as diffs, it was checked to apply sixth in a scratch worktree: `gates/t1p5_makefile_order.txt`,
   kept for the record and now moot.) `ci-yml-T1p4.diff` is removed (main has it). **The earlier log's "all three
   diffs still apply" was wrong** (the Makefile diff did not apply to main: main already had `TEST_WORKERS`).
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
- **"INT, TERM and HUP": INT tested, and the claim dropped with HUP's.** Testing INT found that a run on a host
  starts with INT and QUIT ignored, inherited from the start call, which backgrounds the run from a non-interactive
  shell (main's own start call; HUP likewise, under nohup); a shell cannot take back a signal ignored when it
  started. Measured: the run's command reads SIGINT as SIG_IGN. So INT to a run does nothing, and stopping one is
  TERM, which is tested. On the way, one attempt here backgrounded the command inside cmd.sh to make INT interrupt a
  waiting bash; it passed the INT case alone (the race was in the test's favour) and failed it in the gates, where the
  whole gate run, started so, could not be interrupted. It was taken out. Making INT work needs the run started with
  INT restored: a CARRIES row for the orchestrator's file.
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

## Gates at `f11a865` on main `bb1c897` (the owner's five patches on main; this lane's three diffs applied)

- **The plants**, on the server (Linux, /proc and setsid real; the harness applies `stack-lease-T1p5.diff` with
  `t1/apply_diff.py` and takes it back): 16 plants, 23 case runs, all red, none missed, no harness fault; the whole
  file green before (66 passed) and after on main's script (`gates/t1p5_plants_f11a865.txt`). Three earlier runs each found
  something, all fixed here: the stand-in ssh hid `reap`'s exit code; the INT claim (above); and the stand-in ssh
  returned before its output closed, so the held start call could not be red.
- **The server, offline:** `make -k ci` exit 0 (`gates/t1p5_f11a865.ci.txt`); `make test`, each part run: pytest 12,782
  passed and the server's GPU case alone failed; test-js on the server 3,135 passed and MatrixView's first-frame budget
  failed under the server's load (a known perf-budget item; passed in the Mac's full run) (`gates/t1p5_f11a865.test.txt`).
- **The Mac:** live-collect exit 0; test-js 3,136 + 51 passed; a11y 1,019 passed and 1 failed, keyboard 768 passed and 2
  failed, those three main's own (`gates/t1p5_mac_f11a865.txt`).

## The orchestrator's review of `2b1e26a` (12 November 2026), one pass, rebased onto main `9a4a0fb`

1. **Must-fix 1, no `pkill` of other processes.** `test_the_start_call_returns_while_the_run_goes_on` ran
   `pkill -f "sleep 6"`, ending any same-user process whose command line held it (a `sleep 60`, other lanes' runs).
   The run's command now carries a sentinel of the case's own (its tmp path), the case ends that alone, and a
   bystander `sleep 60` must outlive it. Red by hand on the Mac (`gates/t1p5_pkill_plant.txt`): the old pattern was
   planted confined to the case's own process group, since this Mac runs another session's `lanes_heartbeat.sh watch
   60`, whose `sleep 60` an unconfined plant would have ended; the bystander was ended, the case red for that reason.
2. **Must-fix 2, the gates** at the final head on main, raw output kept (`gates/t1p5_<head>.*`).
3. **Should-fix 3.** The reaper reads each environment whole with `grep -qzxF … "/proc/$1/environ"`: no redirection to
   print its own error, and a value holding a newline then the tag no longer matches (a case; planted). A case also
   asserts a run's log holds no "Permission denied" or "No such file"; as root on the server every environment is
   readable, so that case guards the shape rather than proving the old one red there.
4. **Should-fix 4.** The start is chained on the folder's being made new (`mkdir $run || exit 4`; the rest of its
   set-up `|| exit 5`, each refused in its own words). With `date` and `od` pinned on PATH two runs get one name, and
   the second is refused in words with nothing of it started (a case; planted).
5. **Should-fix 5, `stop <lane>`** (the orchestrator's ruling): TERM to the run's process group (the wrapper is its
   session's leader), up to 15 s for the session to end, KILL to the group and to the run's tag left, then the exit
   file (143, or 137 when a KILL was needed), so the follow ends and the next run is allowed. Tested end to end
   through the verb on the server: cmd.sh, its command and the detached server gone, exit 143, the follow ended, the
   next run allowed. Planted three ways: TERM to the wrapper alone (a KILL then needed, 137), no wait before the KILL,
   no exit written. The usage says Ctrl-C on the Mac ends only the follow, never the run, and `stop` is how a run is
   ended. **The CARRIES row** (row 209's text, sent to the orchestrator rather than edited here): restoring INT on the
   host would not change the Mac's Ctrl-C, which ends only the follow; `stop` is the way.
6. **Should-fix 6, reap fails closed**: reaped only when the run's exit is written, or its recorded pid is non-empty
   and dead with no process of its session alive (cmd.sh and its command outlive a killed wrapper in the wrapper's
   session; a leftover server that made a session of its own does not). Otherwise refused in words, pointing to
   `stop`. `test_reap_ends_what…` writes a dead pid; a new case kills a session's leader and keeps a member alive, and
   reap refuses (planted).
7. **Should-fix 7.** The environment is read again before TERM too. **Not shown red alone**: a pid that changes between
   the scan and the TERM cannot be timed from a test; the KILL pass's re-read (the same function) is.
8. **Should-fix 8.** A case runs pytest with the Makefile's own `-c` and pytest.ini, no `-p`, at `-n 2 --dist
   loadgroup`, on one case under `tests/`, and asserts the controller prints `worker_isolation: 2 workers …`. Red with
   the conftest diff taken back and `-p tests.worker_isolation` on the outer command line. The real gate record keeps
   the header line.
9. **Should-fix 9, `apply_diff.py`.** Atomic across files (each file backed up before the temporaries are renamed; a
   failed rename puts back every file already renamed), CRLF kept, "\ No newline at end of file" honoured on either
   side, the diff split on "\n" alone. A case each in `gates/t1p5_apply_diff.txt`, against the old applier, which lost
   CRLF, reported a newline added while writing nothing, cut a form-feed line in two, and could not apply a diff of two
   files at all.
10. **Minor.** REPORT.md for this step. CARRIES.md is main's on the branch (the INT row's text went to the
    orchestrator). The friction fragment's Makefile wording corrected. `osprey_reap` takes its argument alone: empty is
    refused, never the caller's own tag (a case sets the caller's tag; planted). reap says "No process tagged for the
    run … was found: nothing reaped" when that is so (a case; planted). The live-selection case uses monkeypatch.
