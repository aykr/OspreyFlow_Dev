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
