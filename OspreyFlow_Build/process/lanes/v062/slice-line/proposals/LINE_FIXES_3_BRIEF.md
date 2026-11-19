# The third line-fixes session: the unblockers for GG6 and BL6, then the merge's progress record

Written by the conductor on 19 November 2026 for the owner's third line-fixes session, on his decision of that day: GG6 and BL6
are unblocked by this session, not by hand. Not started. Part 1 is deliverable alone; part 2 only if part 1 is done and proved.

## Why

Two slices are verified (GG6 at 496d7b92ce) or accepted by the owner (BL6 at 5cf1cad9ae) and cannot merge, and four faults in
the line's gate made the last day's merges cost hours:

- **GG6** conflicts with main in OspreyFlow_Build/spec/ADR_RESERVATIONS.md (both appended rows at the table's end). The merge's
  "does not merge cleanly onto main: the builder rebases it" refusal records nothing, so the slice stays in phase `verified`,
  and `resume.py` refuses everything: send-back ("was not refused by the merge gate"), add-round ("not stopped at its rounds
  limit"); `run_seat.py builder` ("not in the building phase").
- **BL6** adds four pure tests that build a repository of their own in a temporary folder; the slice-line suite's test
  `test_the_real_scan_map_names_every_pure_walker_and_nothing_stale` fails because the owner-only `scan_map.tsv` has no row for
  them. A row added to main before BL6 merges names a test that is not on main: `scan_select.stale` reports it, and main's own
  suite goes red for every other merge. The slice cannot add the rows (the guard keeps `scan_map.tsv` out of an agent's hands).
- The gate's findings counted BL6's "2 tests" refused: one is the real failure, the other the acceptance command's **expected**
  red on the base (a collection error, `cannot import name 'client_name_check'`).
- SE3's first merge attempt failed because `opentofu-check` could not reach registry.opentofu.org (TLS handshake timeout); its
  second and GG1's first, on `test_stack_lease.py::test_live_runs_exactly_the_selection_from_the_core_folder_with_extra_arguments`
  (a pytest temp folder gone while another pytest run on the Mac was going; GG1's came with nothing else of the line running).

## Part 1, the unblockers (deliverable alone)

**1a. Any merge conflict is recorded, and a send-back for it is free.**
- `merge_slice.py`, in `merge()`, where the merge of the tip into main fails and `records_only_conflict` finds no records-only
  conflict (the raise that says "the builder rebases it"): call `refuse_to_builder` first, with kind `conflict`, the conflicting
  files from `git merge-tree --write-tree --name-only` on main and the tip, and 0 tests, exactly as the records-only case does
  today, then raise as now. The records-only case (kind `records`) keeps its own behaviour.
- `resume.py send-back` for kind `conflict`: works at the rounds limit with **no** `add-round` line and spends **no** round (as for
  `records`); returns the slice to building with the finding naming the files. The builder's one task is to merge main into its
  branch and keep both sides of an append-only change; the brief's section for that is the conductor's. The verifier still
  passes the new tip, and that pass does not count as a round. (A conflict that is not mechanical still ends in the builder's
  hands; whether it needs a round is the owner's, not the line's: the session does not guess.)
- Tests, red first, in the real shape: two rows appended at the end of a table on main and on the branch (conflict, kind
  `conflict`, send-back accepted at the limit with no line, round unchanged); a records-only conflict (unchanged); a conflict
  with no files named by merge-tree (refused in words, not recorded as a slice fault).

**1b. A slice that adds a pure test which walks a folder merges without the owner editing main first, and main is never red
in between.** The owner's suggested shape: the branch itself may add rows to `scan_map.tsv`, only as added lines, each naming a
test file the same branch adds; anything else in that file stays refused. The session may propose a better shape, with its
reasons. **Two constraints it must meet, and the first is not in the suggestion:**
- BL6's tip is verified and accepted for that exact tip (5cf1cad9ae); the acceptance record is for one tip, so BL6's four rows
  **cannot ride in BL6's branch**: a commit adding them would void the accept. The shape must let BL6 merge with its tip as it
  is. Candidates: the merge adds the rows itself in the merge commit, from rows a verifier or the owner proposed and recorded
  at the tip (not from the builder); or `scan_select.unmapped` treats a test the merge result adds, whose own source walks only
  a temporary repository, as mapped with `-` and a reason the line derives; or another. The suite's two checks (`unmapped`: no
  pure walker without a row; `stale`: no row naming a test that is not there) are evaluated on the **merge result** for a
  merge, and on main alone for main's own suite, and both must hold.
- The guard keeps `scan_map.tsv` and everything under `scripts/slice_line/` out of an agent's hands; the shape must say how a
  builder's rows reach the merge without opening that file to it (for example rows in a file the slice adds under a folder the
  line reads, validated at merge: only added lines; each naming a test file the branch adds; no prefix wider than the test
  needs; `-` only with a reason).
- Tests, red first: a branch adding a pure walker with no row is refused in words naming the test; the same with its row
  merges; a row naming a test the branch does not add is refused; a row edited or removed is refused; main's suite stays green
  on main alone (the plant: rows applied without their tests would turn `stale` red).

**1c. The gate's findings parser does not count the acceptance command's expected red on the base as a failed test.** In
`merge_slice.py`, `gate_findings` reads the whole merge log: the red-before run's collection error (an `ERROR … tests/test_….py`
line, or any `FAILED` line before the full gate starts) is the expected result and must not be counted or listed. Test: a log
with a red-before collection error and one real gate failure gives one test, not two; a log with only the expected red gives
none and is not a refusal.

**1d. A gate that fails only because a registry or a download could not be reached is retried once and is not recorded as a
refusal of the slice.** The signatures belong to named steps (the OpenTofu provider registry: "Failed to resolve provider
packages", "could not connect to registry", "TLS handshake timeout"; the Docker pulls; npm and uv downloads), matched in the
step's own output and with **no** failed test of ours in the same log. One retry of the failed step only, said in the merge
log and the merge record; a second failure is recorded as a refusal of kind `network` (not a fault of the slice: no round, no
finding to the builder) and the conductor tells the owner. Never retry on a failed test. Tests: a log whose only red is the
registry timeout is retried and, when the retry is green, merges; the same with a failing test beside it is not retried; two
timeouts in a row give kind `network`.

**1e. The merge gate's pytest runs use a temp base of their own**, so another pytest run on the Mac (a builder's checks, a
verifier, the owner's session) cannot remove their folders: pytest keeps only the newest few `pytest-N` folders per user under
one base, and the merge's long runs lost theirs. Give the full gate's environment (`ci_env`, and the slice's own runs in
`slice_env`) its own base per merge (for example `PYTEST_DEBUG_TEMPROOT` or a `--basetemp` under the merge's temp tree),
removed with the tree. Test: two pytest runs started with different bases do not touch each other's folders; a planted run
that removes the shared base's older folders leaves the merge's alone. Note the other half of the fault: the same test failed
once with nothing else running; it waits for a file its fake lease writes and then reads it. That is a timing fault in the
test (OspreyFlow_Build/tests/test_stack_lease.py, around line 1463; BACKLOG.md has the row) and is **not** in this brief's scope
to change, but the session may say whether a base of its own made it pass.

## Part 2, only if part 1 is done and proved

MERGE_PROGRESS_BRIEF.md, as written (same folder). It is the merge's and the seats' progress record for the dashboard.

## Tests that must fail if a change is wrong (rules 12 and 15)

Each change above has a test that was red first with its fault planted in the shape the code meets (a merge log as the gate
writes it; a real table conflict; a registry timeout line as OpenTofu prints it), and a planted fault in
`OspreyFlow_Build/scripts/slice_line/tests/plant_faults.py` showing the test red with the change disabled. The suite
(the run.sh in the line's tests folder) and the README's counts (244 cases, 176 planted faults at the last count) are updated. No change opens a path
a seat could use to write a pass record, change a scan row it did not add, or merge on a red gate.

## The two real cases, shown working in a dry run (scratch worktrees, never the real slices' state)

1. **GG6's round 6:** a copy of the branch at 496d7b92ce against main as it is: the merge refuses it as a `conflict` naming
   OspreyFlow_Build/spec/ADR_RESERVATIONS.md; `send-back` works at the limit with no line; the builder's one task is to merge main
   in and keep both rows; after that `git merge-tree` is clean and the merge accepts a verifier pass at the new tip.
2. **BL6's four rows:** a copy of the branch at 5cf1cad9ae (accepted for that tip) against main as it is: the four new pure tests
   (tests/test_client_name_check.py, test_client_name_check_compressed.py, test_client_name_check_parallel.py,
   test_client_name_check_paths.py, each walking only its own temporary repository) pass the suite's `unmapped` and `stale` checks on
   the merge result with the tip unchanged; main alone stays green; the gate's findings for the expected red are none.

The conductor then runs the real GG6 send-back and the real BL6 merge.

## How the owner starts it

As the second line-fixes session was started (LINE_FIXES_BRIEF.md, "How the owner starts you"): a worktree on a new branch from
main, a Claude session in it, this brief as the instruction; hand back in the OUT folder as that brief says. No `resume.tsv`
line is needed for the session; GG6's unused `add-round` line stays unused (the new send-back needs none for a conflict).
