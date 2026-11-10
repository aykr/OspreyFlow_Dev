You are the <lane> lane of OspreyFlow's parallel build, working in this worktree on branch
lane/<lane> (spec/06_DECISIONS.md ADR-142). Read OspreyFlow_Build/process/CLAUDE.md (rules 1–15; rule
14 as ADR-142 reworded it), OspreyFlow_Build/process/FDE_HANDOVER.md §1, and
OspreyFlow_Build/process/BUILD_PLAN_PARALLEL_LANES.md (your lane's table and the file ownership map).

Your brief is process/lanes/<lane>/BRIEF.md (or the text I paste below). Read the ADRs and spec
sections it names. Change only the files your lane owns; anything else is a request to the orchestrator,
in your report. Do only the brief's step; do not start the next.

Before changing code, write a short plan: the files you will touch and the tests you will write first
(rules 1, 4, 12, 13). **Never stop on a question** (the owner, 8 November 2026): take your recommended
option, build it, and log it in REPORT.md under "Decisions taken" (the question, the options, what you
chose and why), so the owner can overrule it afterwards. Only three kinds of question stop the piece they
touch, and go to the orchestrator first: one that would loosen access control (rules 3 and 4), one that
would admit real data (rule 9), and one that would contradict an accepted ADR. Even then, carry on with
everything the question does not block.

**This Mac is the owner's** (the owner, 10 November 2026). Never open a desktop app on it (no `open -a`, no
`osascript … tell application`, no Keynote, PowerPoint, Preview or browser window) and never start Docker: a deck
agent opened Keynote on the owner's screen, and a local test started Docker Desktop, both on 10 November. Build and
check files headlessly. `make -k ci` and `make test` run on the test server through `stack_lease.sh offline
<lane>`; browser tests run there or in this Mac's two slots, each slot granted by the orchestrator.

A `packages/schemas` change rides with your step, in its own commit at the head of the branch, unless the
orchestrator has said another lane needs it first. Report ready-to-merge once, at the end of the step.

The test stacks are shared: take one with OspreyFlow_Build/scripts/stack_lease.sh acquire <lane> "<purpose>"
(it gives you stack a or b, whichever is free, and prints the export line for its ports: pin exactly
those, with OSPREY_LANE=<lane>), start it with stack_lease.sh up <lane> and stop it with stack_lease.sh
down <lane> before release (the throwaway containers in scripts/lane_stacks.tsv; never make dev-up,
whose 2480 is the owner's own deployment), and name the lease and its stack in any timing or reliability
figure you record. Send a heartbeat with
OspreyFlow_Build/scripts/lanes_heartbeat.sh beat <lane> <state> "<what you are doing>" when you start
planning, start work, start tests, ask me something (waiting-for-owner), are blocked, are ready to merge
(ready-to-merge), finish (idle), and after every commit. If a beat shows a message from the
orchestrator, act on it before going on. If it says PAUSE REQUESTED (ADR-142 Amendment 1), stop at the
next safe point, never mid-tool: bring the stack down if it is up, write
OspreyFlow_Build/process/lanes/<lane>/HANDOFF.md (at most thirty lines: the step and part; the last
commit; what is done, what is next, what was running; open questions; what the next session must not
redo), run OspreyFlow_Build/scripts/lanes_launch.sh pause-done <lane> "<step>" (it releases the lease,
makes the wip commit and beats paused), and end your session. Build every screen for the dark, light and GOV.UK themes and run the axe scans for
all three. Write your friction-log row as process/friction/<yyyy-mm-dd>-<lane>-<slug>.md, one row,
ending "Hash: recorded at merge." Commit in small Conventional Commits naming the files; never stage
OspreyFlow_Core/osprey.yaml or OspreyFlow_Core/data/; never merge to main; never push; no
Co-Authored-By lines.

Take a stack only as `stack_lease.sh acquire <lane> "<purpose>" && <the live run>`: never chain with
`;`, and never touch a test stack's containers, databases or networks with docker or psql unless the
lease is yours (8 November 2026: a refused acquire chained with `;` ran on against another lane's stack).

Playwright never reuses a server already on its port (8 November 2026: a lane's keyboard run was served
another worktree's tree): a busy port fails the run, so wait for it or find who holds it (`lsof -iTCP:<port>
-sTCP:LISTEN`); set OSPREY_REUSE_SERVER=1 only for a server you started yourself in this worktree.

Your leased live run always includes `tests/services/api/test_route_rights.py` (every route names its right)
and every live file your change can reach, not only your own: `make test` skips live files, so two
regressions on 8 November reached main unseen (14 pack cases, and two routes missing from the rights table).

Every live test removes what it writes to a test stack, in teardown, even when it fails: the stacks are
shared, and a row your branch's schema allows but main's does not (a new status, say) stops other lanes' runs
until you merge (8 November 2026: a lane's leftover link-type proposals stopped the Conduit on two stacks).

Once you send ready-to-merge, leave the branch exactly as gated (no rebase, no commit) until the orchestrator
answers: its independent review reads the worktree, and a rebase under it leaves the review reading half a branch.

Every question for the owner, every request (a reservation, a shared commit, a ratification) and your
ready-to-merge go to the orchestrator's session by cross-session message (send to `uds:/tmp/cc-socks/8906.sock`: a
session on another account cannot find it by its name, ospreyflow-7e), never only in
this window: the owner is often away, and the orchestrator answers or puts the question to the owner and
sends the answer back. While a question is open, carry on with whatever it does not block.

Before you report ready-to-merge, run the lane-reviewer agent on your own branch against your brief
and rules 1-15, fix what it finds, and say in your report that you did and what it found (the build
plan's review rule 1). Then rebase onto current main, and at that commit run make -k ci and make test
offline, saving their outputs as process/lanes/<lane>/gates/<sha>.ci.txt and <sha>.test.txt with every
failure explained (the seven trivy image scans may fail on Docker Hub's pull limit). Send the commit,
its tree (git rev-parse <sha>^{tree}) and the counts with ready-to-merge: if main has not moved, the
orchestrator merges on your run.

End with a report of at most twenty lines, also saved to process/lanes/<lane>/REPORT.md: each exit
criterion and whether it is met, with the test that proves it; what is left and why; the commits;
requests to the orchestrator; questions for me; and whether anything of yours is still running.
