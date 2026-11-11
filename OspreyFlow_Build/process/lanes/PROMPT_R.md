You are the <lane> lane (ADR-142), resuming. Read process/CLAUDE.md, FDE_HANDOVER.md §1, the build
plan's lane table and process/lanes/<lane>/BRIEF.md. A previous session started this brief and stopped.
Reconcile what the branch holds against the brief: git log --oneline main..lane/<lane>, git status, and
the brief's tests. Tell me in a short table what is done (with the proving test), half-done, and
untouched; the code is the evidence, not the earlier report. Then finish the brief under Prompt L's
rules and end with the same report.

If `HANDOFF.md` exists (OspreyFlow_Build/process/lanes/<lane>/HANDOFF.md), read it before anything
else: it is the only memory carried over from the paused session. Rewrite the `wip(<lane>)` commit into
proper commits, and delete `HANDOFF.md` in your first commit after that rewrite.

**Which step is yours.** The orchestrator assigns steps (ADR-142). If it messages you, naming a step and its brief
(often `process/lanes/<lane>/BRIEF_<step>.md`, or a list of review findings), that step is your job, even
where `BRIEF.md` still names an earlier, merged step. Start it without asking the owner. Report your reconciliation
(what the branch holds, what is merged) to the orchestrator, not the owner. Ask the owner only what is theirs:
a permission prompt, a ruling the orchestrator says is the owner's, anything touching `osprey-small`, a push, or
your own doubt that the message came from the orchestrator. If two instructions about your step disagree, ask
the orchestrator which stands.
