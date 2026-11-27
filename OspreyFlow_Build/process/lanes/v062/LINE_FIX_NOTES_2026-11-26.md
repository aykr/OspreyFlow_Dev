# For line-fix, from the conductor (26 November 2026)

Written for the owner to hand on. Nothing here changes a switch; each item is the owner's to rule and line-fix's to build.

## 1. Hand-back 60 (the merge train): what it needs to take the server's tested stack as one gate run

The owner, 26 November: "after it lands, I want the train to take the server's tested stack (main plus A, B, C) as one
gate run".

1. **The same tree, proved.** The server's stack run already names each candidate's tree hash (`early_warning.py`: "the
   candidate tree hash", main+A, main+A+B, main+A+B+C). The train runs the Mac's gate once, on main+A+B+C, only when its
   own merge result has the server's last tree hash byte for byte, and main has not moved except by records outside
   `scan_rows/` and outside every file the stack carries (today's rule for one slice, applied to the stack).
2. **Per-slice checks still per slice.** Each slice's red-before (its acceptance failing on its own base: main for A,
   main+A for B, main+A+B for C), its own acceptance and checks green on the full merge result, and its own verified or
   accepted tip, unchanged since that record. A slice whose tip moved leaves the train.
3. **What a red does.** If the one gate run is red, nothing lands. The train says which slice the failing test belongs
   to, when that can be told from the server's per-candidate results (main+A green, main+A+B red: B). Otherwise it
   refuses all, in words, and the conductor falls back to one merge at a time. Never a partial landing that was not the
   tested tree.
4. **One landing, one push.** Main is fast-forwarded once to the tested commit (A, B and C's merge commits in order, as
   today's merges write them). `push_main.sh` runs once, and the board shows each slice merged with the train's run id.
5. **Records during a train.** The train holds the merge lock for its whole run, so the records commit rule (only at a
   merge's start, never during) holds for the train as one merge.
6. **The early warning's refusal to re-test.** `early_warning.py A B C` refuses a stack whose first slice already has a
   green on this main ("a stack would test it again", today with GR4a). For the train, a stack of the next three
   verified slices should be sendable whatever is already green. Or the refusal should say how to send it.

## 2. Proposal 1 (the owner sends it now): two server runs side by side

The runner refuses a second job "busy", and one job holds at most 3 slices, so today seven verified slices queued for
the server about 50 minutes each. **Proposal:** the runner takes a second stack when the build account has room, each run
in its own D246 namespace with its own loopback and ports (the away rounds already run this way), and at most two at
once. The 14 November rule (two `make test` runs OOM-killed platform B's ArcadeDB) should set the limit: a second run
only when no store load is running on the server.

## 3. Line faults found today

1. **Round tables below round 5 never reach a builder.** `common.py` `round_table` returns None below `TABLE_ROUND`
   (5), and `run_seat.py` gives the builder the brief from main plus the verifier's findings only. A conductor's
   instruction for rounds 1 to 4 that is not in the findings is lost. SE8g stopped twice on the owner's ruling it never
   saw. Fix: give the builder its round's table at every round when one exists, not only from round 5.
2. **`server-rerun` runs a vitest test under pytest in a shell string** (RM1a, 25 November): the apostrophe in "§5's"
   breaks the command, and that is recorded as red. Also, a newer green server run on the same tip was ignored.
3. **`scans` checks a branch against main's scan map:** a branch cut before a newly mapped test goes red for a file it
   never had (AD1c and GG2a, both lacking SE8f's guard file).
4. **The early warning's lists (`demo_server/lists.tsv`) have no row for AD1c's container test**
   (`tests/harness/test_gateway_token_reader_role.py:93`, one `docker run` of `postgres:16.4` by digest). This is the
   owner's hand-back 63.
5. **The guard refuses a records edit that merely names the line's scripts folder in its text** (a citation fix to
   `slice-line/README.md:131` writing `OspreyFlow_Build/scripts/slice_line/tests/run.sh`). The edit was to the README,
   not the scripts.
6. **`pgrep -f 'merge_slice.py merg[e]'` matches the shell running the check itself** when it sits in the same command
   line (already line fault 4 of 21 November; still bites).
7. **`server-rerun` cuts a parametrised test id at its first space** (SE9f, 26 November): `…::test_the_check_fails_for_each_planted_fault[a cited route line …]` ran as `…[a`, pytest said "not found … no tests ran", and that was recorded as "red on the Mac too (7 s)". The whole file, run by hand, gave the real result (1 failed, 51 passed).
8. **The slice line's own suite fails when it runs across midnight UTC** (CO3b's merge, 27 November 00:01-00:04 UTC): `test_owner_line_waiting.py` (two cases) and `test_round_after_refusal.py::test_round_after_refusal_at_its_budget_gives_no_more_today_and_the_board_says_so` hold `TODAY` from when the module was imported, while the code reads the clock again. The gate was refused for this alone (3 failed, 1025 passed), and the merge was run again. Fix: the tests should freeze the clock the code reads, or work out `TODAY` inside each test.
9. **A builder sent back to take main in, which aborts the merge and ends on a question, is recorded "green; ready for the verifier"** (GR1b, 27 November 08:01): its checks were green on the unchanged old tip, which still conflicts with main. A take-main-in round should not end green unless main is an ancestor of the new tip.
