# Brief for the line-fixes session: the merge, and the seats, report their progress for the dashboard

Requested by the owner on 19 November 2026 ("make these runs have intermediate status outputs going forward so that it is
possible to track progress in the dashboard"). The conductor cannot change the line's code (OspreyFlow_Build/scripts/slice_line/
changes only by the owner's hand), so this is a brief, not a change.

## The problem

A merge takes about half an hour (today, SE3: make -k ci about 20 minutes, then make test about 7), and for all of that time
the dashboard shows the slice as "verifying" and nothing else. The owner cannot tell a merge that is working from one that is
stuck, which part of the gate it is in, or how long is left. The board writes OspreyFlow_Build's status file
(status.js, STATUS_FILE in common.py) only after an event (a merge, a verifier record, a stop), never during one. The same
holds, to a lesser degree, for a builder's checks and a verifier's run.

## What to build

1. **A progress record written by the merge as it goes.** One small JSON file per slice in its records folder, rewritten
   (atomically: write beside it, then rename) at the start and end of every step, and every 30 seconds while a step runs:
   - the slice, the tip, the merge's own id (the id in its merge log's name), the process id, and the time it started;
   - the step now running, its number and the number of steps (for example "5 of 9"), and when it began;
   - the steps already done, each with its result (passed, red as expected, red) and its seconds;
   - the log file's path and its size and last-written time, so a stalled step shows (no growth for N minutes);
   - an estimate of the time left, from the seconds the same step took in this slice's previous merge attempts or, failing
     that, in the last three merges of any slice (the records already hold the logs' times); say "no estimate" when there
     is nothing to go on. Never invent one.
2. **The steps are the merge's own**, read from merge_slice.py's docstring and code: the checks before the gate (verifier
   pass at the exact tip, the owner's acceptance if any, main's CI state, the conflict check); the red-before run of the
   acceptance command on the base; the acceptance run and the checks on the tip; the full gate on the merge result, split
   into its parts (each make -k ci target that has its own heading, then make test's parts: the Python run, the live
   collection, the JavaScript run, the line's own suite); the live step if on; the commit and the push. Where a part runs
   many tests, report the test count so far when the runner prints it (pytest's progress lines carry it).
3. **The board reads the record** (board.py): the slice's entry in status.js gains a progress field (step name, "n of m",
   seconds in the step, seconds in the merge, estimate left, and "stalled" when the log has not grown for ten minutes with
   the process alive, or "no process" when the record says running and the process is gone). The board writes status.js
   whenever the record changes: either the merge calls board.py --quiet at each step (cheap, and the board already does
   this after events), or board.py gains a --watch mode the dashboard's page can poll. The first is simpler; it needs no
   new process.
4. **A merge that dies leaves no false "running".** On a clean exit the record is marked finished with its result; the board
   treats a "running" record whose process is gone as "merge stopped without a result" and says so in words. The merge lock
   is the existing check that a merge holds the line; the record must agree with it.
5. **The same for the seats, in a smaller form.** run_seat.py writes the same kind of record for a builder (the round, the
   time since its last commit, the checks' step when the Stop hook runs them) and a verifier (the pass it is on, the
   seconds). If this is too large for the session, the merge alone is the first piece.
6. **The dashboard** (Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/) shows the progress field as a line under the
   slice: "merging: step 5 of 9, make test, 4 minutes in, about 3 left". The dashboard's page is the owner's; this brief
   names the field it will read and nothing else.

## Rules that bind

- Rule 15: each new behaviour has a test that was red first, with the violation planted in the shape the code meets at its
  real call site: a stalled log (the file not growing while the process is alive), a record whose process is gone, a step that
  fails (the record says red, with its seconds), two merges' records not mixing. The line's suite (OspreyFlow_Build/scripts/
  slice_line/tests/run.sh) and plant_faults.py take the new cases, and the README's count of cases and planted faults is updated.
- The record holds no test output and no secret; only names, numbers and times. The records folder is outside the repository
  and stays so.
- The merge's behaviour does not change: the same steps, the same order, the same refusals. A failure to write the record
  must never fail or slow a merge (the write is best effort and says so in the log once).
- README: the section "The line's checks" and the status-file row say what the progress field holds and when it is written.

## Acceptance

With a merge running (a scratch slice whose gate is a short fake), reading the record at any moment shows the step, its
number, the seconds so far and the log's size; a step that sleeps without writing is shown "stalled" after the stall limit
(set small in the test); a killed merge is shown "stopped without a result"; the board's status.js carries the field; the
whole suite is green with the new cases red first.

## Related items already in the backlog

The board's "verifying" label for a slice sent back, and for an accepted slice that has not yet merged (BACKLOG.md, 19 Nov).
The two belong in the same session: they are the same file and the same reading of the records.
