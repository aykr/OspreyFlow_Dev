# The fifth line-fixes session: the day's batch (the owner's list of 21 November 2026, in his order), then the merge progress brief

Written by the conductor on 21 November 2026 for one quiet window the owner picks. Not started. The conductor cannot change the line's
code (`OspreyFlow_Build/scripts/slice_line/` changes only by the owner's hand), so this is a brief, not a change. **Each item is a fault the
line showed on 20 and 21 November; each gets a test that was red first with the fault planted in the shape the code meets (rules 12 and
15) and a planted fault in `OspreyFlow_Build/scripts/slice_line/tests/plant_faults.py`.** No item opens a path by which a seat could write a pass record,
clear a stop, push or edit the line. Items 1 to 7 are the owner's list; items 8 and 9 are what the conductor found while applying the
owner's seven lines on 21 November; the merge progress brief comes last.

## The owner's first three items (his word of 21 November, "fewer stops for my lines"; they come ahead of everything below)

**A. The line clears a stop itself, with no line from the owner, when the cause is (a) main having moved under the slice, or (b) a fault in the
conductor's brief or checks that changes nothing about what the slice must prove.** Each such clearance is logged (a record in the slice's folder and
a line in a list the conductor's morning report prints: the slice, the stop, the cause (a or b), what the line did, the time). **Still the owner's
alone, and refused by the line without his line:** accepting a slice with open findings; a refreeze that changes what is tested; anything on keys
or security (a stop whose findings name a key, a credential or a security rule is never cleared by the line); any stop at the eighth round.
Design the test for (a) and (b) so they cannot be abused: (a) is "a merge of main into the branch is clean and the slice's own acceptance and
checks are unchanged"; (b) is "the red record's failing check is a check the slice did not write, and it fails identically on main's own tree in the
same worktree shape" (the `test_layout` case: it failed on a tree with nothing of the slice's in it). A check removed from a slice's list by the
line is removed only in case (b), is recorded, and the acceptance test is never the one removed. Tests: each cause clears and logs; each of the four
exclusions is refused; a stop with a finding of fault in behaviour is not cleared; the log lists every clearance.

**B. Each brief's checks are dry-run inside a real builder worktree before the slice starts.** `slice_start.py` makes the worktree, runs each command
in the row's checks column (the acceptance command may be red, as it is red first; every other check must be green on the worktree as it stands
with nothing built) and refuses to start the slice if one cannot pass there, naming the command and the failing test. This is what would have found
`test_layout` before a builder spent six tries on it. Tests: a check that fails in a worktree for a worktree-only cause (a planted extra root folder)
refuses the start in words; a clean row starts; the acceptance command being red does not refuse.

**C. The board writes, for each build, how many of its slices have merged and how many are cut**, so the dashboard shows PL4 as "nine of twelve"
and not as nothing. Read the build id column of `slices.tsv` and the merge records; "cut" is the number of rows for that build id (a row added
later raises it); write it in the status file the board already writes. Tests: a build with three rows and two merged writes "2 of 3"; a new row
raises the cut; a build with no merged slice writes "0 of N", not an absence.

