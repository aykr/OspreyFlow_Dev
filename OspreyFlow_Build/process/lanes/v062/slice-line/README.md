# The v0.6.2 slice line

Set up 17 November 2026 on `lane/slice-line-setup` (build BL1), on the owner's settings of that day. One
conductor; scouts, builders and verifiers that each carry a slice; gates that are scripts and hooks, not
paragraphs. A dial trades speed against tokens without touching any gate. Claude Code 2.1.326.

## Who sits where

| Seat | Definition | Runs as | Account (accounts.yaml) |
| --- | --- | --- | --- |
| Conductor | `.claude/agents/slice-conductor.md` + `CONDUCTOR_BRIEF.md` | the owner's interactive session: `run_seat.py conductor` | `seats.conductor` (default) |
| Scout | `.claude/agents/slice-scout.md` (Read, Grep, Glob) | a subagent of the conductor | always the conductor's (a subagent cannot run on another account) |
| Builder | `.claude/agents/slice-builder.md` | its own `claude -p` session, in the slice's worktree: `run_seat.py builder <ID>` | `tracks.<n>` (1: default, 2: sol) |
| Verifier | `.claude/agents/slice-verifier.md` | its own `claude -p` session, on a detached copy of the tip: `run_seat.py verifier <ID>` | `seats.verifier` (sol) |

Every builder is its own session, on either account, rather than an `isolation: worktree` subagent: a subagent
runs on its parent's account; Claude Code names a subagent's branch `worktree-<name>` (ADR-142 wants
`lane/<name>`); and a subagent's worktree branches from `origin/main` by default, which lags local `main` between
a merge and its push (pushes wait while main's CI runs). A builder started on its own gets the Stop gate as its
own session's Stop hook, an exact per-slice usage figure, and the same launch on both accounts.

**Permission mode** of the separate sessions: `dontAsk`, with each seat's tools pre-allowed (builder: Read, Grep,
Glob, Edit, Write, Bash; verifier: Read, Grep, Glob and `git diff|log|show|status`). Anything else is denied,
never prompted. The guard runs before the permission check in every mode, so the mode never widens a gate.

## Where the guard runs from

