# The fifth line-fixes session: the day's batch (the owner's list of 21 November 2026, in his order), then the merge progress brief

Written by the conductor on 21 November 2026 for one quiet window the owner picks. Not started. The conductor cannot change the line's
code (`OspreyFlow_Build/scripts/slice_line/` changes only by the owner's hand), so this is a brief, not a change. **Each item is a fault the
line showed on 20 and 21 November; each gets a test that was red first with the fault planted in the shape the code meets (rules 12 and
15) and a planted fault in `scripts/slice_line/tests/plant_faults.py`.** No item opens a path by which a seat could write a pass record,
clear a stop, push or edit the line. Items 1 to 7 are the owner's list; items 8 and 9 are what the conductor found while applying the
owner's seven lines on 21 November; the merge progress brief comes last.

## 1. The plan-id pattern

`common.plan_ids()` reads the plan page's build ids with `[A-Z]{2}\d+`, which does not match ids with a longer prefix; the diff is written
and checked: `slice-line/proposals/PLAN_ID_PATTERN.diff`. Apply it, with a test that reads a plan page holding one id of each prefix length
in use (read the real page for the longest) and a planted fault (the old pattern put back).

## 2. Records and resume actions while a merge runs

Today `merge_slice.py records` is refused while a merge runs, and the standing accept is refused while any merge runs. A merge takes 25 to
35 minutes and the conductor's work in `OspreyFlow_Build/process/lanes/v062/` (briefs, rows, scan rows, the hold files) waits for it, and a
tracked-file edit there leaves the main checkout dirty, which makes the next merge refuse ("the main checkout has uncommitted changes").
**Read how the merge builds its tree (the temporary merge tree is built from a fixed commit of main) and how it lands the result, and
allow: (a) `records` commits of files under `OspreyFlow_Build/process/lanes/v062/` and `OspreyFlow_Build/spec/` conductor-owned paths while a
merge runs, if and only if the merge's landing step handles main having moved by such a commit (it must not lose the commit, must not
merge a stale tree, and must record the base it tested); (b) the resume actions that touch only the records folder and the slice's own
worktree (`add-round`, `clear-stop`, `send-back`, `accept`) while a merge of a different slice runs.** If the landing step cannot handle a
moved main safely, say so and propose the smallest change that can (for example, the merge re-reads main's tip after the gate and refuses
only if a file the gate tested has changed). Tests: a commit while a merge runs is landed, and the merge's result still contains it; a moved
base that touches a tested path is refused; a resume action on another slice is applied, one on the merging slice is refused.

## 3. The standing accept applied before another round

`standing.tsv` holds the owner's standing rule (`accept-test-gaps from-round 3`: a verifier finding that is only a gap in a test, from
round 3, may be accepted narrower). Today the line spends another builder round on such a finding and applies the rule only at the stop.
**Apply it where the verifier's record is read: if the only open findings are gaps in a test and the slice is at or past the standing
rule's round, the line accepts narrower (recording "standing accept: N gaps in a test for the backlog", as the board already prints) and
does not start a builder round.** Findings of fault in behaviour, any security or key finding, and any slice with a fault and a gap are
never covered. Tests: gaps only at round 3 (accepted, no round); gaps only at round 2 (a round); a fault and a gap (a round); a security
finding (never).

## 4. Lint and the scan-map check in the Stop check