**Also on the owner's word of 21 November, for the conductor (not the line):** the balanced dial is set to 8 rounds in `dial.yaml` and applies to
slices started after it is committed; after a slice's fourth round a read-only scout lists every open case as a table before round 5 starts and
rounds 5 to 8 are judged against that table (no fifth round without it). The line may enforce this (refuse to start round 5 until the table file
exists in the slice's folder); if it is cheap, add that as item D with a test.

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

## 10. The owner's approved decision-record diffs (the owner's word of 21 November: "approved: <diff name>")

When the owner writes "approved: <diff name>" in chat, the conductor applies that diff and commits it with "approved by the owner, <date>" in the message,
then pushes. This covers diffs that touch only `OspreyFlow_Build/spec/06_DECISIONS.md`, `OspreyFlow_Build/spec/ADR_RESERVATIONS.md`, both `DESIGN.md` copies
(`OspreyFlow_Build/spec/design/DESIGN.md` and `OspreyFlow_Core/DESIGN.md`) and `OspreyFlow_Build/process/CLAUDE.md`. It never covers `OspreyFlow_Core/Makefile`,
`.github/workflows/ci.yml`, the release workflow, `harness/signatures.py`, or the owner-only files in the lanes folder (`resume.tsv`, `standing.tsv`,
`dial.yaml`, `accounts.yaml`, `live_step.yaml`). **Today four things stop the conductor** (read from the code): (1) the guard refuses the conductor's shell
writes that name any path outside `OspreyFlow_Build/process/lanes/v062/` (`guard.py` about line 312, which is how `git apply` on a scratch copy of the
specification was refused) and its Edit and Write tools likewise; (2) `merge_slice.py records` commits only paths under `process/lanes/v062/` (about line 998)
and refuses the owner-only files; (3) the guard refuses a direct `git commit` to `main` by an agent, and `push_main.sh` pushes only a tip the merge script wrote
(the trailer rule); (4) `process/CLAUDE.md` is on the guard's protected list. **The smallest change: one new `merge_slice.py` mode, run by the conductor, and nothing
else widened.**

- **The owner's two additions (21 November):** (a) the owner gives the approval in chat as `approved: <name> <hash8>`, where hash8 is the first 8 characters of
  the diff's SHA-256; `approve-diff` takes **both** the name and the hash8, and **refuses if they do not match the file** (the conductor never runs it on a name
  alone); (b) **every report to the owner lists, at the top, each owner-approved diff applied since the last report: name, hash8, commit.** Make the second
  mechanical: `apply-approved` appends a line (name, hash8, commit, date) to a committed list in the records folder that the board prints and the conductor copies
  into the report.
- `merge_slice.py approve-diff <name> <hash8>`: records, in the records folder (`approved/<name>.json`), the diff file's SHA-256, its name and the date, written by the
  conductor on seeing the owner's "approved: <name>" in chat. (The line cannot read chat; this is the conductor's attestation, kept in a committed record the owner
  can audit.)
- `merge_slice.py apply-approved <name>`: refuses unless (a) an approval record exists and the diff file's current SHA-256 equals the recorded one (**"if the diff
  has changed since the owner approved it, ask again" is enforced by the hash**); (b) every file the diff touches is in the allowed set above and none is in the
  excluded set (read the file list from `git apply --numstat`; a rename or a mode change refuses); (c) `git apply --check` passes against main's tip with the main
  checkout otherwise clean; (d) after applying in the merge tree and before committing, the decision checks pass on the result (`tools/adr_reservations_check`,
  `tools/doc_citations_check`, `tools/decision_log_publication_check`, and for `CLAUDE.md` the citation check). It then commits with `approved by the owner,
  <date>` and the names of the diff and its hash in the message, the existing `Slice-Records: yes` trailer **and a new trailer `Owner-Approved-Diff: <name>`**, and
  pushes through `push_main.sh` (whose trailer rule accepts the new trailer and nothing else new).
- The guard allows the conductor to run these two modes (it already allows `merge_slice.py` modes); **it does not widen the conductor's shell writes, its Edit and
  Write tools or `records` mode.** The guard keeps refusing a direct `git apply`, `git commit` or redirect into the specification by the conductor.
- Tests, red first, in the shape the code meets: a changed diff after approval (refused); a diff touching `OspreyFlow_Core/Makefile`, `release.yml`, `ci.yml`,
  `harness/signatures.py` or an owner-only lanes file (each refused); a diff touching one allowed and one excluded file (refused whole); a diff that does not apply
  (refused, nothing staged); a diff that breaks the reservation check (refused, nothing committed); an approval for another name (refused); a stale approval record
  whose diff was deleted (refused); the happy path commits with the trailer and the push check accepts it. Planted faults in `plant_faults.py` for each refusal.

## Part 2, only if part 1 is done and proved

`MERGE_PROGRESS_BRIEF.md`, as written (same folder): the merge's and the seats' progress record for the dashboard.

## How the owner starts it

As the third and fourth sessions were started (`LINE_FIXES_3_BRIEF.md`, "How the owner starts it"): a worktree on a new branch from main, a
Claude session in it, this brief as the instruction; hand back in the OUT folder as that brief says. **A quiet window means no merge and no seat
running: the conductor holds new starts when the owner names the time, finishes what is running and says when the board is idle.** No
`resume.tsv` line is needed. Until the fixes are applied the conductor carries on as now.
