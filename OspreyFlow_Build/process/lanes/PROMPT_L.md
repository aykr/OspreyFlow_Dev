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
