# Faults found in the slice line on its first run, 18 November 2026

Measured by the conductor on main at 4be5838, by reading the scripts and by calling the guard's own functions with
planted inputs (nothing was run that starts a session or pushes). None has a build id in the plan, so none is started
(`CONDUCTOR_BRIEF.md`); and every one is in `scripts/slice_line/` or the installed hooks, which the guard and the merge
script refuse to any slice. They reach the owner as a diff, as `make-ci-wiring.diff` did, or as a session the owner
starts for them.

## The owner's decisions on these, 18 November 2026

- **They wait: build first.** They stay in this file. Not started, no slice.
- **Until F2 is fixed:** the conductor checks GitHub by hand before every merge (`gh run list --branch main`, the
  latest completed run) and does not merge on a red run, nor while the last completed run is unreadable. A run still in
  progress is not a reason to refuse: `push_main.sh` already defers the push.
- **F1, when fixed, takes all three protections:** the wider text match, the launcher check (the seat shim) and the guard
  registered for every session on this Mac.
- **A correction to this file's first draft.** ADR-142 Amendment 9 on main says 77 cases and 68 planted faults, as the
  README does; the conductor read the older copy in `slice-line/diffs/adr-142-amendment-9.diff` (41 and 28). Its sentence
  "while main is red, every merge is refused" **stays**; F2 is what makes it true. Until then it describes a gate that
  is not built (rule 12: no test fails if it is false).

## F1. A seat can start a Claude session the guard does not see

