# studio lane · report · L1.4 (phase 7b, staging drawers; ADR-140 Amendment 12), 8 November 2026
1. **Drawer per step: met.** Six drawers, typed fields only (rule 8), each with a live sample; `ingest-studio.spec.ts` covers 13 new ids (K1–K8), 46/46; axe 7 states × 3 themes + label checks, 28 green.
2. **Same words as the save gate: met.** Sample and save both call `staging_gate`, a later step's refusal included (`test_studio_staging_routes.py`; R1c, R2).
3. **Profiler on staged tables: met.** A staged pipeline's Map editor maps the last step's table, profiled (K7).
4. **Run route feeds the sources: met.** Each source is read by its own `<run>:<node>` load, so no two runs share a raw file (`test_staged_pipeline_run.py`, P1).
5. **Counts, metering, refs: met.** In the schemas commit at the branch's head: step counts on the report and view (withheld with the other counts); `RejectionRef`, no row key; `rows_staged` and `parquet_bytes` set (S1–S5, C1–C8, P2, P4).
6. **Phase 7's exit: met.** Visits and contacts built by keys, mapped over the staged table, tested and deployed (keyboard). Run with every element traced to its rows (`test_phase7_exit.py`). Live under lease studio, stack a, 19:03–19:05Z.
7. **Carried: met.** One encoding: `engine.hash_parts`.
8. **Settled:** Q1–Q4 (a) by the orchestrator. **Decisions taken:** list records from their rows' files, read when the live model names them; list rows admitted by synthetic SHA-256 (rule 9); plain gate words.
9. **Reviews:** my lane-reviewer, two rounds, all fixed, each planted red (`L1.4_RED_RECORD.md`). Round 1: preview oracle on masked rows, preview reading any file (rule 3), a source silently dropped (rule 2). Round 2: list rows withheld from a case not reading the dataset (rule 4). The orchestrator's review (A, B): a source read only if it is one of the recipe's dataset's files, refused at save and Connect; Test and Preview of a staged pipeline with the drawer's two guards; the test root each test's own folder (A1–A4, B1–B2).
10. **Slip (rule 14), mine:** an offline run wrote one synthetic bucket to stack a's store. Reported, removed under my lease; the live file now skips without one (friction row).
11. **Gates:** in `gates/<sha>.*` at the rebased head, every failure explained, none mine.
12. **Left:** step counts not yet drawn on the Glass's run report.
13. **Commits:** 19 on lane/studio above main, the schemas commit first.
14. **Requests (a–b):** (a) your shared commit of `actionRegistry.ts` and `every-harness.spec.ts` (`L1.4_*.diff`); (b) ratify outside my map: spec/03's route line, `tools/no_branches_check.py`'s entry, `run_resources.py` and the lifespan's one target-model pool, five route tests, `reportsMap.ts`.
15. **Requests (c–e):** (c) mark Amendment 12 written; (d) and (e) fixed on your review (item 9); left recorded: Test of a pipeline with no steps still counts over masked rows, as before phase 7.
16. **Questions:** none. **Running:** nothing; no lease held.