`install.sh` (the owner's) copies `guard.py`, `stop_check.py` and `usage_hook.py` to
`~/.ospreyflow/slice-line/bin/` (read-only, SHA-256 in `manifest.json`) and writes `settings.json` there. Every
hook command names that fixed copy, never a worktree's. The repository's `.claude/settings.json` registers the
guard for every session in the repository (beside the graphify hooks); each seat is also started with
`--settings ~/.ospreyflow/slice-line/settings.json`, so its hooks hold even if a worktree's settings were changed.
A missing guard fails closed: the hook exits 2 and every tool call is refused.
`install.sh --register-everywhere` (only with the flag: the owner's word, 18 November 2026) also registers the guard
in every account's own settings on this Mac (`~/.claude`, `~/.claude-<account>`), so a session started outside the
checkout loads it too; that binds the owner's own sessions in every repository by the rules the guard applies to a
session with no seat.

**The seat shim** (`seat_shim.sh`, F1): `install.sh` installs it as `bin/shim/claude`, `claude-sol` and `claude-ayan`
(read-only, in the manifest). `run_seat.py` starts every seat through it, with the shim's folder first on the seat's
PATH and a one-time launch token it has just written to the data folder; the shim runs the real `claude` only for
that token, removing it, so the session never holds one. Any `claude` a seat runs itself meets the shim's refusal,
whatever the command's text. An absolute path to the real binary, or `npx`/`node` running the package, does not pass
through the shim: the guard's text match (`SEAT_LAUNCH`) is what refuses those.

**A seat refuses to start unless the guard is loaded** (`run_seat.py`): the installed files, the seat shim included, must match
the manifest; the fixed settings must register them; no settings file the session reads may set `disableAllHooks`;
the account must be signed in and not stopped; and the session's own SessionStart hook must answer with the
launch's one-time token before the prompt is sent (the prompt goes over stream-json input only after that).

## Gates and their proofs

`OspreyFlow_Build/scripts/slice_line/tests/run.sh` (411 cases) plants each violation in the shape its real call
site produces; `OspreyFlow_Build/scripts/slice_line/tests/plant_faults.py` shows each test red with its gate disabled (323 planted faults, 0 missed). `make ci` runs the suite (`slice-line-check`), and so does its own CI job.

| Gate | Where | What refuses |
| --- | --- | --- |
| The owner's files | guard | Edit/Write of `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`; shell writes naming them; `dial.yaml`, `accounts.yaml`, `live_step.yaml`, `resume.tsv`, `standing.tsv` |
| Never staged | guard | `git add`/`commit -a` that would take `OspreyFlow_Core/osprey.yaml` or `OspreyFlow_Core/data/` |
| No push, remote or repository | guard, push_main.sh | every `git push`, remote change, `gh repo create/edit`, write `gh api`; the push script refuses all but a merge-written main to the recorded origin, fast-forward only |
| A builder in its worktree | guard | edits, `cd`, `-C`, `GIT_DIR`, writes naming another checkout; branch switches |
| Only the merge script writes main | guard, merge_slice.py | commit/merge/reset/rebase/pull on main; `update-ref`, `branch -f`, `fetch .:main`, `checkout -B main` |
| No credential or address | guard (tool calls), Stop hook (final text) | key patterns; the owner's addresses by SHA-256 (`emails.sha256`) |
| GOV.UK demo, airbyte | guard | `govuk.ospreyflow.app`, `/opt/ospreyflow*`, `osprey-small`, `:8000`, airbyte/abctl; any hand change on the test server |
| The line itself | guard, merge_slice.py | `.claude/`, `scripts/slice_line/`, the records, the status file, `OSPREY_*` overrides, nested `claude` |
| Cannot stop on red | stop_check.py | the frozen checks and acceptance run at Stop; red (or uncommitted) sends back the failure lines only; after 6, stopped |
| GitHub's run on main | merge_slice.py, board.py | nothing: a second opinion, not a gate (the owner, 20 November 2026). Each merge records the latest completed run on main (`github_at_merge` in `merged.json`) and goes on, red, cancelled or unreadable; the board prints "main is red: run N" as a note and `status.js` carries it (`main_ci`) |
| A test of ours red twice on GitHub | merge_slice.py, board.py, clear_github_stop.py | every merge while `github.stopped.json` is there (below), in words naming the test, the job and the commit; the board prints "merging stopped: ..."; only the owner's `clear_github_stop.py` (refused to every agent) removes it |
| Merge | merge_slice.py | see the script's docstring: lock, frozen match, verifier pass for the tip, protected paths, red before, green after, **today's full gate**: `make -k ci` and `make test`, both run and both reported, in the merge tree's own environment built as CI's `test` job builds it (`uv sync --frozen` on the `UV_PYTHON` `ci.yml` sets, `npm ci` under the Node major `ci.yml` names, no `VIRTUAL_ENV` or other `.venv/bin`, closed ports, the merger's slot), never the main checkout's; then **the live step** (below) |
| Status file | board.py | `done` only with a merge record, its test run and a verifier pass; unknown build ids reported, not written; a bad or incomplete record skipped and reported, the slice shown from its other records and every other slice carried on |

**What a hook cannot do** (documented, not worked around): no hook can stop text the model has already shown (the
Stop hook catches a key or address in a final message and forces a correction, after the fact); shell commands
are judged by their text, so a command that computes a path can slip past the guard; the merge script's diff
check is the backstop that does not depend on the text. Claude Code caps a Stop hook at 8 consecutive blocks
without a tool call; the line's own cap is 6 red stops.

## A slice's life

1. The conductor writes `slices/<ID>.md` from `SLICE_BRIEF.template.md` and its row in `slices.tsv`, and commits
   them with `merge_slice.py records`. The build id must be one of the plan's (`dashboard/index.html`).
2. `slice_start.py <ID>`: first a **dry run** of the acceptance on main in a scratch worktree (`dry_run.py`): it
   must be red for a reason no malformed-command signature matches. Then the checks **in the slice's own
   worktree**, made as the builder will have it (the rulings copy at `Claude outputs/slice-line/`, the hashed
   client names, env: full's environment) with nothing built, in the Stop hook's environment: every step of
   the `&&` chain must be green there, the slice's own new files stood in by placeholders, and leave no file
   git does not ignore (LINE_FIXES_5_BRIEF.md, B: `test_layout` failed on the rulings copy at the root, which
   the scratch tree never had). A red run names the step and the failing tests, and the worktree and the
   branch are removed: nothing is frozen. Then worktree `~/dev/osprey-wt/slice-<ID>` on
   `lane/slice-<ID>`; the acceptance and checks commands **frozen** (a change needs the owner's word: `resume.py`
   refreeze, or the conductor's own `correct-command`); account, track, dial setting, rounds fixed; and a
   **Playwright port slot** of the slice's own (from 16 up, clear of `scripts/lane_ports.tsv`'s lanes, of every
   unmerged slice's slot, and of the stacks' and the owner's ports), set wherever its frozen commands run: the dry
   run, the builder's session and its Stop hook, and the merge script's acceptance and checks runs. `env: full`
   builds the worktree's own environment as CI builds it (`uv sync --frozen`, `npm ci` under CI's Node); the
   lanes' launcher is not used.
3. `run_seat.py builder <ID>` until green, then `run_seat.py verifier <ID>`. Each finding in the verifier's record
   (`verify-<tip>.json`) has a `kind`, `fault` (in behaviour) or `test_gap` (a gap in a test), a required field of the
   verdict's schema; any other value, or none, is no kind, which counts as a fault (a record written before the field is
   read by its findings' prefixes "FAULT IN BEHAVIOUR:" and "GAP IN A TEST:", and only such a record), and the record counts them (`kinds`). Findings go back to the builder
   until the rounds limit; then the slice stops and its note names the split and the one decision the owner must make.
4. `merge_slice.py merge <ID>`: a verifier's pass for the tip, or in its place, for that exact tip only, the owner's
   acceptance (`accepted-<tip>.json`, behind it the verifier's unchanged findings record for the tip and its use logged
   in `owner-changes.tsv`); a tip that moved after the acceptance has neither. Then the acceptance (red before) and the checks and scans (green after) run in an
   environment built as CI builds it, its venv outside the tree, with the slice's slot; `node_modules` is removed
   before the full gate, which builds its own. Then main fast-forwarded to the tested merge commit, then `push_main.sh` (every merge is pushed; only a run on main in progress or queued defers it: below). A red full gate
   (or a merge refused for a conflict with main: kind `records` in the records folder alone, kind `conflict` for any other, with the files `git merge-tree` names; a merge that fails with no file named is refused in words and not recorded) leaves the slice `refused`: the failing tests and
   their failing lines (not the whole log) are written as a findings record (`verify-gate-<tip>.json`), the board
   shows "refused by the gate: N tests", and `resume.py <ID> send-back` returns it to the builder with those findings.
   A slice merged on an acceptance has `accepted_findings` (the count, the text, the split) in `merged.json`; the board
   prints "merged, accepted narrower: N findings" and `status.js` keeps the findings (`accepted_findings`) for the
   conductor's next report.
5. `board.py` prints the board and writes `status.js` after every merge, verifier record and stop. For each build
   it writes how many of its slices have merged and how many are cut (its rows in `slices.tsv` on main; a row
   added later raises it): `slices` ("9 of 12"), `slices_merged` and `slices_cut` on the build's entry, and
   `build_slices` for every build of the plan with rows, so a build with none merged says "0 of N".

## The merge gate's findings, retries and temp folders

The gate's findings (`gate_findings`) leave out every run in the red-before tree (`slice-<ID>-before-*`): its red is the acceptance command's expected result, never a failed test of the slice (BL6's "2 tests" of 19 November 2026 were one real failure and the expected collection error). A log with only that red gives no finding.

A step of the full gate (`make -k ci`, `make test`, and the environment's `uv sync` and `npm ci`) that fails only on a network step (a registry or a download that could not be reached, matched in that step's own output: OpenTofu's provider registry, Docker's pulls, npm's and uv's downloads; no failed test of ours, and no failed make target but `opentofu-check` and `chart-check`) runs once more, said in the log as `RETRY`; a retry that goes green is named in `merged.json` (`retried`). Two in a row are a refusal of kind `network` (`refusal-network-*.json`): not the slice's fault, no round, no finding to the builder; the conductor tells the owner and runs the merge again. A failed test is never retried.

Every pytest run of the merge has a temp base of its own (`PYTEST_DEBUG_TEMPROOT`): the slice's acceptance and checks under the merge's environments folder, the full gate beside its tree (`<tree>-pytest`), each removed with the merge's trees, so another pytest on the Mac (which keeps only its newest few `pytest-N` folders under the shared base) cannot remove the merge's (SE3 and GG1, 19 November 2026).

## The scans a slice's checks include

A slice's checks name its own tests; a pure test that walks the repository (as `test_admin_sections.py` walks the
workspace's sources, which AD2's checks did not name, so only the full gate caught it, seven minutes into the merge)
belongs to no slice. `OspreyFlow_Build/scripts/slice_line/scan_map.tsv`, the line's (no conductor or slice can change
it), maps each pure test that walks a folder to the path prefixes it walks, or to `-` with why it is not selected (it
walks only its own temporary folder, or it runs Docker and is not pure). The Stop hook runs, beside the frozen checks
and acceptance, every mapped test whose prefixes a path the slice's branch changes (against its base) falls under and
which the slice's own commands do not already run, on the worktree's own environment with closed ports; red is red,
and the test record names the scans it ran, so the verifier sees them. A scan map that cannot be read is red.
`scan_select.unmapped()` proves the map complete: a pure test (not in `make test`'s `--ignore` list) whose source, or
a `tools/` module or test helper it imports or runs, walks a folder, with no row, fails the line's suite; so does a
row naming a test or a prefix that is not there. `install.sh` installs the map and `scan_select.py` beside the hooks.

**A slice that adds a pure walker** (19 November 2026, for BL6): its rows wait on main in `OspreyFlow_Build/process/lanes/v062/scan_rows/<ID>.tsv`, committed by the conductor in records mode from rows the verifier or the owner proposed (never from the slice's branch: that folder is a protected path), in the map's own columns. Nothing in main's suite reads them, so main stays green while they wait. The merge applies them to `scan_map.tsv` in the merge commit itself and removes the file, only as added rows, each naming a test file the branch adds, with no row yet, and a why; then it checks on the merge result that no test the branch adds or changes walks a folder without a row, and that no row names a test the branch removes. A refusal is in words, not the slice's fault. The slice's tip is unchanged, so a verifier's pass or the owner's acceptance for it still holds; `merged.json` names the rows (`scan_rows`). The Stop hook reads the installed copy of the map, which `install.sh` refreshes.

## GitHub: a second opinion, not a gate

The owner's ruling of 20 November 2026, after run 44681092481 failed in `conformance` on one test (ArcadeDB's expired transaction, one failure in 3,598) and the line held three verified slices for the hour a rerun takes: merges go on the Mac's full gate alone, whatever GitHub's last run says; every merge is pushed, waiting only while a run is in progress; a red run is rerun once without asking; only a test of ours failing twice stops merging and comes to the owner, with the job, the test and the commit; and a release still needs GitHub green on the commit released. It replaces items 2 to 4 of the 18 November ruling on GitHub failures and ADR-142 Amendment 9's sentence "while main is red, every merge is refused".

**A merge reads GitHub, never waits for it** (1a). `merge_slice.py merge` reads GitHub's latest completed run on main (`common.main_ci()`: `gh run list --branch main --status completed`) and records it in `merged.json` as `github_at_merge` (`state` green, red or unknown, `run`, `url`, `why`, `at`), saying it in one line after its result ("GitHub's last run on main: red (run N), not a gate; merging"). A record, never a decision: the Mac's full gate alone decides, and a run gh cannot read is no reason to hold a merge the gate passed. Every other refusal stands.

**Every merge is pushed** (1b), so GitHub always tests the newest main. `push_main.sh` defers only while a run on main is in progress or queued (a new push would cancel it), never for a completed red run, and writes the commit to `push.pending`. A deferred push is never forgotten: the board prints "push pending (<commit>)", and the conductor runs `merge_slice.py push-pending` when the run ends (a conductor command, like `merge` and `records`): under the merge lock, once nothing is in progress or queued, it runs `push_main.sh` with every rule it keeps (main's tip written by the merge script, the recorded origin, a fast-forward) and gives its words back. The guard still refuses `push_main.sh` to every agent.

**A test of ours red twice stops merging** (1c). `merge_slice.py watch-github` (the conductor's, after a run ends; `merge` runs it before it starts, and `push-pending` too) reads the latest completed run on main; when it is red, it reads the failing tests from `gh run view <run> --attempt <n> --log-failed` (pytest's `FAILED <path>::<test> - <why>` lines, after GitHub's job, step and timestamp) and records them in `records/github/<run>.json`. The same test failing in that attempt and in the one before it on the same commit (the run's previous attempt, or the previous run on that head) writes `github.stopped.json` (the test, the job, the commit, both runs); while it is there every merge is refused, naming them, and the conductor tells the owner. A first red, a red that passes on its rerun, a different test failing on the rerun, a job that failed with no `FAILED` line (a download, the network, a runner) and gh unreadable write no stop and hold no merge. The owner clears it with `OspreyFlow_Build/scripts/slice_line/clear_github_stop.py` (no arguments; refused when there is no stop): the file goes and a line is appended to `github-stop-clears.tsv` beside `owner-changes.tsv`, which `watch-github` reads, so the same pair of runs never stops merging again. The line never asks GitHub to rerun or cancel anything: the conductor reruns a red run once, by hand.

**A release still needs GitHub green on the commit released** (1d). `OspreyFlow_Build/scripts/slice_line/release_green.py check <commit>` passes only when the latest completed run of `ci` on exactly that commit concluded success (`gh run list --commit <sha> --status completed`; a red run that passed on its rerun counts); a green run on another commit, its parent included, does not; none, red, or gh unreadable refuses in words naming the commit. `OspreyFlow_Build/tools/release_local.py` calls it before it builds anything, and `OspreyFlow_Build/scripts/publish_user_repo_update.sh` before it exports the product, beside the owed live tests.

## Resuming a slice

`resume.py <ID> <action>` is the only way back to `building` for a stopped or refused slice. The conductor runs it,
whole and unchained (the guard refuses it to every other seat). Every action takes the merge lock, refuses a worktree
with uncommitted changes, brings main's `RULINGS.md` into the worktree as an untracked copy that git ignores
(`Claude outputs/slice-line/RULINGS.md`, named in the builder's and the verifier's prompts; never a commit on the
slice's branch), and, where the branch conflicts with main only in the records folder, merges main into it, taking
main's records, and sends the slice for a fresh check.

| Action | For | Authority |
| --- | --- | --- |
| `refreeze` | commits `slices.tsv`, changed in that slice's frozen columns only, and refreezes them (history kept) | a line in `resume.tsv` |
| `add-round` | a slice stopped at its rounds limit: round and limit each +1 | a line in `resume.tsv` |
| `clear-stop` | a slice stopped on red checks: `red_stop.json` and `red_stops` removed | a line in `resume.tsv` |
| `send-back` | a slice the merge gate refused: back to the builder with the gate's findings, its round advanced; for a conflict with main (kind `records` or `conflict`) no round is spent, at the rounds limit too, and the builder's one task is to merge main in, keeping both sides of an append-only change | none within the rounds limit, or for a conflict; past it, the owner's `add-round` line as well |
| `correct-command` | a slice stopped **only** by the conductor's own malformed command (ruling 3) | none: the limits are in the code |
| `accept` | a slice stopped at its rounds limit (or refused by the gate at it) whose tip has the Stop hook's green test record and a verifier's `findings` record for that same tip: writes `accepted-<tip>.json` (the owner's line, the date, every finding verbatim, split into faults in behaviour, gaps in a test and findings with no kind), phase `verified`, `accepted: true`; changes no finding and no verifier record. A last verdict of `pass` is refused (nothing to accept) | a line in `resume.tsv` |
| `accept`, standing | with no `resume.tsv` line for the slice: the owner's one standing line in `standing.tsv`, `accept-test-gaps from-round <N> <YYYY-MM-DD>` (N 3 or more: ruling 5, "from a slice's third round on"), accepts a slice at round N or later whose newest findings record is the verifier's for its exact tip, every finding in it a gap in a test (`kind: test_gap`; in a record written before the field, the text's prefix "GAP IN A TEST:"). One fault in behaviour, or one finding with no kind, and it is refused in words; the slice goes round again or stops as before. The record is marked `by: standing`, with the rule's text; `run_seat.py verifier` tries it after each record with findings, and the conductor may run `resume.py <ID> accept` for a slice already stopped. The merge reads the line again (gone or no longer met: refused); its record lists each gap (`accepted_findings.backlog_rows`) for the conductor's backlog row, and the board adds "(standing accept: N gaps in a test for the backlog)". The conductor tells the owner afterwards | none per slice: the owner's line in `standing.tsv` (no file, or anything else in it: off) |
| `undo-seat-failure` | a verifier call that was refused, written before seat failures existed as the finding "no verdict returned" that sent the slice round again (CO2, 19 November 2026), when every pass of that record is that line and the session's own stream shows its call refused: the record becomes a `seat_failure` record, the round goes back by one, the phase to `verifying` | a line in `resume.tsv` |
| `self-clear` | the line clears a stop itself (LINE_FIXES_5_BRIEF.md, A; below) | none: the code holds the limits; `run_seat.py` tries it after every red stop |
| `move-seat <builder\|verifier> <account>` | a started slice's seat moved to another account (one `accounts.yaml` names, signed in and not stopped), while none of its seats runs and no merge runs: `state.json`'s `account` or `verifier_account` rewritten, and nothing else (no record, finding or round). The builder and the verifier stay apart by session, not by account: the merge refuses a pass from a session that built the slice, on any account | a line in `resume.tsv`: `<ID> move-seat <seat> <account> <YYYY-MM-DD>` |

**The line clears a stop itself** (`resume.py <ID> self-clear`; the owner, 21 November 2026, "fewer stops for my lines") when its cause is one of two, each tested so it cannot be stretched. (b) The red stop is the checks alone and its failing tests are ones the slice did not write (not its acceptance files, not changed by its branch, not the acceptance's), all run by one pytest step that, run on main's own tree made as a builder's worktree is made (the rulings copy, the hashed client names, the Stop hook's environment), fails on exactly the same tests and is green with them deselected: the line adds `--deselect <id>` for each to that step, commits the row in records mode, refreezes (history kept, `refrozen_by` naming it) and clears the stop. (a) Main has moved under the slice: it has commits the branch lacks, merges in cleanly and changes none of the slice's acceptance files: the line merges it in and clears the stop, once per move of main. Neither spends a round. **Never the line's, whatever the cause**: any stop at round 8 or later; a stop whose failure lines or findings name a key, a credential or a security rule (matched anywhere in a word, any case: a word too many leaves the stop with the owner; the command the red stop echoes is not read); a stop on a verifier's findings (a fault in behaviour is never cleared, and accepting open findings is the owner's, or his standing line's); a slice whose frozen commands differ from main's row or whose refreeze line waits in `resume.tsv`; the acceptance's own test. Each clearance is a record in the slice's folder (`self-clear-<time>.json`) and a row of `self-clears.tsv` in the data folder (the time, the slice, the stop, the cause, what the line did), which the board prints ("cleared by the line: ..."; `board.py --self-clears` for the morning report) and `status.js` carries (`self_clears`). `clear-stop` still needs the owner's line.

`resume.tsv` (`OspreyFlow_Build/process/lanes/v062/resume.tsv`) is the owner's: one line `<ID> <action> <YYYY-MM-DD>`
(today, UTC), one use per line, each use logged in `owner-changes.tsv` in the data folder (time, slice, action,
detail). `RULINGS.md` is never the authority: the conductor writes it. `standing.tsv` (beside it, never committed) is the owner's
standing line for the accept; without it the standing accept is off.

`correct-command`'s limits (`resume.py`, `dry_run.py`): the slice's last red output matches a malformed-command
signature (`make: *** <dir>: No such file or directory`; `OSPREY_PORTS_SLOT is not set`) and nothing a failing test
prints; the corrected acceptance and checks name exactly the same test files and add nothing that changes what is
tested (`||`, `-k`, `--ignore`, ...); the corrected commands are proved on main in a scratch worktree first (checks
green to the last step of their `&&` chain, the slice's own new files stood in by placeholders; acceptance red for a
reason no signature matches); the use is logged, and the board prints "command corrected: old -> new" for the
conductor's next report.

## The live step

The full gate's last part runs the live test files the slice's change itself reaches
(`OspreyFlow_Build/tools/live_select.py --reached`) on the test server through `stack_lease.sh`. `--reached` leaves out
the lanes' floor, which selects `test_route_rights.py` for every change: on 17 November 2026 the dry run's slice, two
files under `process/` (which `OspreyFlow_Build/tools/live_map.tsv` maps to `none`), took test stack b on the server
for that file alone. A change that reaches no live file now takes no stack and reads no queue; a file the change does
reach, `test_route_rights.py` included, is still run.

The owner's `OspreyFlow_Build/process/lanes/v062/live_step.yaml` turns the step on or off; it is off from
18 November 2026, until the demo's images no longer share tags with test builds. Off, nothing reaches the server: a
change that reaches live files merges on the offline gates, and the merge log and `merged.json` (`live_step`) name
each live file not run. **Each is owed** (`OspreyFlow_Build/scripts/slice_line/owed.py`) until a live run that
passed has run it since: the board prints what is owed and `status.js` carries it (`owed_live_tests`), and a release
is refused while anything is owed or the records cannot be read (`owed.py check`; and unless GitHub is green on the commit released, `release_green.py check`: both called by
`OspreyFlow_Build/tools/release_local.py` and `OspreyFlow_Build/scripts/publish_user_repo_update.sh`). With the step
on, each merge's live run also runs every owed file and, green, records them paid (`live-paid.json`). On, the step first reads the server's run queue (`osprey-runs/QUEUE` and `pgrep -x make` on
each host in `scripts/lane_stack_hosts.tsv`): it goes when the queue is empty or has `merger` first and no make runs,
waits a minute at a time for `queue_wait_minutes`, then refuses the merge. A queue that cannot be read is never taken
as clear. A missing or unclear setting refuses the merge.

## The client names' hashed list

`OspreyFlow_Build/marketing_site/client_names.local.sha256` is gitignored and kept on this Mac only. The full gate
copies it from the main checkout into the merge tree before `make -k ci`, after the merge commit is made and only
where the tree's own ignore rules keep it out of git, so the sites' checks and BL6's client-name check run in the
gate; a merge is refused when it is missing or empty there. GitHub's runners have no copy: there the check says in
words that it did not run. `slice_start.py` copies it the same way into a new slice's worktree (only where git ignores
it there; never committed), so the builder's checks see it, and says in words when the main checkout has none.

## Records mode

`merge_slice.py records -m "<msg>" <paths>` commits only `OspreyFlow_Build/process/lanes/v062/`, never
`dial.yaml`, `accounts.yaml`, `live_step.yaml`, `resume.tsv` or `standing.tsv`, and refuses a backlog change to a started slice's frozen commands.

## The dial and the accounts

`dial.yaml` (Thrift 1 builder / Balanced 2 / Sprint 4; rounds 1/2/2; seat models) and `accounts.yaml` (names
only) are the owner's. Neither is read by any gate. A started slice keeps its setting and accounts (a seat moves only on the owner's `resume.py <ID> move-seat` line). The scouts'
model follows the dial through the Agent call's `model`; their effort stays at the definition's (an Agent call
cannot set effort).

## Accounts and usage

Every seat session's stream reports its account's rate-limit windows; `run_seat.py` records them in
`~/.ospreyflow/slice-line/accounts/<account>.json`. At 90% of a window, no new slice starts on that account; the
running slice finishes. A refused session (rate limit, signed out) stops its track (`StopFailure` hook). **A seat failure** (a call refused: `is_error`, an `api_error_status` of 401, 403, 408, 429 or 5xx, no result line, or a verifier with no verdict and no turns) is never a verdict, a finding, a round or a red stop: `run_seat.py` tries the seat three times, the pause growing, each refused try a `seat-failure-*.json` record that nothing reading a verdict reads; then, or as soon as the account is stopped, the slice stays in its phase with the failure and the account in its state, the account is stopped, the board shows "seat failed on <account>", and the run prints the error's own words for the owner. **The owner clears a stopped account** with `clear_account.py <account>` on a `resume.tsv` line `clear-account <account> <YYYY-MM-DD>`: one cheap probe call on that account, and the stop is removed only if the call is accepted; logged in `owner-changes.tsv`; the guard refuses the script to every agent, as it does `refreeze.py`. Work is never moved to the other account by the line: the owner edits `accounts.yaml` for new slices, and moves a started slice's seat with `resume.py <ID> move-seat` on a `resume.tsv` line. Usage per slice, seat and account is in
`usage.tsv` (`board.py --usage`); the conductor's own (with its scouts') is one row per session: its SessionEnd hook
writes it, and `run_seat.py conductor` writes it after the session when the hook did not (never twice).
`board.py --usage` prints totals per slice and per account, each account's five-hour and seven-day windows beside
it (or "not reported" where its sessions' stream never gave one: the default account's gives only seven-day), and
says that cost is a list-price estimate, not a bill.

## The line fixes of 21 November 2026 (LINE_FIXES_5_BRIEF.md)
- **The owner's approved diffs** (10): `merge_slice.py approve-diff <name> <hash8>` records the owner's "approved: <name> <hash8>" (refused unless hash8 is the diff file's SHA-256 now) in `approved/<name>.json`, committed; `merge_slice.py apply-approved <name>` applies `slice-line/proposals/<name>.diff` only while its SHA-256 is the approved one, it touches only spec/06_DECISIONS.md, spec/ADR_RESERVATIONS.md, both DESIGN.md and process/CLAUDE.md (no rename or mode change), it applies to main's tip and the decision checks are green on the result; it commits with "approved by the owner, <date>", `Slice-Records: yes` and `Owner-Approved-Diff: <name>`, lists name, hash8, commit and date in `approved/applied.tsv` (the board prints it for the top of each report) and pushes (`push_main.sh` accepts the new trailer). The guard refuses the conductor's own `git apply`, `git am` and `patch` (but `--check`, `--stat`, `--numstat`, `--summary`).

## Files outside the repository

`~/.ospreyflow/slice-line/`: `bin/` (the hooks), `node/v<major>/` (CI's Node, found before PATH's: the gate refuses another major; Node 22.23.5 for darwin-arm64 is installed at `node/v22/`, from nodejs.org's tarball, its SHA-256 matching `SHASUMS256.txt`), `settings.json`, `manifest.json`, `origin.url`,
`emails.sha256`, `records/<ID>/` (frozen, state, sessions, tests-, verify-, accepted-, merged, logs), `accounts/`,
`sessions/` (guard markers), `usage.tsv`, `push.log`, `push.pending`, `merge.lock`, `records/github/` (each red run's failing tests), `github.stopped.json`, `github-stop-clears.tsv` (the owner's clears), `self-clears.tsv` (the stops the line cleared itself). The dashboard's
`status.js` is in the git-ignored `Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/`.
