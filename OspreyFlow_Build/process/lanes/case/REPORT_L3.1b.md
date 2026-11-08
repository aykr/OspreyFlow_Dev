# Case lane · L3.1b · report (8 November 2026)

Built from `process/lanes/case/L3.1b_PLAN.md`, the brief, with the orchestrator's answers. Phase 5's
target-model half, ADR-145 Amendment 4's home case and *Make live* owner step, and the `drawn` kind.
Two schemas commits went to main alone and first: be60199 (step 0) and afdb1f0 (the routes'
shapes), with 1c97b9d for step 5's ceiling and drawn input.

## What L3.1b meets

1. **A dataset's domain model** (ADR-140 decisions 4 and 5, R12; `01_DOMAIN_MODEL.md` §2.2b).
   - The store (`services/api/target_models.py`), in memory and on Postgres:
     - one live version and at most one draft per dataset, a second draft refused in words, with a
       partial unique index on Postgres for each;
     - a draft opens as a copy of live, or as version 1 with the POLE core alone;
     - an extension is retired, never deleted, and may be restored by a revert;
     - a POLE core type cannot be an extension;
     - *Make live* names the draft it was shown;
     - a revert is a new draft N+2, never a rewrite.
   - Seven routes under `/v1/datasets/{dataset_id}/model`, behind the dataset's gate and
     `edit_target_model` (D8, the data engineer's; ADR-112 Amendment 6). A composite's model is read,
     not changed.
   - **Impact:** the changed types (each pack's own types from `type_packs`, never one it only
     widens, plus the extensions); the deployed pipelines writing them; and only the cases and
     composites the reader may open (rule 7).
   - **Make live** flags and pauses exactly those pipelines, through `flag_for_model`, ratified by
     studio on its conditions.
2. **A case's packs are derived** (ADR-126 Amendments 2 and 3).
   - At the case's level check (one place) and in the listing, the packs come from its dataset's
     live model. The stored packs stand while the dataset has no model.
   - A change of packs through the case is refused (409 `packs_from_the_model`).
   - `scripts.seed_target_models` gives each dataset a live v1 whose packs are the union of its
     own cases' choices. Each case counts only for the dataset it chose, so no case's packs reach a
     dataset it doesn't read. It runs dry first, and a second run changes nothing.
   - The Glass's case settings show the packs read-only, in the *domain model* wording, with no
     change offered (`CaseDomains.tsx`). Vitest, keyboard 4/4 and axe 8/8 pass.
   - `investigations.domains` is kept and marked deprecated in spec 01.
3. **The home case and *Make live*'s owner step** (ADR-145 Amendment 4 decisions 2, 4, 5 and 7).
   - The first *Make live* asks who answers for the dataset. Refused in words:
     - no one;
     - a team, until L2.5;
     - an owner kind the System setting forbids;
     - anyone the directory doesn't hold as a person (never a service account);
     - anyone at all when there's no directory to ask (fail closed).
   - It then makes the home case, named for the dataset and reading it, with exactly the named
     owners as its Authors.
   - A home case cannot be removed. A later *Make live* naming owners is refused.
   - Admin › System's *Dataset owners may be* has its routes (administer_system, audited).
   - `scripts.make_home_cases` gives existing datasets theirs, the person who made each as Author.
     It gives none where that isn't a person, and names each such case as needing an owner. Dry
     run first.
   - One home case per dataset per deployment: the reading of decision 5.
4. **The `drawn` kind** (ADR-143 Amendment 2 decisions 3 and 5).
   - `POST /v1/datasets/drawn` makes, in one step, the drawn dataset, its live model and its home
     case, with the maker as Author.
   - Its `highest_marking` is set within the maker's clearance. The refusal's words name only the
     maker's own clearance.
   - Read through its home case alone: no other case may choose it, each guard holding alone.
   - No load into it (409 `drawn_not_loaded`), and no rule in its case until merged (409
     `drawn_not_judged`).
   - Every dataset's highest marking is on Admin's datasets (None meaning the deployment's highest)
     for glass's column. L3.3 enforces it on writes.

Each refusal and rule above has a test that fails with that check alone removed (rule 15).

## Live figures (each with its lease)

- **Step 1**, lease `case` taken 02:22:02Z, at 4cc2eb1. Run 02:22:16–02:22:54Z: **260 passed,
  0 failed**. It covered the store on Postgres (two drafts at once, one refused; the indexes, and
  red with them dropped), flag_for_model on Postgres (red twice), the route, rights, places and
  census tests, and the seeding script.
- **Steps 3 and 4**, lease `case` taken 03:39:56Z, at f879dd8.
  - Run 03:40:00–03:40:22Z: 228 passed, 1 failed.
  - The failure was route_rights' no-role test: "rejected SSL upgrade" four seconds after the
    Postgres container started. Alone under the same lease it passed 1/1, on the branch and on
    main's code.
- **Step 5**, lease `case` taken 03:52:51Z.
  - The first run at b3238b2 had 155 passed and 9 failed.
    - **Eight were mine and real:** the lifespan left a closed target-model store on the state,
      which every case's level check now reads, so a later app in the same process got "pool is
      closed". Shown under the same lease: route_rights then composite_schedules failed on the
      branch and passed 64/64 on main.
    - **One was my test, not the code:** a constraint query that didn't filter to its own schema.
  - Both were fixed in 39242db. The re-run, 03:56:20–03:56:56Z: **164 passed, 0 failed**.
- **The whole suite, stack-free, against main** at each step: no branch-only failure beyond:
  - the new Postgres tests, which need the stack;
  - this worktree's local `osprey.yaml` and `graphify-out`;
  - the CI wiring the patch covers.

  Final figures at the tip: see the message sending this report.

## For the orchestrator

- **`process/lanes/case/registry-domain-models.patch`:** removes
  `change-a-cases-domain-models-by-keyboard` from `CASE_DATASETS_ACTIONS` (`keyboard/actionRegistry.ts`).
- **`process/lanes/case/ci-wiring-L3.1b.patch`:** wires `test_target_models_store.py`,
  `test_seed_target_models_store.py` and `test_make_home_cases_store.py` into ci.yml's live job and
  both test-job ignore lists (ci.yml and the Build Makefile).
- **The main-side findings,** already routed:
  - the seven alert-jump 500s (fixed on main, 4f8d6f3);
  - `test_recipe_runs_unreverted`'s `own_key_merges` (studio's);
  - `test_ws_ticket.py:26`'s hardcoded Valkey port.

## Ratify, outside the case map

- **The Conduit:** `services/api/{app (the model, drawn, owner-setting and home-case routes; the
  level check's derivation; the loading and rule refusals; the lifespan),studio_recipes
  (flag_for_model, ratified by studio)}.py`.
- **Lane 1's and Lane 2's files, each as agreed:**
  - `apps/workspace/src/investigation/{CaseDomains,CaseDomains.test,CaseSettings,CaseSettings.test}.tsx`
    and `cases.ts` (ratified for the read-only control);
  - `apps/workspace/keyboard/case-datasets.spec.ts`;
  - `apps/workspace/src/shell/placesByRole.json` (regenerated).
- **Other lanes' tests:** `services/api/test_{admin_sections,alert_evidence_withheld,case_domains,
  composite_schedules,no_corpus_counts_on_the_wire,place_routes,route_rights,studio_recipes_store}.py`
  and `working_set/test_branch_by_filter.py`.
- **The spec:** `spec/{01,03,06}`. In 06, ADR-112 Amendment 6 and ADR-126 Amendment 3 are
  reserved and written.

## Open, carried

- **Teams as owners** wait on L2.5. Until then `teams_only` lets no dataset go live, and says so.
- **A composite's own model** waits for its superset check.
- **The highest marking's enforcement on writes** is L3.3's.
- **The board for a drawn dataset** is L3.3's. Merging a drawn dataset is L3.9's.
- **Studio's share:**
  - a deployed pipeline pins the model version (`model_version`);
  - a Test run names the draft;
  - the screens: the Model tab, the pipeline node's removal, *Make live*'s owner step and the
    *Drawn* badge.
- **Glass's share:** the System control for the owner setting, and Admin › Datasets' *Highest
  marking it may hold* column.
