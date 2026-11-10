# Studio lane · brief L1.7 · Operations and external orchestration; Studio › Releases

Written by the orchestrator, 10 November 2026, for a **fresh studio session** (`ayan`), **started from lane/studio at
8d997d4 (L1.5, cleared, merging now)**: build on it, and rebase onto main once L1.5 is merged there (the orchestrator
tells you). Read `process/lanes/studio/REPORT.md` (L1.5), ADR-145 decision 9 and ADR-140 Amendment 9 decision 4
first. Opus, medium. Size L.

**The lane, the stacks, the merge rule.** Test stacks are on the owner's server only (b to g); Docker and stack a are off on this Mac, so never start Docker. Ask the orchestrator for a stack, then main's `stack_lease.sh` (acquire, up, `remote studio -- …`, down, release; `remote-log studio` reattaches). `make test` runs on the server: `stack_lease.sh offline studio -- sh -c 'make -k test SKIP_JS=1; cd ../OspreyFlow_Core && make test-js'`. Ask before `make -k ci` or any Playwright here (two heavy runs at most). Never call remote or offline while one of your runs is alive. Prompt L's rules: never stop on a question; build the recommended option (the strict one for access) and log it under "Decisions taken"; real data stops a piece. Your own lane-reviewer, then the gates at a commit rebased onto main, saved under `gates/`, with one leased live run including `test_route_rights.py`; re-gate after any code change. Report to the orchestrator **by message**.

**Build** (the plan's row L1.7): Phase 10's Operations content and external orchestration inside Admin's *Running ›
Operations* (ADR-145 decision 9; Admin's screen by agreement with admin); Studio › Releases, the YAML bundle,
`packages/schemas/release.schema.json` (a schemas commit first), `ospreyflow release export` and `import --dry-run`
(ADR-140 Amendment 9 decision 4). **Carried (CARRIES.md, studio rows):** the seven live tests failing on main; the Deploy
refusal's role id; the `subscribed=()` defaults; the Studio's door to the roles help page; Derive and the typed steps
over a marked column (rule 3, the strictest marking of what an output row draws on); the gazetteer identifiers in a
Studio-loaded case dataset. Each red first.

**Exit.** Phase 10's exit and ADR-140 Amendment 9's release tests; the carries closed or named as left; a friction row.