The rule (`guard.py` `SEAT_LAUNCH`, line 80) matches the word `claude`, `claude-sol` or `claude-ayan` only after
whitespace or `; & | ( \``, and only when followed by whitespace or the end. Planted in the shape `check_bash` receives
(the conductor's seat, so only this rule can refuse them), 24 variants:

| Refused | Allowed (not refused) |
| --- | --- |
| `claude -p`, `env claude`, `command claude`, `nohup`/`time`/`sudo claude`, `exec claude`, `xargs claude`, `claude<TAB>-p` | an absolute path (`/usr/local/bin/claude`), a quoted name (`"claude"`, `'claude'`), `$(which claude)`, `claude;ls`, **`bash -c 'claude -p x'`**, `npx @anthropic-ai/claude-code`, `node .../claude-code/cli.js`, a path under `~/.claude/`, a name built in the shell (`${C}aude`), a name built in Python (`"cl"+"aude"`) |

Consequence: a session started that way, from a directory outside the checkout, loads no `.claude/settings.json`, so no
guard (the owner's own certificate session on 18 November was started this way on purpose; its `STEP1_STOPPED.md` says
how). The guard is text-judged (README "What a hook cannot do"), so no regex closes this; a fix has three layers, in
order of strength, and the owner picks: (1) widen the pattern to every quoted, path, `bash -c` and package-runner shape
above, each with a red case, as a floor; (2) register the guard in `~/.claude/settings.json` for every session on the
Mac, so a session outside the checkout still loads it (the guard already runs from a fixed copy; this would also bind
the owner's own other sessions, and how the guard treats a session with no seat was not checked); (3) put the `claude` binary behind a seat
shim, so that a seat's own environment resolves `claude` to a wrapper that refuses unless `run_seat.py` set its one-time
token. (3) is the only one that does not depend on the command's text.

## F2. A red run on main does not stop the line

`merge_slice.py` never asks GitHub anything: its seven conditions are local (lock, frozen, verifier, protected paths,
red-before, green-after, the local full gate). `push_main.sh` asks only `gh run list --status in_progress` and `queued`
(lines 32-39) and defers; a run that has **completed red** changes nothing. So today, if main's run fails, the next merge
is built, tested locally, merged and pushed on top of it, and the board, which does not read GitHub, shows nothing.

ADR-142 Amendment 9's Cost paragraph (on main) says the opposite: "while main is red, every merge is refused". No test
fails if that sentence is false (rule 12): the invariant is stated in prose and implemented nowhere. It has been true of main
twice already: runs 44031786619 and 44040359545 completed `failure` on 17 November.

Wanted (the owner, 18 November): the line stops merging and tells him. Shape: before `merge`, `merge_slice.py` reads the
latest **completed** run on main (`gh run list --branch main --status completed --limit 1`); a `failure` (or `cancelled`
with nothing newer) refuses with the run id and URL; an unreadable answer refuses too (never taken as green, as the live
step's queue is not); `board.py` prints "main is red: run N" and writes it to `status.js`. Records mode is exempt (the
owner must be able to write the stop's own records). Red-first test: a fake `gh` returning `failure`, asserting no
merge, no push, the message, and that records mode still works; planted in the shape the script actually calls
(`gh run list ... --json`), not a bare string (rule 15). The existing `OspreyFlow_Build/tools/ci_status_check.py` is
the likely thing to reuse; it was not read.

## F3. BL1's record is under another name

The set-up merge was recorded by hand as `records/setup-a0dc7ac/merged.json`; `slices.tsv` has the row `BL1`. So the board
shows BL1 as "building" (branch exists, no merge record under its id) and every plan build that "needs BL1" stays
"waiting" on the dashboard. Slices that name `after: BL1` would wait forever; the five drafted rows therefore name no
`after` on BL1. `board.py` will not show BL1 `done` honestly either: it needs a verifier's pass record, and the merge was
by hand. The owner decides whether BL1 is to be shown done by a record he writes, or removed from `slices.tsv`.

## F4. No environment for a product slice's acceptance and checks

`merge_slice.merge` runs the frozen acceptance in two bare detached trees (no `.venv`, no `node_modules`); the full
gate then refuses a tree that already has either (`ci_env`, line 131). So an acceptance command that installs into the
tree breaks the gate, and one that assumes the tree's `.venv` fails before the slice. The drafted commands keep the
Python environment outside the tree (`uv run --frozen` with `UV_PROJECT_ENVIRONMENT` per slice) and, for the Glass,
`npm ci` and remove `node_modules` only where none exists. No product slice has run through this yet: BL6 is the first,
and its first merge attempt is the proof. A change to `merge_slice.py` to build the environment for the acceptance run
would be the cleaner fix.

## F6. `env: full` cannot start a slice

`slice_start.py` line 65 calls `lanes_launch.sh setup slice-<ID>` for `env: full`, and that script knows only the old
lanes (studio, case, admin, rules, platform, docs, demo and their `-b`): "Unknown lane 'slice-SE1'", exit 2, found on the
first start (18 November, nothing written). The five rows therefore carry `env: none` (a plain worktree; the env column
is not frozen), and their commands bring their own environment (F4). A builder in such a worktree has no `.venv` or
`node_modules` until its own command makes one. The fix is a `slice_start.py` that builds the worktree's environment
itself (`uv sync --frozen`, `npm ci`, as `ci_env` does) instead of calling the lanes' script.

## F7. A stopped slice has no way back

Found when BL6 stopped on 18 November (six red Stop hooks: a wrong path in the conductor's frozen checks, `make -C
OspreyFlow_Build` after a `cd OspreyFlow_Core`). Once the checks are corrected (`refreeze.py`, the owner's, and records
mode refuses to commit the change first) nothing returns the slice to `building`: `run_seat.py builder` refuses any
other phase, and the red-stop records stay. `diffs/resume-bl6.sh` does it by hand. The line needs a `resume` step (after
`refreeze`) that clears the stop and logs it. Also: a frozen command is checked by no one before the slice starts; a
dry run of each checks command on the base, in a scratch worktree, would have caught this one in a minute.

## F5. A worktree has no hashed client-name list

`slice_start.py` makes the worktree from git; the list is gitignored. The builder of BL6 cannot see a single hit without
it. The merge gate copies it in (`bring_client_hashes`); a worktree needs the same, once, by the owner after
`slice_start.py` (`cp` from the main checkout into the worktree's `marketing_site/`), or the same call in `slice_start.py`.
