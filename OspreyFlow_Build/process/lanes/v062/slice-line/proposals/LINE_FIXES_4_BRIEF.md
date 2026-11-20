# The fourth line-fixes session: GitHub is a second opinion, not a gate; then the merge's progress record

Written by the conductor on 20 November 2026 for the owner's fourth line-fixes session, on his ruling of that day. Not started. Part 1
is deliverable alone; part 2 only if part 1 is done and proved.

## Why

The line's merge gate refuses every merge while GitHub's last completed run on main is red (`merge_slice.py` about line 690, from
`common.main_ci()`; ADR-142 Amendment 9's Cost sentence: "while main is red, every merge is refused"). On 20 November 2026 a run on a
commit that changed only a scan-map row file failed in `conformance` on one test (`ArcadeDBError 404: Remote transaction session not
found or expired`, after a 58-minute job, the transaction expiry the project already knows), and the line refused GG6, PL2a and PL2b,
all verified, for the hour a rerun takes. Separately `push_main.sh` pushed straight after that red run finished (it defers only while a run
is in progress). The owner's ruling of 20 November:

- Merges go on the Mac's full gate alone, whatever GitHub's last run says.
- Every merge is pushed, waiting only while a run is in progress, so GitHub always tests the newest main.
- A red run is rerun once without asking. Only a test of ours failing twice stops merging and comes to the owner, with the job, the
  test and the commit.
- A release still needs GitHub green on the commit released.

This replaces items 2 to 4 of the 18 November ruling on GitHub failures (`RULINGS.md`) and the sentence in ADR-142 Amendment 9.

## Part 1, the five changes (deliverable alone)

**1a. `merge_slice.py` no longer refuses on a red run.**
- Remove the refusal at about line 690 (and the "unknown" refusal with it: GitHub being unreadable is not a reason to hold a merge
  the Mac's gate passed). Keep `common.main_ci()` as the reader.
- Record the state instead: `merged.json` carries `github_at_merge` (`state`, `run`, `url`, `why`, the time) and the merge prints one
  line saying it ("GitHub's last run on main: red (run N), not a gate; merging"). A record, never a decision.
- The other refusals stay as they are (the verifier's pass for the exact tip, red-before and green-after, the full gate, the
  protected paths, the lock, a dirty main checkout).
- Tests, red first: `OspreyFlow_Build/scripts/slice_line/tests/test_main_ci.py` today asserts the refusal; change it to assert the merge carries on with the state
  recorded, for red, for unknown (gh unreadable) and for green, in the shape `gh run list --json` gives; the plant is the old refusal
  put back.

**1b. `push_main.sh` pushes after every merge, and defers only for a run in progress.**
- It already defers only for an in-progress or queued run (lines about 32-40) and does not look at a completed red run: keep that, and
  add a test that a completed red run does **not** defer a push (the rule now), and that an in-progress and a queued one do. (Rule 15:
  fake `gh` on `PATH` answering as the real `gh run list --status ... -q length` does.)
- A deferred push must not be forgotten. Today it waits for "the next merge's push". Add `merge_slice.py push-pending`: if
  `push.pending` exists and no run is in progress or queued, run the push; the board (`board.py`) prints "push pending (commit)" while
  one waits, and the conductor runs `push-pending` when a run ends. The guard still refuses `push_main.sh` to an agent's command line;
  `push-pending` is a conductor command like `merge` and `records`.
- Tests: pending written on a deferral, cleared on a push, `push-pending` pushes only when nothing is in progress, and refuses when
  main's tip was not written by the merge script (the existing trailer rule).

**1c. A test of ours failing twice stops merging, until the owner clears it.**
- New `merge_slice.py watch-github` (a conductor command, also run by `merge` before it starts and by `push-pending`): for the latest
  completed run on main that is red, read the failing test names (the `FAILED ` lines of `gh run view <id> --log-failed`; a job that
  failed on a download, a network fault or a runner with no `FAILED` line names no test and is never a stop). Record each run's
  failing tests in `~/.ospreyflow/slice-line/records/github/<run>.json`.
- **The stop:** the same test name failing in a run and in the **rerun of the same commit** (a second completed attempt of the same
  run, or the next run on the same head) writes `~/.ospreyflow/slice-line/github.stopped.json` (the test, the job, the commit, both
  runs). While it exists `merge_slice.py merge` refuses, in words that name the test, the job and the commit and say the owner clears
  it. A first red, a red that passes on rerun, and a different test failing on the rerun write nothing.
- **The owner's command to clear it:** a new script, clear_github_stop.py, beside the line's other scripts, like `clear_account.py` (executable; run by the owner;
  the guard refuses it to an agent; it removes the file and appends a line to `owner-changes.tsv`'s sibling record for audit; refuses
  if there is no stop). Register it everywhere `clear_account.py` is registered (guard, install, the registration test).
- Tests, red first, in the shape the code meets: a `gh run view --log-failed` text as GitHub prints it (the real shape from 20
  November: pytest's `FAILED ../OspreyFlow_Build/tests/...::name - ...` summary line), once red then green (no stop), red twice on one
  test (stop; merge refused in words; clear works; merge proceeds), red twice on different tests (no stop), red with no `FAILED` line
  (no stop), `gh` unreadable (no stop, no refusal).

**1d. The release check reads GitHub green on that commit.**
- `OspreyFlow_Build/tools/release_local.py` (and `OspreyFlow_Build/scripts/publish_user_repo_update.sh` where it releases) refuses a
  release unless the **latest completed attempt of a run on exactly the commit released** concluded `success` (`gh run list --commit
  <sha> --status completed --json conclusion,databaseId,attempt`; a rerun that passed counts; a green run on another commit does not;
  none, or gh unreadable, refuses in words and names the commit). Read how the existing release refusal for owed live tests
  (`tests/test_release_owed.py`) is built and add this beside it.
- Tests, red first: a run green on the parent but none on the commit; red then green rerun (accepted); red only; gh unreadable.

**1e. The ADR-142 sentence, as a diff for the owner.** Already written and checked with `git apply --check` against main:
`proposals/ADR142_AM9_COST_SENTENCE.diff` (it replaces "and for main's own gate to be green: while main is red, every merge is
refused" in Amendment 9's Cost paragraph). The session does not edit `spec/06_DECISIONS.md`; the owner applies it. The session also
brings `slice-line/README.md` (the gate, the push step and the GitHub paragraphs) to the new rule, and `RULINGS.md` is the conductor's.

## Part 2, only if part 1 is done and proved

`MERGE_PROGRESS_BRIEF.md`, as written (same folder): the merge's and the seats' progress record for the dashboard.

## Tests that must fail if a change is wrong (rules 12 and 15)

Each change has a test that was red first with its fault planted in the shape the code meets, and a planted fault in
`OspreyFlow_Build/scripts/slice_line/tests/plant_faults.py` showing the test red with the change disabled. The suite (`OspreyFlow_Build/scripts/slice_line/tests/run.sh`) and
the README's counts (317 cases, 245 planted faults at the last count) are updated. No change opens a path a seat could use to write a
pass record, clear the stop, or push; `clear_github_stop.py` and `push_main.sh` stay refused to an agent's command.

## The real case, shown working in a dry run (scratch copy of the records, never the real state)

Run 44681092481 (20 November, `conformance`, `test_typology_rules.py::test_an_alert_explains_itself_with_its_transactions_links_and_node`,
one failure in 3,598, the 404 above): a first red writes no stop and does not hold a merge, the merge records `github_at_merge` as red;
if the rerun fails on that test too, the stop is written and a merge refuses naming the test, the job and the commit; the clear command
removes it. And the 20 November case of a push straight after a red completed run is now the rule, shown pushing.

## How the owner starts it

As the third session was started (`LINE_FIXES_3_BRIEF.md`, "How the owner starts it"): a worktree on a new branch from main, a Claude
session in it, this brief as the instruction; hand back in the OUT folder as that brief says. No `resume.tsv` line is needed.
Until the fixes are applied the conductor carries on as now: reruns the red run, merges when main is green, and says so.
