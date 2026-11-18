# Brief: fix the slice line's gaps (the owner's ruling 4 of 18 November 2026)

You are the one session the owner starts **outside the line** to fix the line itself. You edit a copy of it, run its
tests, and hand back one set of diffs and one list of commands for the owner to apply. You apply nothing.

## How the owner starts you (so you can edit a copy of the line and run its tests without the guard refusing it)

The guard reads the repository's `.claude/settings.json` and refuses any edit under `scripts/slice_line/` or `.claude/`,
in any checkout, including a scratch copy. A session started in a folder with no repository and no settings of its own
loads no hooks (the owner's `~/.claude` and `~/.claude-sol` settings register none; checked 18 November). So:

1. From the main checkout: `git worktree add -b lane/line-fixes ~/dev/line-fixes/work main`
2. `cd ~/dev/line-fixes && claude` (the default account was at 7% of its seven-day limit, `sol` at 30%; the owner chooses)
3. Paste: *Read `~/dev/line-fixes/work/OspreyFlow_Build/process/lanes/v062/slice-line/proposals/LINE_FIXES_BRIEF.md` and
   do it. Work only in `~/dev/line-fixes/work`. Hand back in `~/dev/line-fixes/OUT` as the brief says.*

## Where you work, and the rules the guard cannot hold for you

You are started in `~/dev/line-fixes/` (no repository, no hooks of the line). Your worktree is `~/dev/line-fixes/work`,
on `lane/line-fixes`, made from main. Work there and nowhere else. The guard is not loaded in your session, so these
hold by your own discipline, and the owner will read your commands:

- Read `work/OspreyFlow_Build/process/CLAUDE.md` first (the standing rules bind you), then
  `work/OspreyFlow_Build/process/lanes/v062/slice-line/README.md`, `RULINGS.md`, and
  `LINE_FAULTS_2026-11-18.md` beside the README: it holds the measurements this brief rests on.
- **Never**: push, add a remote, change `main`, touch the main checkout, `~/.ospreyflow/` (the installed hooks, the
  records, the manifest) or `~/.claude*` settings; run `install.sh`, `refreeze.py` or `push_main.sh`; start a Claude
  session (the suite's fake `claude` is the only one); touch the GOV.UK demo, airbyte, the test server or any live
  store; write a credential or an email address anywhere; name the UK public sector client or its abbreviation.
- The suite is pure: `work/OspreyFlow_Build/scripts/slice_line/tests/run.sh` (it uses the main checkout's venv from a
  worktree that has none, and throwaway repositories under a temp folder). `plant_faults.py` shows each test red with its
  gate disabled.
- **Rule 15, and the owner's order: every change has a test shown failing first**, in the shape the code meets at its
  real call site (a fake `gh` on `PATH` for a red run, JSON on stdin for a hook, a subprocess in a throwaway repository
  for a script). Save each red run's output under `~/dev/line-fixes/OUT/red/<item>.txt`, then the green one. Add a
  planted fault to `plant_faults.py` for each gate you add, and run it: it must report 0 not caught.
- The line's own files are `OspreyFlow_Build/scripts/slice_line/`, `.claude/`, and the owner's yaml files. You may edit
  the first two in your worktree. You may not change `dial.yaml`, `accounts.yaml` or `live_step.yaml`.
- Commit each item on `lane/line-fixes` as its own commit (Conventional Commits, British English).

## What to build, in this order

**(a) A resume step, and the conductor's own-malformed-command step.** Today `refreeze.py` (the owner's) takes a started
slice's commands from main's backlog row, records mode refuses to commit that row first, and nothing returns a stopped
slice to `building` (F7). Add `resume.py <slice> <action>`, run by the conductor (add it to the guard's `ALLOWED_SCRIPT`,
whole and unchained; builders, verifiers and scouts still refused), actions:
- `refreeze`: commits `slices.tsv` alone (the working copy differs from HEAD in that slice's row only, and only in the
  frozen columns) with the records trailer, and freezes the commands as `refreeze.py` does, keeping the history;
- `add-round`: a slice stopped at its rounds limit gets one more round (round and limit each +1, phase `building`);
- `clear-stop`: a slice stopped on red checks has `red_stop.json` and `red_stops` removed and goes back to `building`;
- every action takes the merge lock (no merge runs meanwhile) and refuses a worktree with uncommitted changes (one agent
  per worktree). The owner has run exactly this by hand in `diffs/allow-bl6-round-3.sh`, `resume-bl6.sh` and
  `resume-ad2.sh`: they are your specification, **except for one thing they got wrong: the rulings.** A worktree is a
  snapshot, so the builder and verifier must read the rulings given since the slice started; but `allow-bl6-round-3.sh`
  did it by committing a copy of main's `RULINGS.md` on the slice's branch, and main's `RULINGS.md` changed several times
  after, so `merge_slice.py merge BL6` then refused ("does not merge cleanly"). Never commit main's records into a slice's
  branch. Deliver the rulings another way (for example an untracked, excluded file in the worktree that the seat prompts
  name; the verifier's checkout is made by `run_seat.py`, so the line adds it there too), and if a branch has fallen
  behind main in the records folder, `resume.py` merges main into it (see `diffs/resume-bl6-merge-main.sh`, proved on a
  scratch copy) and sends the slice for a fresh check. A merge conflict in the records folder alone is never a reason to
  stop a slice.
- **Authority is the owner's written word in a file only the owner can write:** a new `resume.tsv` in `lanes/v062/`
  (guard `OWNER_ONLY`, `merge_slice.OWNER_FILES`, README), one line `<slice> <action> <YYYY-MM-DD, UTC today>`; one line,
  one use, each use logged to `owner-changes.tsv` in the data folder (time, slice, action, detail). Do **not** use
  `RULINGS.md` as the authority: the conductor writes it, so the conductor could authorise itself. Tests: no line, a line
  for another slice, action or day, and a used line each refuse and change nothing; the owner's three yaml files are
  byte-identical after every action; the guard refuses every seat a write to `resume.tsv`.
- **`correct-command` (ruling 3): standing authority, no line needed**, so its limits live in the code, which the
  conductor cannot edit, and not in any file it can. The conductor may correct and resume a slice that stopped **only
  because its own command was malformed**, when: the stop's last red output matches a malformed-command signature
  (start with the two seen: `make: *** <dir>: No such file or directory` and `OSPREY_PORTS_SLOT is not set`; a genuine
  failing assertion never matches); the corrected acceptance and checks name **exactly the same test files** as the old;
  the corrected commands are **proved on main first** in a scratch worktree (checks green minus the slice's own new
  files; acceptance red for a reason that matches no signature); and the use is logged and shown on the board and in the
  conductor's next report ("command corrected: old, new"). Never anything that changes what a check tests. Tests for each
  refusal, including a corrected command that adds, drops or swaps a test file.

**(a2) A step that sends a verified slice back for another round (the owner's order of 18 November, after AD2).** The
merge script refuses on a red gate and leaves the slice in `verified` with nothing that returns it to the builder; the
owner has had to write `diffs/resume-ad2-round-2.sh` by hand (read it: it is your specification, including the findings
record the builder's prompt needs, because `run_seat.py builder` reads only the newest `verify-*.json` for findings).
Build: when `merge_slice.py merge` refuses on a red full gate, it records the failing tests (names and the failing lines
from its log, not the whole log) as a findings record and sets the slice to a phase the board shows ("refused by the gate:
N tests"). `resume.py <slice> send-back` returns it to `building` with those findings in the builder's prompt and the round
advanced, **without an owner line while the slice is within its rounds limit** (it loosens nothing: it is the line's own
rule that findings send a slice back until the limit); past the limit it needs the owner's `resume.tsv` line for
`add-round` as well. It brings main's `RULINGS.md` to the worktree as the other actions do. Test it with AD2's real
case: the branch `lane/slice-AD2` at 993a434 against main, whose merge fails `test_admin_sections.py`.

**(b0) A rule that a slice's checks include every test that scans the files it touches (the owner's order, after AD2).**
AD2's checks named the form's own tests; `test_admin_sections.py`, which walks the workspace's sources and counts the
routes each Admin section reads, was nobody's, so the Stop hook and the verifier both missed what the full gate caught
(`make test`, 7 minutes, at merge). Build a way for the line to know, from the files a slice's branch touches, which
pure tests read those files, and to run them in the Stop hook and the verifier's checks: for example a reviewed map from
a path prefix to the tests that scan it (kept in the repository, shown to be complete by a test that fails when a pure
test walks a source tree the map does not name), or a selector built the way `tools/live_select.py` and
`tools/live_map.tsv` select live tests. The map or selector is the line's, not the conductor's: the conductor cannot
shrink what a slice's checks run. Bound the cost: only pure tests (closed ports), only those mapped to touched paths.
**Required proof:** on `lane/slice-AD2` at 993a434 the Stop hook's selection includes `test_admin_sections.py` and
therefore goes red; on main it is green; and a planted change to a workspace source file that adds an import to a section
is caught the same way. Also report which other known whole-tree scanners exist (`tests/test_doc_citations_check.py` is
one: it reads every document, which is how two briefs turned main red today) and map them.

**(b) A dry run of a slice's frozen commands at `slice_start`.** It refuses to start a slice whose commands do not run.
In a scratch worktree of main: the checks command, minus the slice's own new files, must exit 0 and reach its last step;
the acceptance command must fail for a reason that matches no malformed signature. On 18 November the conductor's first
dry run of a Playwright chain stopped at vitest and never reached the last step, and the slice stopped there six times
later: your dry run must reach the end of a `&&` chain or say which step it did not reach. Test: the two real malformed
commands of 18 November (`make -C <wrong dir>`; Playwright with no port slot) are each refused at start.

**(c) The test settings the Stop hook and the merge script lack (F4, F6, F8).**
- A Playwright slot (`OSPREY_PORTS_SLOT`) for a slice's own runs: the Stop hook and the merge script's acceptance and
  checks runs set none, and Playwright refuses a linked worktree without one (`apps/lanePorts.ts`). Give each slice a slot
  of its own at `slice_start` (see `scripts/lane_ports.tsv` and `tests/test_lane_ports.py` for the table's rules) and set
  it wherever a frozen command runs.
- F4: the merge script runs acceptance and checks in two bare trees (no venv, no `node_modules`) and the full gate then
  refuses a tree that has either (`ci_env`). Build the environment for those runs as `ci_env` does, outside the tree or
  removed before the gate, so a product slice's frozen commands need not carry their own `uv run` and `npm ci`.
- F6: `env: full` calls `lanes_launch.sh`, which knows only the old lanes. Make `slice_start.py` build the worktree's
  environment itself (`uv sync --frozen`, `npm ci`), or drop `env: full`.
- With these in, the five current rows' own `export OSPREY_PORTS_SLOT=` and `UV_PROJECT_ENVIRONMENT=` prefixes become
  unneeded; say how the owner updates them (this is `refreeze` territory).

**(d) The hashed list reaching a slice's worktree without the owner (F5).** `slice_start.py` copies
`marketing_site/client_names.local.sha256` from the main checkout into the worktree when it exists, and only where git
ignores it there (as `bring_client_hashes` checks); it says in words when the main checkout has none. Never commit it.

**(e) Usage per slice, seat and account.** Recorded rows exist now (`~/.ospreyflow/slice-line/usage.tsv`, one per seat
session: slice, seat, account, model, tokens, list-price cost, the account's five-hour and seven-day shares), and
`board.py --usage` prints them. Check what is still missing and add it: the conductor's own session (one row per
session, the SessionEnd hook: none has appeared), the default account's `five_hour` window (the stream gives it only
`seven_day`), a total per account and per slice, and the account windows beside them. Say in the output that cost is a
list-price estimate, not a bill.

**(f) A red GitHub run stops merging and shows on the board (F2).** `merge_slice.py merge` reads the latest completed run
on main (`gh run list --branch main --status completed --limit 1`), refuses on `failure` (and on `cancelled` with nothing
newer) naming the run, refuses when `gh` cannot be read (never taken as green), and `board.py` prints "main is red: run N"
and writes it to `status.js` (the dashboard shows it). Records mode and the owner's own scripts are exempt. Test with a
fake `gh` on `PATH`, in the shape the script calls (`--json` fields), not a bare string. ADR-142 Amendment 9's sentence
"while main is red, every merge is refused" stays; this makes it true.

**(g) F3 is done** (the owner ran `diffs/record-bl1-done.sh`; the board shows BL1 done). **Then F1's three protections:**
1. the wider text match in the guard, with a red case for each of the 24 variants in `LINE_FAULTS_2026-11-18.md`;
2. the launcher check: a seat's environment resolves `claude` to a wrapper that refuses unless `run_seat.py` set its
   one-time token, so a refusal does not depend on a command's text;
3. the guard registered for every session on this Mac (the owner's `~/.claude/settings.json` and
   `~/.claude-sol/settings.json`), through `install.sh`. This binds the owner's own sessions too: before you build it,
   read what the guard does with a session that has no seat today, and say in `COMMANDS.md` which rules would bind the
   owner's own sessions and which would not. Do not change the guard's treatment of the owner's own sessions beyond the
   owner's word in this brief.

## What you hand back, in `~/dev/line-fixes/OUT/`

- `patches/000N-<item>.patch`, one per item (`git format-patch main..lane/line-fixes`), each applying to main;
- `COMMANDS.md`: the exact commands for the owner, in order, with what each does: `git am` or merge of the branch, the
  files that need `install.sh` to copy the hooks (the manifest hashes them), any line the owner writes by hand
  (`resume.tsv`), the settings files the owner edits, and the new gate counts for the README (the ADR text names 77 cases
  and 68 planted faults: do not edit the spec, say what the numbers become);
- `red/` and `green/`: the failing and passing output for every test;
- `NOT_DONE.md`: anything you could not do or prove, and every decision you needed and made, with why.

Stop and write to `NOT_DONE.md` rather than guess where this brief and the code disagree.
