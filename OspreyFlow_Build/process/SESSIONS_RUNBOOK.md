# Running the orchestrator and three lanes

6 November 2026 · for the owner · how the sessions ADR-142 describes are started. **You start two
things: the orchestrator and the heartbeat monitor.** The orchestrator does the rest itself (ADR-142
decision 10): it makes the worktrees and their environments, writes the briefs, and opens each lane
in its own Terminal window with Claude Code already started on its prompt. §2–§4 are what it runs, kept
here so you can see it and do any step by hand if you ever need to. Commands are for your Mac's
Terminal; paths assume the repository stays where it is:

```
REPO="$HOME/Documents/MyProjects/IntelAnalysis_and_NetworkDiscovery_Platform/ospreyflow"
WT="$HOME/dev/osprey-wt"
```

Put those two lines at the top of each Terminal tab you open (or in `~/.zshrc`). You start Claude
Code as `CLAUDE_CONFIG_DIR=~/.claude-ayan claude` (on 6 November 2026 no `claude-ayan` alias was
defined; `~/.zshrc` holds `claude-izi` and `claude-sol` only). The launcher starts each lane the same
way the orchestrator's own session runs: `claude` by its full path, under the orchestrator's
`CLAUDE_CONFIG_DIR` (`OSPREY_CLAUDE_CMD` and `OSPREY_CLAUDE_CONFIG_DIR` change them).

## 0. Before anything: let phase 4 finish

