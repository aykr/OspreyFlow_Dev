# Studio lane · brief carries · two carried Studio items (S)

Written by the orchestrator, 12 November 2026, for a **fresh studio session on `sol`**, from **main** (`git
fetch`, branch `lane/studio-carries` from `main`). Read CARRIES.md rows 90 and 123 and ADR-140 Amendment 19's
reservation first. Opus, medium. Size S.

**The lane, the stacks, the merge rule.** Test stacks are on the owner's server only (b to g); Docker and stack a are off on this Mac, so never start Docker. Ask the orchestrator for a stack, then main's `stack_lease.sh` (acquire, up, `remote studio -- …`, down, release; `remote-log studio` reattaches). `make test` runs on the server: `stack_lease.sh offline studio -- make test` (it runs pytest, live-collect and test-js in turn; test-js also on the Mac, where Node is). Ask before `make -k ci` or any Playwright here (two heavy runs at most). Never call remote or offline while one of your runs is alive. Prompt L's rules: never stop on a question; build the recommended option (the strict one for access) and log it under "Decisions taken"; real data stops a piece. Your own lane-reviewer, then the gates at a commit rebased onto main, saved under `gates/`, raw, not filtered, with one leased live run including `test_route_rights.py`; re-gate after any code change. Report to the orchestrator **by message**.

**Build, each red first (rule 15):**
1. **An import replacing an in-progress draft** (CARRIES row 90, L1.7's review): `studio_release.apply_import`
   silently replaces another person's in-progress model draft. Refuse it in words naming whose draft it is and
   how to proceed; the importer's own draft may be replaced only with an explicit confirmation. The Glass
   shows the refusal (keyboard step, rule 13, if a new action appears). A test for each: another's draft
   refused, own draft with and without confirmation, no draft.
2. **A source's declared default marking at a Join** (CARRIES row 123; **ADR-140 Amendment 19, reserved for
   you**): keep the guard fail-closed (an unmarked table never joins a marked one). Add a source-level declared
   default marking that an unmarked table's rows carry before the join, set in Studio › Sources by someone with
   the source-approver right, audited (who, when, from, to), and the Join's refusal naming that setting. An
   access-control test on the setting's write and read (rule 4); the default never lowers a bound marking.
   Write Amendment 19 as built, with the test that would fail for each sentence (rule 12).

**Never.** osprey-small (the owner's demo deployment, v0.5.0, frozen) and its containers are never touched, read
or written by this step: throwaway lane stacks only. Nothing of this step runs on the server from **12:00 UK on
Friday 13 November** until the owner says the demo is over. Not pushed; the orchestrator merges. It goes into
v0.5.1 with the chain. D2c and the client-install chain keep priority for merges and reviews.
