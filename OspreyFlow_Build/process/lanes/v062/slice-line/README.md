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

`OspreyFlow_Build/scripts/slice_line/tests/run.sh` (48 cases) plants each violation in the shape its real call
site produces; `tests/plant_faults.py` shows each test red with its gate disabled (37 planted faults, 0 missed).

| Gate | Where | What refuses |
| --- | --- | --- |
| The owner's files | guard | Edit/Write of `OspreyFlow_Core/Makefile`, `.github/workflows/ci.yml`; shell writes naming them; `dial.yaml`, `accounts.yaml` |
| Never staged | guard | `git add`/`commit -a` that would take `OspreyFlow_Core/osprey.yaml` or `OspreyFlow_Core/data/` |
| No push, remote or repository | guard, push_main.sh | every `git push`, remote change, `gh repo create/edit`, write `gh api`; the push script refuses all but a merge-written main to the recorded origin, fast-forward only |
| A builder in its worktree | guard | edits, `cd`, `-C`, `GIT_DIR`, writes naming another checkout; branch switches |
| Only the merge script writes main | guard, merge_slice.py | commit/merge/reset/rebase/pull on main; `update-ref`, `branch -f`, `fetch .:main`, `checkout -B main` |
| No credential or address | guard (tool calls), Stop hook (final text) | key patterns; the owner's addresses by SHA-256 (`emails.sha256`) |
| GOV.UK demo, airbyte | guard | `govuk.ospreyflow.app`, `/opt/ospreyflow*`, `osprey-small`, `:8000`, airbyte/abctl; any hand change on the test server |
| The line itself | guard, merge_slice.py | `.claude/`, `scripts/slice_line/`, the records, the status file, `OSPREY_*` overrides, nested `claude` |
| Cannot stop on red | stop_check.py | the frozen checks and acceptance run at Stop; red (or uncommitted) sends back the failure lines only; after 6, stopped |
| Merge | merge_slice.py | see the script's docstring: lock, frozen match, verifier pass for the tip, protected paths, red before, green after, **today's full gate**: `make -k ci` and `make test`, both run and both reported, in the merge tree's own environment built as CI's `test` job builds it (`uv sync --frozen`, `npm ci` under the Node major `ci.yml` names, no `VIRTUAL_ENV` or other `.venv/bin`, closed ports, the merger's slot), never the main checkout's; then the live files reached, through the lease |
| Status file | board.py | `done` only with a merge record, its test run and a verifier pass; unknown build ids reported, not written |

**What a hook cannot do** (documented, not worked around): no hook can stop text the model has already shown (the
Stop hook catches a key or address in a final message and forces a correction, after the fact); shell commands
are judged by their text, so a command that computes a path can slip past the guard; the merge script's diff
check is the backstop that does not depend on the text. Claude Code caps a Stop hook at 8 consecutive blocks
without a tool call; the line's own cap is 6 red stops.

## A slice's life

1. The conductor writes `slices/<ID>.md` from `SLICE_BRIEF.template.md` and its row in `slices.tsv`, and commits
   them with `merge_slice.py records`. The build id must be one of the plan's (`dashboard/index.html`).
2. `slice_start.py <ID>`: worktree `~/dev/osprey-wt/slice-<ID>` on `lane/slice-<ID>`; the acceptance and checks
   commands **frozen** (only the owner's `refreeze.py` changes them); account, track, dial setting, rounds fixed.
3. `run_seat.py builder <ID>` until green, then `run_seat.py verifier <ID>`. Findings go back to the builder until
   the rounds limit; then the slice stops and its note names the one decision the owner must make.
4. `merge_slice.py merge <ID>`: main fast-forwarded to the tested merge commit, then `push_main.sh`.
5. `board.py` prints the board and writes `status.js` after every merge, verifier record and stop.

## Records mode

`merge_slice.py records -m "<msg>" <paths>` commits only `OspreyFlow_Build/process/lanes/v062/`, never
`dial.yaml` or `accounts.yaml`, and refuses a backlog change to a started slice's frozen commands.

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

`~/.ospreyflow/slice-line/`: `bin/` (the hooks), `node/v<major>/` (CI's Node, if PATH has none: the gate refuses another major), `settings.json`, `manifest.json`, `origin.url`,
`emails.sha256`, `records/<ID>/` (frozen, state, sessions, tests-, verify-, merged, logs), `accounts/`,
`sessions/` (guard markers), `usage.tsv`, `push.log`, `push.pending`, `merge.lock`. The dashboard's
`status.js` is in the git-ignored `Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/`.
