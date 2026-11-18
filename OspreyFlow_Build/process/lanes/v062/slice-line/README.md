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

**A seat refuses to start unless the guard is loaded** (`run_seat.py`): the installed files must match the
manifest; the fixed settings must register them; no settings file the session reads may set `disableAllHooks`;
the account must be signed in and not stopped; and the session's own SessionStart hook must answer with the
launch's one-time token before the prompt is sent (the prompt goes over stream-json input only after that).

## Gates and their proofs

`OspreyFlow_Build/scripts/slice_line/tests/run.sh` (77 cases) plants each violation in the shape its real call
site produces; `OspreyFlow_Build/scripts/slice_line/tests/plant_faults.py` shows each test red with its gate disabled (68 planted faults, 0 missed). `make ci` runs the suite (`slice-line-check`), and so does its own CI job.

| Gate | Where | What refuses |
| --- | --- | --- |
| The owner's files | guard | Edit/Write of `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`; shell writes naming them; `dial.yaml`, `accounts.yaml`, `live_step.yaml`, `resume.tsv` |
| Never staged | guard | `git add`/`commit -a` that would take `OspreyFlow_Core/osprey.yaml` or `OspreyFlow_Core/data/` |
| No push, remote or repository | guard, push_main.sh | every `git push`, remote change, `gh repo create/edit`, write `gh api`; the push script refuses all but a merge-written main to the recorded origin, fast-forward only |
| A builder in its worktree | guard | edits, `cd`, `-C`, `GIT_DIR`, writes naming another checkout; branch switches |
| Only the merge script writes main | guard, merge_slice.py | commit/merge/reset/rebase/pull on main; `update-ref`, `branch -f`, `fetch .:main`, `checkout -B main` |
| No credential or address | guard (tool calls), Stop hook (final text) | key patterns; the owner's addresses by SHA-256 (`emails.sha256`) |
| GOV.UK demo, airbyte | guard | `govuk.ospreyflow.app`, `/opt/ospreyflow*`, `osprey-small`, `:8000`, airbyte/abctl; any hand change on the test server |
| The line itself | guard, merge_slice.py | `.claude/`, `scripts/slice_line/`, the records, the status file, `OSPREY_*` overrides, nested `claude` |
| Cannot stop on red | stop_check.py | the frozen checks and acceptance run at Stop; red (or uncommitted) sends back the failure lines only; after 6, stopped |
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
2. `slice_start.py <ID>`: first a **dry run** of the slice's commands on main in a scratch worktree (`dry_run.py`):
   the checks, with the slice's own new files stood in by placeholders, must exit 0 and reach the last step of their
   `&&` chain (a red run names the step it did not reach); the acceptance must be red for a reason no
   malformed-command signature matches. Otherwise nothing is created. Then worktree `~/dev/osprey-wt/slice-<ID>` on
   `lane/slice-<ID>`; the acceptance and checks commands **frozen** (a change needs the owner's word: `resume.py`
   refreeze, or the conductor's own `correct-command`); account, track, dial setting, rounds fixed.
3. `run_seat.py builder <ID>` until green, then `run_seat.py verifier <ID>`. Findings go back to the builder until
   the rounds limit; then the slice stops and its note names the one decision the owner must make.
4. `merge_slice.py merge <ID>`: main fast-forwarded to the tested merge commit, then `push_main.sh`. A red full gate
   (or a merge refused for a conflict in the records folder alone) leaves the slice `refused`: the failing tests and
   their failing lines (not the whole log) are written as a findings record (`verify-gate-<tip>.json`), the board
   shows "refused by the gate: N tests", and `resume.py <ID> send-back` returns it to the builder with those findings.
5. `board.py` prints the board and writes `status.js` after every merge, verifier record and stop.

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
| `send-back` | a slice the merge gate refused: back to the builder with the gate's findings, its round advanced | none within the rounds limit; past it, the owner's `add-round` line as well |
| `correct-command` | a slice stopped **only** by the conductor's own malformed command (ruling 3) | none: the limits are in the code |

`resume.tsv` (`OspreyFlow_Build/process/lanes/v062/resume.tsv`) is the owner's: one line `<ID> <action> <YYYY-MM-DD>`
(today, UTC), one use per line, each use logged in `owner-changes.tsv` in the data folder (time, slice, action,
detail). `RULINGS.md` is never the authority: the conductor writes it.

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
is refused while anything is owed or the records cannot be read (`owed.py check`, called by
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
words that it did not run.

## Records mode

`merge_slice.py records -m "<msg>" <paths>` commits only `OspreyFlow_Build/process/lanes/v062/`, never
`dial.yaml`, `accounts.yaml` or `live_step.yaml`, and refuses a backlog change to a started slice's frozen commands.

## The dial and the accounts

`dial.yaml` (Thrift 1 builder / Balanced 2 / Sprint 4; rounds 1/2/2; seat models) and `accounts.yaml` (names
only) are the owner's. Neither is read by any gate. A started slice keeps its setting and accounts. The scouts'
model follows the dial through the Agent call's `model`; their effort stays at the definition's (an Agent call
cannot set effort).

## Accounts and usage

Every seat session's stream reports its account's rate-limit windows; `run_seat.py` records them in
`~/.ospreyflow/slice-line/accounts/<account>.json`. At 90% of a window, no new slice starts on that account; the
running slice finishes. A refused session (rate limit, signed out) stops its track (`StopFailure` hook). Work is
never moved to the other account: the owner edits `accounts.yaml`. Usage per slice, seat and account is in
`usage.tsv` (`board.py --usage`); the conductor's own (with its scouts') is one row per session (SessionEnd).

## Files outside the repository

`~/.ospreyflow/slice-line/`: `bin/` (the hooks), `node/v<major>/` (CI's Node, found before PATH's: the gate refuses another major; Node 22.23.5 for darwin-arm64 is installed at `node/v22/`, from nodejs.org's tarball, its SHA-256 matching `SHASUMS256.txt`), `settings.json`, `manifest.json`, `origin.url`,
`emails.sha256`, `records/<ID>/` (frozen, state, sessions, tests-, verify-, merged, logs), `accounts/`,
`sessions/` (guard markers), `usage.tsv`, `push.log`, `push.pending`, `merge.lock`. The dashboard's
`status.js` is in the git-ignored `Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/`.
