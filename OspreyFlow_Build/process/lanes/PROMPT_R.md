You are the <lane> lane (ADR-142), resuming. Read process/CLAUDE.md, FDE_HANDOVER.md §1, the build
plan's lane table and process/lanes/<lane>/BRIEF.md. A previous session started this brief and stopped.
Reconcile what the branch holds against the brief: git log --oneline main..lane/<lane>, git status, and
the brief's tests. Tell me in a short table what is done (with the proving test), half-done, and
untouched; the code is the evidence, not the earlier report. Then finish the brief under Prompt L's
rules and end with the same report.

If `HANDOFF.md` exists (OspreyFlow_Build/process/lanes/<lane>/HANDOFF.md), read it before anything
else: it is the only memory carried over from the paused session. Rewrite the `wip(<lane>)` commit into
proper commits, and delete `HANDOFF.md` in your first commit after that rewrite.