Builders hand back with ruff, eslint or the scan-map check red, and the conductor finds it at the pre-merge check (SE7, PL4c, PL4d2 each
lost a round or a merge attempt to it). **Make the builder's Stop check run, on the files the branch changed against its base, `ruff check`
and `ruff format --check` for Python, eslint for TypeScript, and the scan-map check for every new test under `OspreyFlow_Build/tests`** (the
conductor's `cheap_checks.py` does the three; read it and move its logic into the line). A red here returns the builder to the same round
with the finding, not a new round. Tests: a changed file with a lint error; a new test with no scan-map row; both red, and a clean branch
green.

## 5. `test_layout` in a builder's worktree

The line places a `Claude outputs/slice-line/RULINGS.md` folder at the root of every slice worktree; `tests/test_layout.py::
test_no_product_folder_is_left_at_the_root` fails on it ("still at the root: ['Claude outputs']"), so a slice whose checks include that test
cannot go green in its worktree (PL4d3c stopped for it; BL1b's fix cannot be proved there). **Place the rulings copy where no test of the
repository's layout can see it (the worktree's `.git` information folder is not a root entry; or a path outside the worktree that the
seat's instruction names) or make the test ignore exactly that folder and say why.** Tests: a worktree made by the line passes `test_layout`;
a planted stray root folder still fails it.

## 6. Two seats of one account starting together

Two seats of the same account started in the same moment can race on whatever the line shares per account (the account's window cache or
usage file, its probe, a lock). **Reproduce it first: start two seats of one account within one second against a fake `claude` and read what
is shared (the usage read, the stop file, the window file); make that state written atomically and read under a lock, and make a second
start wait or take the lock rather than fail.** The conductor has no record of the exact failure in the files it read; if it cannot be
reproduced, say so and put the reproduction attempt in the report. Test: two starts at once, both run; the shared file is never half-written
(a planted unlocked write fails it).

## 7. The board shows "the owner's line is in" as its own state

After the owner adds a line to `resume.tsv` and before the conductor applies it, the board still shows the slice as "stopped" or "refused
by the gate", and the dashboard cannot tell a stop waiting for the owner from one the owner has answered. **Show a distinct state, "the
owner's line is in: `<action>` (`<date>`), waiting to be applied", for every slice that has an unapplied line in `resume.tsv`; clear it when
the action is applied.** Tests: an unapplied line shows the state; applied, it goes; a line for a different action than the stop's does not
show it (it will be refused).

## 8. Found on 21 November while applying the owner's lines

1. **`records` and `refreeze` deadlock each other.** `merge_slice.py records` refuses any commit while `slices.tsv` differs in a started
   slice's frozen checks ("that needs the owner's word (refreeze.py)"), and `resume.py <slice> refreeze` refuses unless the main checkout
   differs from main in `slices.tsv` alone. The conductor's other edits (briefs) therefore cannot be committed while a refreeze waits, and the
   refreeze cannot run while they are uncommitted. The conductor got out by setting `slices.tsv` aside, committing the briefs, putting it
   back and refreezing. **Let `records` ignore a `slices.tsv` change that `resume.tsv` already covers with an unapplied refreeze line, and let
   the refreeze ignore other uncommitted files under `OspreyFlow_Build/process/lanes/v062/slices/`.**
2. **`clear-stop` ahead of its `refreeze` starts the builder on the old checks.** `resume.py PL4d3c clear-stop` set the slice to building
   with the frozen checks that had caused the stop, before the refreeze line was applied. **Refuse `clear-stop` for a slice while an
   unapplied `refreeze` line for it is in `resume.tsv`, and say to apply the refreeze first.**
3. **The slice guard misreads some shell shapes.** A command that copied a file into `process/lanes/v062/` and then ran a line script in the
   same `&&` chain, or used a shell variable in a redirect target, was refused as a write outside the conductor's folder or a change to the
   line's scripts. Split commands work. **Parse the redirect target and the script path separately, and resolve simple variables or refuse
   with a message that names the shape.** Test: each shape in both directions.
4. **`resume.py <slice> add-round` on a slice whose phase is "refused by the gate" answers "not stopped at its rounds limit"**, while
   `send-back` accepts it and spends the owner's `add-round` line. **Say in the refusal that `send-back` is the action, or accept the
   `add-round` line for that phase.**

## 9. The fault list of the night (`LINE_FAULTS_2026-11-21.md`, read it whole)

The line's own tests that straddle midnight UTC (take the date once and pass it, or freeze the clock); the two `cloud_platform_backup`
tests that raised `LeaseNotHeld` in one gate and passed in others (find the cause or make the tests pin the lease environment); the dirty
main checkout refusing a merge; a background wait that polls `pgrep -f 'merge_slice.py merge'` matching its own command line (give the
conductor a `merge_slice.py wait-idle` that waits for no merge, so no chain needs `pgrep`).

## Part 2, only if part 1 is done and proved

`MERGE_PROGRESS_BRIEF.md`, as written (same folder): the merge's and the seats' progress record for the dashboard.

## How the owner starts it

As the third and fourth sessions were started (`LINE_FIXES_3_BRIEF.md`, "How the owner starts it"): a worktree on a new branch from main, a
Claude session in it, this brief as the instruction; hand back in the OUT folder as that brief says. **A quiet window means no merge and no seat
running: the conductor holds new starts when the owner names the time, finishes what is running and says when the board is idle.** No
`resume.tsv` line is needed. Until the fixes are applied the conductor carries on as now.
