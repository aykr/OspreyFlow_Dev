# Rules lane · brief lists · screening lists in live files, and one owner on two lists (S)

Written by the orchestrator, 12 November 2026, for a **fresh rules session on `sol`**, from **main** (`git
fetch`, branch `lane/rules-lists` from `main`). Read CARRIES.md rows 113 and 114, ADR-146 Amendment 3 and ADR-109
Amendment 7 first. Opus, medium. Size S.

**The lane, the stacks, the merge rule.** Test stacks are on the owner's server only (b to g); Docker and stack a are off on this Mac, so never start Docker. Ask the orchestrator for a stack, then main's `stack_lease.sh` (acquire, up, `remote rules -- …`, down, release; `remote-log rules` reattaches). `make test` runs on the server: `stack_lease.sh offline rules -- make test` (it runs pytest, live-collect and test-js in turn; test-js also on the Mac, where Node is). Ask before `make -k ci` or any Playwright here (two heavy runs at most). Never call remote or offline while one of your runs is alive. Prompt L's rules: never stop on a question; build the recommended option (the strict one for access) and log it under "Decisions taken"; real data stops a piece. Your own lane-reviewer, then the gates at a commit rebased onto main, saved under `gates/`, raw, not filtered, with one leased live run including `test_route_rights.py`; re-gate after any code change. Report to the orchestrator **by message**.

**Build, each red first (rule 15):**
1. **Live files remove the screening lists they load** (CARRIES row 113): `test_screening_refresh.py` and every
   live file that loads a screening list into the shared store removes it in teardown, including on failure.
   The red: a second file's case that sees the first file's list (the synthetic people both name) goes green
   once teardown removes it. Find every such file, not only the two named.
2. **One owner on two screening lists** (CARRIES row 114; **ADR-146 Amendment 7, reserved for you**). **The
   owner's ruling is pending.** The orchestrator's recommendation: one alert citing both lists, each list's
   citation (and its `owner_listed` factor) shown only to a reader cleared for that list, so the alert never
   reveals a list a reader cannot see (rule 3); a true positive confirms every cited match (ADR-109 Am 7).
   **Build everything that does not depend on the ruling now:** the test that two lists naming one owner are
   seen together; the per-list visibility of a citation (needed under either answer); the disposition across
   both. Then build to the recommendation behind one switch point, and message the orchestrator when you
   reach it: you are told the ruling before the pieces that differ are finished. Amendment 7 as built, with
   the test for each sentence (rule 12).

**Never.** osprey-small (the owner's demo deployment, v0.5.0, frozen) and its containers are never touched, read
or written by this step: throwaway lane stacks only. Nothing of this step runs on the server from **12:00 UK on
Friday 13 November** until the owner says the demo is over. Not pushed; the orchestrator merges. It goes into
v0.5.1 with the chain. D2c and the client-install chain keep priority for merges and reviews.
