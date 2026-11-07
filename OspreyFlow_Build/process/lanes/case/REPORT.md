# Case lane · L3.1 · report (6–7 November 2026)

**Lease for every live figure:** `case`, on the handover's throwaway test stack (ArcadeDB 2491, Postgres 55433, Valkey 6379), since `make dev-up` collides with the owner's deployment on 2480: 6 November for the first build, 7 November for the rulings; stopped and released at the end of each.
1. *Unchanged under case B* (ADR-143): **met.** `tests/conformance/graph_port/test_analyst_layer.py` (degree, by type, rank, type counts, `expand`, paths, `edges_among`), ArcadeDB 26.10.1; red with A's layer in B's read set.
2. Read set = source (or a composite's own id + its members) + own layer, nothing else: **met.** `tests/services/api/test_analyst_layer.py`, red with each defect planted in `datasets.read_set`; Postgres in `test_analyst_layer_store.py`.
3. No layer in any list for any role (Admin's too), or in a refusal's text; outside the case refused as a missing case: **met**, same files; Postgres lists red with `_OFFERED` planted out.
4. Migration: **met.** Dry run writes nothing (`_main --dry-run` over a pre-kinds schema, red with the store opened); removed cases placed, caseless rows reported, second run writes nothing. `tests/test_migrate_cases_to_one_dataset{,_store}.py`. **Not** run on the owner's deployment (the owner's to run).
5. The owner's rulings (7 November): **built.** Q1 (ADR-143 Amendment 1): hand-marking and manual `SAME_AS`/`NOT_SAME_AS` write into the layer, proposals and extractions into the source. Q2 (ADR-099 Amendment 14): a composite case writes under the composite's own id. Q3 (ADR-136 Amendment 1): as built, no longer interim. `tests/services/api/test_case_writes.py`, each writer at its real call site under `scope_to_case`, red first (layer not held; members first).
6. Phase 5's exit: **contract half met; target-model half is L3.1b** (Q4). Still open: `same_as_writer` into composites (Amendment 12 item 4); the alert jump's "a dataset of its own" fallback (item 6).
7. Spec: `01` §2.2a and §4, `02` (new case), `03` (routes), `04` (egress), the three amendments in `06`. Friction: `process/friction/2026-11-06-case-analyst-layer-read-set.md`.

**Wider run:** see the closing line. **lane-reviewer** (22 findings on the first build): fixed 1–3, 5–9, 14, 16, 17, 20, 21; the rest are in item 6 and the requests.
**Commits:** `git log main..lane/case` (rebased on main at f7a83a1).
**Requests to the orchestrator:**
- Ratify files outside the map: `services/api/{datasets,questions,model_routing,dataset_scope,document_reader,email_extraction}.py`, `services/api/working_set/service.py`, `scripts/{case_seed,stamp_datasets}.py`, `a11y/every-harness.spec.ts`, `spec/02`, `spec/ADR_RESERVATIONS.md` (three rows to `written`), and other phases' tests that made a case naming no dataset.
- Commit `BUILD_PLAN_INGEST_STUDIO.md`; fix `make dev-up`'s collision on 2480; have the owner wire `test_analyst_layer_store.py`, `test_migrate_cases_to_one_dataset_store.py` and `test_case_writes.py` into `ci.yml` and the `Makefile`.
- Open minor items: the disabled *Create case* button's text is low-contrast on amber (default) and blue (GOV.UK), seen in the hand check, exempt from axe as disabled, styling not this lane's; `create_investigation` can leave an empty dataset when the case fails to be made; a composite's three writes are not one transaction; typing a new dataset's name has no keyboard step; Ask's composite labels are untested; marks and links written before Amendment 1 stay in the source (no silent move).

**Hand check (default and GOV.UK):** `cd OspreyFlow_Core/apps/workspace && node scripts/sync_govuk_assets.mjs && npx vite --port 5185`, then `http://localhost:5185/keyboard/case-datasets-harness.html` and `…?brand=govuk&choice=existing`. Run by the lane on 7 November: dark, light and GOV.UK correct; keyboard 5/5, axe 8/8.

## The owner's rulings (7 November 2026), all as recommended

1. Analyst writes: split (ADR-143 Amendment 1). 2. A composite case's writes: the composite's own id (ADR-099 Amendment 14). 3. A layer's egress: the strictest of its case's (ADR-136 Amendment 1). 4. Phase 5's target-model half: L3.1b, not tonight.
