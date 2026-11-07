# Studio lane · brief L1.2a and L1.2b · main's red tests, phase 6's exit, then pipelines by loading case

Written by the orchestrator, 7 November 2026, after L1.2's merge (`25b1084`). Opus, medium. Do the parts in
this order. Part C waits for L3.1's merge, and I will tell you when it lands. Stop at a clean, committed
point after each part, and message me ready-to-merge for it, so each part merges on its own.

**Binds.** `process/CLAUDE.md` rules 1–15 (rule 14 as ADR-142 rewords it; the leased stack is the throwaway
test stack, `SESSIONS_RUNBOOK.md` §4); ADR-140 and Amendment 8; `spec/09_INGEST_STUDIO.md`;
`spec/ingest_studio_redesign/BUILD_PLAN_INGEST_STUDIO.md` phase 6.

**Part A (L1.2a, now): main's four red tests,** all on `main` since before the lanes:
- `test_revert_elements_by_type` and `test_write_onto_a_reverted_node`: the tests' expected SQL lacks the
  `withdrawn_by_load = null` the revert now writes. Decide which is right, from ADR-110 Amendments 8–9.
- `test_unfiltered_node_lookup_confined`: `services/ingest/snapshot_withdrawal.py` calls
  `GraphPort.live_edges_touching` outside the confined modules. This is rule 3's guard. Either the read
  is confined, or it is shown to read no case's data and allowlisted with a stated reason. Test first.
- `test_load_checks.py`'s two verify cases: the `studio` fixture never overrides `get_recipes_repo_root`.

**Part B (L1.2b, now): phase 6's exit.** The Prison Intelligence reports pipeline is built from scratch in
guided mode by someone following the demo script, and edited in expert mode. So: write the from-scratch
steps into `DEMO_GUIDE.md` chapter 4 (New pipeline, choose the registered source, + entity, the
bindings the committed reports map makes); make the harness walk build what the reports map builds;
add an expert-mode edit of the reports pipeline; walk it live once on the throwaway stack under the
lease, naming the lease. Record what is and is not met.

**Part C (L1.2a, after L3.1 merges): the owner's ruling of 7 November.** Only a case that loads into a
dataset lists or opens its pipelines. Enforce it in the store's query for `get_authorized`,
`list_drafts` and `list_all` with one clause (`dataset_id` = the loading dataset, and the NULL case
decided and tested). Parametrise every `AuthorizedStudioRecipeDep` and `RunnableStudioRecipeDep` route
(nineteen) with a cross-case case and a composite principal built by `scope_to_case`. The fake store
must refuse what the real one refuses. This needs an amendment: ask me to reserve it.

**Files.** The Studio lane's map; `DEMO_GUIDE.md` chapter 4 (ratified for part B). Take the lease for
every live run, the throwaway stack included.

**Report** per part (Prompt L's format, at most twenty lines, in `REPORT.md`), with questions for the
owner sent to me by message.