1. Let the phase 4 session write its final report. Then close it (`/exit`), and check nothing of it is
   still running:
   ```
   pgrep -alf '(^|/)claude(-ayan)?( |$)'
   cd "$REPO/OspreyFlow_Core" && docker compose -f deploy/compose/dev.yaml ps
   cd "$REPO" && git status --short
   ```
   Expect no `claude` process (macOS `pgrep` leaves out its own ancestors unless given `-a`; the
   Claude desktop app's helper processes are not sessions), no dev-stack containers listed, and only `OspreyFlow_Core/osprey.yaml`
   modified. (Your own deployment and the airbyte container are separate and stay running.)
2. If phase 4's report left anything undone, that becomes Lane 1's first step (L1.1), not a fifth
   session.

## 1. What you do: start the orchestrator, then the monitor

The orchestrator lives in your original checkout, on `main`.

```
cd "$REPO"
CLAUDE_CONFIG_DIR=~/.claude-ayan claude --model opus
```

Choose Opus at medium effort (`/model`). The package is already in
`"$REPO/OspreyFlow_Build/Claude outputs/ospreyflow_parallel_build_2026-11-06/"` (gitignored); if not,
unzip it there. Then paste **Prompt O0**
(§7). It works alone; no lane exists yet. It will ask you to confirm the "confirm at step 0" items as
multiple choice, then commit the records and the tooling, push, write the briefs, make the worktrees
and open three Terminal windows — studio, glass and case — each with Claude Code running its lane. In
each new tab, answer any approval Claude Code asks for and, if you want other than Opus, set the model
and effort with `/model`. Then start the monitor in a tab of its own (§5).

## 2. Make the three worktrees (the orchestrator runs this: `lanes_launch.sh setup <lane>`)

By hand, the equivalent is:

```
mkdir -p "$WT"
cd "$REPO"
git worktree add "$WT/studio" -b lane/studio main
git worktree add "$WT/glass"  -b lane/glass  main
git worktree add "$WT/case"   -b lane/case   main
git worktree list
```

Then, for **each** of `studio`, `glass`, `case`:

```
L=studio        # then glass, then case
cd "$WT/$L"
cp "$REPO/.claude/settings.local.json" .claude/ 2>/dev/null || true      # your personal permissions
cp "$REPO/OspreyFlow_Core/osprey.yaml" OspreyFlow_Core/osprey.yaml        # your local copy
git update-index --skip-worktree OspreyFlow_Core/osprey.yaml             # so it can never be staged
(cd OspreyFlow_Core && uv sync --frozen && npm ci)                        # its own .venv and node_modules
graphify update .                                                         # its own graph for the hook guard
```

`uv sync --frozen` builds `.venv` from `uv.lock`, as your original was built (uv 0.5.14). Add
`--extra extraction` only in a lane that runs the extraction tests. The worktrees sit outside
`~/Documents` on purpose, so iCloud does not sync their `.venv` and `node_modules`.

## 3. Open the lanes (the orchestrator runs this: `lanes_launch.sh open <lane>`)

It opens a Terminal window per lane (AppleScript's `do script` opens a window, not a tab), in its worktree, with Claude Code started on Prompt L and the lane's
brief, and refuses if a session is already running there. The documentation lane opens the same way, interactive (the owner's
step 0 answer to P7), after the first feature lane merges. By hand, the equivalent is one tab per lane:

```
cd "$WT/studio" && CLAUDE_CONFIG_DIR=~/.claude-ayan claude --model opus    # Lane 1 · Opus, medium
cd "$WT/glass"  && CLAUDE_CONFIG_DIR=~/.claude-ayan claude --model opus    # Lane 2 · Opus, medium (Sonnet for its mechanical steps)
cd "$WT/case"   && CLAUDE_CONFIG_DIR=~/.claude-ayan claude --model opus    # Lane 3 · Opus, medium
```

In each, paste **Prompt L** (§7) with its lane's name and its first brief (the orchestrator writes the
briefs into `process/lanes/<lane>/BRIEF.md` on `main` at step 0; each worktree sees them once it is
rebased, or you paste the brief's text directly).

Keep the orchestrator's tab open. That makes four tabs: orchestrator, studio, glass, case, and a
fifth for the heartbeat monitor (§5).

## 4. The dev stack: one at a time

**The leased stack is the throwaway test stack** (the orchestrator's judgement of 7 November 2026, under
the owner's delegation; it supersedes the ruling to move dev-up's ports). `make dev-up` publishes ArcadeDB on
2480, which the owner's deployment holds, and the demo guide and several scripts (`seed_paysim`,
`repro_paysim_duplicates`, the hand-run Conduit, the reset's `drop database`) reach `localhost:2480`
whenever no port is set. Moving dev-up would point each of those at the deployment instead. So the
lanes run live tests on the throwaway stack in `FDE_HANDOVER.md` (`osprey-probe-arcadedb-new` 2491,
`osprey-test-pg` 55433, `osprey-test-valkey-6379` 6379, `osprey-test-minio`), whose ports nothing uses by
default, under the same lease. `stack_lease.sh release` refuses while either stack is up. The commands
below that name `make dev-up` stand for bringing that stack up and down.

There is one stack for the machine. A lane that needs Postgres, ArcadeDB or Valkey:

```
OspreyFlow_Build/scripts/stack_lease.sh status
OspreyFlow_Build/scripts/stack_lease.sh acquire studio "phase 6 route tests"
(cd OspreyFlow_Core && make dev-up)
# … run the live tests, with the ports pinned as today (tests/port_guard.py) …
(cd OspreyFlow_Core && make dev-down)
OspreyFlow_Build/scripts/stack_lease.sh release studio
```

`acquire` refuses while another lane holds the lease and says who, for what and since when. `release`
refuses while the stack is still up. Your own deployment on 8080 and 2480 stays untouched: the port guard
already refuses those ports in tests.

## 5. Staying on top: the heartbeat monitor

Open a fifth Terminal tab and leave it running:

```
cd "$REPO" && OspreyFlow_Build/scripts/lanes_heartbeat.sh watch 300
```

Every five minutes it redraws one table — each lane's state (planning, working, testing,
waiting-for-owner, blocked, ready-to-merge, idle), how long since it last reported, how far its branch
is ahead of and behind `main`, its last commit and what it says it is doing — plus who holds the dev
stack and for how long. Under **NEEDS YOU** it lists, and sends a Mac notification for, anything new
that wants you: a lane waiting for your answer or blocked; a lane ready to merge; a lane silent for 45
minutes while it should be working; a lane far behind `main`; the stack leased for over two hours.

For a one-off look: `OspreyFlow_Build/scripts/lanes_heartbeat.sh show`. The limits can be changed with
`OSPREY_QUIET_MINUTES` and `OSPREY_LEASE_MAX_MINUTES`. A heartbeat is the lane's own claim; the
orchestrator still reads the branch before believing it.

## 6. The daily loop (the orchestrator runs it; you answer questions)

1. **A lane works its brief**, commits on its own branch, never merges and never pushes, and ends with
   the report the prompt asks for (also saved to `process/lanes/<lane>/REPORT.md`).
2. **Questions** come back as multiple choice. Answer them in the lane's tab, or tell the orchestrator,
   which can batch all three lanes' questions into one round for you.
3. **When a lane is ready to merge** (its heartbeat says so; or tell the orchestrator), the
   orchestrator, without waiting for you:
   - reads the branch (`git log main..lane/studio`, `git diff main...lane/studio`), not the report;
   - has the `lane-reviewer` agent read it against the brief and rules 1–15;
   - nudges the lane to rebase (`git rebase main`) and re-run its touched tests;
   - takes the lease, merges, runs `make ci`, assembles the friction log, pushes and logs the push;
   - nudges the other lanes to rebase, and writes the merged lane its next brief;
   - tells you what to check by hand.
   A lane that is quiet or stuck is nudged; one whose session has ended is reopened on Prompt R.
   The orchestrator acts only while it is running a turn. Prompt O ends by putting it in **watch
   mode**: it checks the heartbeat every ten minutes and acts, until you interrupt it (Esc) to talk to
   it, or until eight hours pass with nothing changing. Without watch mode, say "check in" when you
   want it to look.
4. **Before you close a tab**, ask that session whether anything of it is still running (background
   shells, subagents). "Handed back a report" is not "stopped" (rule 14).

When a lane's work is done: `git worktree remove "$WT/<lane>"` and `git branch -d lane/<lane>`.

## 7. Paste-ready prompts

### Prompt O0 · orchestrator, step 0

```
You are the orchestrator for OspreyFlow's parallel build. Read OspreyFlow_Build/process/CLAUDE.md
(rules 1–15 bind; rule 14 is about to change) and OspreyFlow_Build/process/FDE_HANDOVER.md §1 (how the
owner works: explain before you fix, multiple-choice questions only, at most four at a time, never edit
an ADR, British English, no Co-Authored-By or Claude-Session lines).

Read, from "OspreyFlow_Build/Claude outputs/ospreyflow_parallel_build_2026-11-06/":
1. adr/ADR-142_parallel_lanes.md, ADR-143_case_dataset_contract_and_drawing_boards.md,
   ADR-144_case_views.md, ADR-145_three_places_admin_roles.md
2. process/BUILD_PLAN_PARALLEL_LANES.md ("Step 0" in full) and process/SESSIONS_RUNBOOK.md
3. In OspreyFlow_Build/spec/06_DECISIONS.md: the last ADR (to confirm 142 is free), and the last
   amendment of ADR-084, ADR-090, ADR-099, ADR-105, ADR-110, ADR-112, ADR-132, ADR-133 and ADR-140, to number
   the amendments marked <reserved>.

First confirm, with pgrep -alf '(^|/)claude(-ayan)?( |$)' (the Claude desktop app's own helper processes are not
sessions), docker compose -f OspreyFlow_Core/deploy/compose/dev.yaml ps and git status, that no other
agent or stack is active.
Then ask me, as multiple choice, every item the four ADRs mark "the owner confirms at step 0", and wait.
If anything in the records contradicts a standing rule or an earlier ruling they do not name as
changed, ask me before writing; do not implement an alternative.

Then do exactly Step 0 of the build plan, the gates each shown red before you rely on them. Ask me
for the Makefile and ci.yml lines as a diff for me to apply; do not edit those two files. Commit in
small Conventional Commits naming each file. Push as ADR-142 decision 6 says (origin only, after make
ci passes on the commit, logged in process/lanes/PUSH_LOG.md with git rev-parse HEAD and
git ls-remote origin refs/heads/main matching). Then write each lane's first brief into
process/lanes/<lane>/BRIEF.md (Lane 1: L1.1 or L1.2; Lane 2: L2.1; Lane 3: L3.1), commit and push
them; save Prompt L and Prompt R as process/lanes/PROMPT_L.md and PROMPT_R.md; then run
OspreyFlow_Build/scripts/lanes_launch.sh setup and open for studio, glass and case (ADR-142 decision 10)
and tell me which tabs opened and the heartbeat monitor's command (runbook §5).

Copy the drafts in the package's scripts/ (stack_lease.sh, lanes_heartbeat.sh, lanes_launch.sh) into
OspreyFlow_Build/scripts/ as the starting point for their step 0 gates.

Report: the ADR and amendment numbers used, the files changed, the push log line, and any question
left open. Then carry on as Prompt O in the runbook says from "Under ADR-142's P10", ending in its
watch mode.
```

### Prompt O · orchestrator, any later session

```
You are the orchestrator for OspreyFlow's parallel build (spec/06_DECISIONS.md ADR-142). Read
OspreyFlow_Build/process/CLAUDE.md (rules 1–15, rule 14 as ADR-142 reworded it),
OspreyFlow_Build/process/BUILD_PLAN_PARALLEL_LANES.md, process/lanes/*/BRIEF.md and REPORT.md, and
process/lanes/PUSH_LOG.md. You write no product code.

Check the state for yourself: OspreyFlow_Build/scripts/lanes_heartbeat.sh show; git worktree list;
for each lane git log --oneline main..lane/<lane>; OspreyFlow_Build/scripts/stack_lease.sh status;
pgrep -alf '(^|/)claude(-ayan)?( |$)'. Tell me in a short table where each lane is against
its brief (the code is the evidence, not the report), what waits for my decision (as multiple choice,
batched across lanes, at most four), and what is ready to merge.

Under ADR-142's P10 you may, without asking me: set up worktrees and environments; merge, run make ci
and push under decision 6; write and send a lane its next brief after a merge; nudge a quiet or stuck
lane (lanes_heartbeat.sh nudge) and reopen a lane whose session ended (lanes_launch.sh resume). Ask me
for design rulings, any other download, the protected Makefile and ci.yml lines, and before closing a
session I opened.

When a lane is ready to merge (its heartbeat, or my word): have the lane-reviewer agent read its branch against the brief and rules
1–15; tell me what the lane must fix, or ask me to have it rebase on main; then take the lease, merge
with --no-ff in the order the build plan sets, run make ci (and Floor B if a live-store path was
touched), run OspreyFlow_Build/tools/friction_assemble.py, commit, push as ADR-142 decision 6 says, log the push, release
the lease, and give me the rebase line for the other lanes and the one thing to check by hand (full
commands and where to click, in the default and GOV.UK themes). Then write that lane's next brief and
nudge the lane to read it.

Then go into watch mode: every ten minutes run OspreyFlow_Build/scripts/lanes_heartbeat.sh show and
lanes_launch.sh alive for each lane, and act on what it shows under the rules above (merge a lane that
is ready, nudge a quiet one, reopen an ended one, batch questions for me). Say in one line what you did
each time you act; say nothing when nothing changed. Never start a server or a wait that cannot end
(the September queue's rule). Stop watching when I interrupt you, or after eight hours with no change.
```

### Prompt L · a lane (replace `<lane>`: studio, glass or case)

```
You are the <lane> lane of OspreyFlow's parallel build, working in this worktree on branch
lane/<lane> (spec/06_DECISIONS.md ADR-142). Read OspreyFlow_Build/process/CLAUDE.md (rules 1–15; rule
14 as ADR-142 reworded it), OspreyFlow_Build/process/FDE_HANDOVER.md §1, and
OspreyFlow_Build/process/BUILD_PLAN_PARALLEL_LANES.md (your lane's table and the file ownership map).

Your brief is process/lanes/<lane>/BRIEF.md (or the text I paste below). Read the ADRs and spec
sections it names. Change only the files your lane owns; anything else is a request to the orchestrator,
in your report. Do only the brief's step; do not start the next.

Before changing code, write me a short plan: the files you will touch, the tests you will write first
(rules 1, 4, 12, 13), and any question as multiple choice (at most four, recommendation first). Wait if
you asked one; otherwise proceed.

The dev stack is shared: take OspreyFlow_Build/scripts/stack_lease.sh acquire <lane> "<purpose>"
before make dev-up, make dev-down before release, and name the lease in any timing or reliability
figure you record. Send a heartbeat with
OspreyFlow_Build/scripts/lanes_heartbeat.sh beat <lane> <state> "<what you are doing>" when you start
planning, start work, start tests, ask me something (waiting-for-owner), are blocked, are ready to merge
(ready-to-merge), finish (idle), and after every commit. If a beat shows a message from the
orchestrator, act on it before going on. Build every screen for the dark, light and GOV.UK themes and run the axe scans for
all three. Write your friction-log row as process/friction/<yyyy-mm-dd>-<lane>-<slug>.md, one row,
ending "Hash: recorded at merge." Commit in small Conventional Commits naming the files; never stage
OspreyFlow_Core/osprey.yaml or OspreyFlow_Core/data/; never merge to main; never push; no
Co-Authored-By lines.

End with a report of at most twenty lines, also saved to process/lanes/<lane>/REPORT.md: each exit
criterion and whether it is met, with the test that proves it; what is left and why; the commits;
requests to the orchestrator; questions for me; and whether anything of yours is still running.
```

### Prompt R · resume a lane after its session ran out

```
You are the <lane> lane (ADR-142), resuming. Read process/CLAUDE.md, FDE_HANDOVER.md §1, the build
plan's lane table and process/lanes/<lane>/BRIEF.md. A previous session started this brief and stopped.
Reconcile what the branch holds against the brief: git log --oneline main..lane/<lane>, git status, and
the brief's tests. Tell me in a short table what is done (with the proving test), half-done, and
untouched; the code is the evidence, not the earlier report. Then finish the brief under Prompt L's
rules and end with the same report.
```

## 8. When something goes wrong

- **Two lanes need the stack at once:** the second waits. If waiting blocks real work, tell the
  orchestrator; it can reorder merges, never share the lease.
- **A lane touched a file it does not own:** the orchestrator moves the change to the owner's lane or
  makes it a small shared commit merged first; the lane drops it on rebase.
- **A rebase conflicts in `06_DECISIONS.md` or the friction log:** the reservation or fragment rule was
  skipped; the orchestrator resolves it and records a friction row saying which.
- **`make ci` is red on a merge:** nothing is pushed; after two failed attempts it becomes a question to
  you (ADR-142 decision 6).
- **A lane wants to change a ruling:** it stops that piece and asks you, as multiple choice.
