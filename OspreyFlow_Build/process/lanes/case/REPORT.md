# Case lane · L3.1 · report (6 November 2026)

**Lease for every live figure:** `case`, 6 November 2026, on the handover's throwaway test stack (ArcadeDB 2491, Postgres 55433, Valkey 6379), since `make dev-up` collides with the owner's deployment on 2480; stopped and released at the end.
1. *Unchanged under case B* (ADR-143): **met.** `tests/conformance/graph_port/test_analyst_layer.py` (degree, by type, rank, type counts, `expand`, paths, `edges_among`), ArcadeDB 26.10.1, leased; red with A's layer in B's read set.
2. Read set = source (or composite members + own id) + own layer, nothing else: **met.** `tests/services/api/test_analyst_layer.py`, red with each defect planted in `datasets.read_set`; Postgres in `test_analyst_layer_store.py`.
3. No layer in any list for any role (Admin's too), or in a refusal's text; outside the case refused as a missing case: **met**, same files; Postgres lists red with their one condition (`_OFFERED`) planted out.
4. Migration: **met.** The dry run never opens the bootstrapping store and writes nothing (`_main --dry-run` over a pre-kinds schema, red with the store opened). The real run places removed cases too and reports rows with no case. A second run writes nothing. `tests/test_migrate_cases_to_one_dataset{,_store}.py`. "Every seeded case" is proved on the seeded shape in memory and on Postgres, **not** on the owner's deployment (the owner's to run).
5. Phase 5's exit: **partly met.** One dataset per case, composites, search/paths through the one access step: done. **Not built:** ADR-126 derived, `TargetModel`, reference lists, the domain-model node (question 4); `same_as_writer` writing into composites (Amendment 12 item 4); the alert jump's "a dataset of its own" fallback, still there (item 6); a composite's own Studio reach (the Studio opens on the composite's id, the Conduit scopes to its first member; Lane 1 and question 2); a conformance case reading a composite's elements.
6. Spec rewritten: `01` §2.2a, `02` (new case), `03` (dataset routes), `04` §6 and ADR-136, the layer egress marked interim. Friction: `process/friction/2026-11-06-case-analyst-layer-read-set.md`.

**lane-reviewer** (22 findings): fixed 1–3, 5–9, 14, 16, 17, 20, 21; 4 and 10 are in item 5 above, 11–13 and 15, 18, 19, 22 in the requests below.
**Commits:** 774388a, 3f1bc01, 2bb69c9, and the fix commit after them (`git log 83ff99e..lane/case`).
**Requests to the orchestrator:**
- Ratify the files outside the map: `services/api/{datasets,questions,model_routing}.py`, `scripts/{case_seed,stamp_datasets}.py`, `a11y/every-harness.spec.ts`, `spec/02`, and other phases' tests that made a case naming no dataset.
- Commit `BUILD_PLAN_INGEST_STUDIO.md`.
- Fix `make dev-up`'s collision on 2480.
- Have the owner wire `test_analyst_layer_store.py` and `test_migrate_cases_to_one_dataset_store.py` into `ci.yml` and the `Makefile`.
- Reserve an ADR-136 amendment once question 3 is ruled.
- Open minor items: `create_investigation` can leave an empty dataset when the case fails to be made; a composite's three writes are not one transaction; the in-memory fake accepts unregistered ids; typing a new dataset's name has no keyboard step; Ask's composite labels are untested.

**Wider run, leased:** 477 of 478 touched-area tests pass; the one failure (`test_phase8_exit_criterion_end_to_end`, 403 `create_case`) fails identically at 83ff99e, before this lane.
**Still running:** nothing of mine (throwaway stack stopped, lease released).

## Questions for the owner (multiple choice, recommendation first)

1. **ADR-143 open question 1: where today's analyst writes go once each case has its layer.** (a) *Recommended (the ADR's):* hand-marking and `manual_link`'s `SAME_AS`/`NOT_SAME_AS` into the layer; accepted question proposals and accepted extractions into the source dataset as today. (b) All four into the layer. (c) All four stay in the source; the layer holds only what is drawn. *Until ruled:* all four write where they do today. Nothing built.
2. **ADR-099 Amendment 12 item 5: where data added to a case reading a composite is written.** (a) *Recommended:* the composite's own id (the case reads it; no member changes). (b) The case's layer. (c) Refused in a composite case. *Until ruled:* the first member, as before.
3. **A layer's egress (ADR-136).** A layer defaulting to `none` would stop every case asking a hosted model. (a) *Recommended:* the strictest of its case's source, or composite members (built so; one function). (b) Always `none`. (c) Set per layer by an administrator.
4. **Phase 5's split.** (a) *Recommended:* this step is the contract and the layer; `TargetModel`, reference lists, ADR-126 derived and the domain-model node become L3.1b, with a `packages/schemas` commit first and Lane 1's files agreed. (b) All of phase 5 in L3.1. (c) The target model and reference lists move to Lane 1.

## Hand check (default and GOV.UK)

`cd OspreyFlow_Core/apps/workspace && node scripts/sync_govuk_assets.mjs && npx vite --port 5185`, then open
`http://localhost:5185/keyboard/case-datasets-harness.html` and `http://localhost:5185/keyboard/case-datasets-harness.html?brand=govuk&choice=existing`:
*What data does this case read?* shows *Use an existing dataset…* (radios, *Both carriers (a composite of 2 datasets)*) and *Make a new dataset* (the default).
