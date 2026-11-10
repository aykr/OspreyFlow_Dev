# Rules-b lane · brief L2.11a · the rule editor's standards: BPMN 2.0 and DMN storage, export, import refusal, Show as BPMN

Written by the orchestrator, 10 November 2026, for a **fresh rules-b session**, **from main** (rebase onto main once
rules' L2.10 merges; the orchestrator tells you). Split from rules' L2.11 at rules' own proposal, so the demo track's
longest step runs in two lanes. Read `spec/06_DECISIONS.md` **ADR-146** (search `## ADR-146`): decision 3's "Stored
to the standards" and its tests (the round-trip, the import refusal, *Show as BPMN*'s keyboard case). Opus, medium.
Size S–M.

**The lane, the stacks, the merge rule.** Test stacks on the owner's server only (b to g); Docker and stack a off on
this Mac, so never start Docker. Ask the orchestrator for a stack, and before `make -k ci` or Playwright here (two
heavy runs at most). `make test` through `stack_lease.sh offline rules-b -- sh -c 'make -k test SKIP_JS=1; cd
../OspreyFlow_Core && make test-js'`; one server run at a time; TaskStop does not stop the server half. Never stop
on a question: build the recommended option (the strict one for access) and log it under "Decisions taken". Your own
lane-reviewer, then the gates at a commit rebased onto main, saved under `gates/`. Report to the orchestrator **by
message**; to rules by message for the interface.

**First, agree the interface with rules.** Rules owns the rule's *When / If / Then* shape in `packages/schemas` and
the editor surface. Agree the shape by message before writing code; build on rules' schema, never a second one.

**Build:**
1. A codec, a pure package over the rule model: a rule saved as a BPMN 2.0 process of three elements (a start event,
   a business-rule task, an end event that raises the alert) and a DMN decision table for its *If*.
2. *Export*: the `.bpmn` and `.dmn` files for a rule (the route under rules' rule routes, by agreement; rule 4's
   access-control test for it).
3. Import: a file with elements OspreyFlow does not run is refused, naming the unsupported elements (and nothing of
   any rule the importer may not see).
4. *Show as BPMN*: the read-only drawing as a component; rules mounts it in the editor. Its keyboard case (rule 13)
   and axe in three themes, by diff for the shared harness files.
5. ADR-146's tests: export then import gives the same rule; the refusal names the unsupported element. Red first, at
   the real call site, the planted fault in the shape the codec really reads (rule 15).

**Not yours:** the declared dataset, the form, draft/test/live, *Changes*, `scripts.migrate_rules_to_datasets`, the
Lists tab — rules'.

**Exit.** A rule exports to `.bpmn`/`.dmn` and imports back to the same rule; an unsupported file is refused in
words; *Show as BPMN* draws it, by keyboard; a friction row. Licence register: any new package (a BPMN or DMN
library) checked against `make licence-check` before it is added.
