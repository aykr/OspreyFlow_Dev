# Studio lane · brief L1.4 · phase 7b: the drawers for each staging step, and phase 7's exit

Written by the orchestrator, 8 November 2026, after L1.3's merge (`04a8cdf`), for a **fresh studio session** on account
`sol`. Read `process/lanes/studio/REPORT.md` (L1.3, items 11 and 12) and ADR-140 Amendment 11 first. Rebase
onto `main`. Opus, medium. Size M.

**The lane, the stacks, the merge rule.** Studio's ownership map; a test stack by `stack_lease.sh acquire
studio "<purpose>" && …`, pinning the ports it prints; questions, requests and ready-to-merge to the
orchestrator by message (Prompt L); before ready-to-merge, your own lane-reviewer, then make -k ci and make
test at a commit rebased onto main, saved under `process/lanes/studio/gates/`.

**Binds.** `process/CLAUDE.md` rules 1–15 (3, 7, 8, 12, 13 and 15 above all); ADR-140 and Amendments 8–11;
`spec/09_INGEST_STUDIO.md` §9; `spec/ingest_studio_redesign/BUILD_PLAN_INGEST_STUDIO.md` phase 7 ("Drawer
editors for each step with a live sample"; the profiler on staged tables) and its exit.

**Build** (the plan's row L1.4, with L1.3's item 11):
1. **A drawer per staging step** (Lookup, Join, Filter, Derive, Union, Dedupe) beside the pipeline, as
   Amendment 8's drawers are, each with a live sample of its output and the save gate's refusals in words;
   guided mode offers no expression anywhere (rule 8).
2. **The profiler on staged tables.**
3. **The run route feeds a pipeline's sources** to the staging engine, each upload its own load, so no
   two runs share a raw file (L1.3 item 12's check-then-write race closed).
4. **Per-step counts and staging metering** on `LoadReport` and `RunMetering`, and refs on
   `RejectionRecord`: a `packages/schemas` change, sent first as a schemas-only commit with make ci and make
   test run on it. No row key reaches any of them (rule 7, the orchestrator's settlement).
5. **Phase 7's exit:** the prototype's "Visits and contacts" pipeline, minus its two expert steps, built
   in the Studio by keys and run on the synthetic data, every created element traceable to its source rows.

**Tests first, each red by a plant at the real call site:** each drawer's actions by keyboard (rule 13),
registry ids as a diff for the orchestrator; axe in dark, light and GOV.UK; a drawer refuses what the save
gate refuses, in the same words; two concurrent runs of one source never share a raw file; per-step counts
equal the staged tables'; phase 7's exit walk.

**Carried, fix if quick:** `_hash` beside `engine.encode_key_parts`, one encoding.

**Exit.** Phase 7's exit; make ci and make test green offline; a live walk under a named lease and stack;
a friction fragment. Report in Prompt L's format, then stop.
