# IS1, Studio answers (slice A): the refresh of 21 November 2026

**What this is.** The 14 questions in section 8 of the Ingest Studio specification were answered on 18 November 2026 from `main` at `528d475`, read only (`ospreyflow_evidence_2026-11-18/STUDIO_ANSWERS.md`, git-ignored). This is the refresh against main as it stood on 21 November (HEAD `e0a7032`), made by a read-only scout that ran nothing (no test, build, browser or sweep), so it is **not a seat**. Nothing here is a decision: where a choice is the owner's it is marked, and it goes to him in one numbered list. IS2 (the model step and entity type form) and IS3 (the dataset map) wait on it.

Path roots: C = `OspreyFlow_Core/`, B = `OspreyFlow_Build/`.

**Headline.** Twelve of the 14 answers still hold. Line numbers have drifted by 1 to 40 lines, so the 18 November citations are unreliable (list C has today's). Question 14 has changed: **SE3 (merged, `7285411`) put a creator check into code.** ADR-140 Amendment 22 and ADR-152 X4 to X7 (accepted 19 November) settle most of the seven items the 18 November session left for the owner; that session predates them.

## A. The 14 answers, re-checked

| Q | Status | What changed, with reference |
| --- | --- | --- |
| 1 Studio's share | Still true | The Model tab is still the placeholder (`C apps/workspace/src/ingest/studio/ModelTab.tsx:1-20`). Root rule now at `C services/ingest/pipeline.py:104-110` (was 103-108). No model version is pinned at publish (`C services/api/app.py:13987-14003`). No Drawn kind in the switcher (`C apps/workspace/src/ingest/studio/datasets.ts:8-11`). Owner step built (`app.py:11868`, `:12039`). Root removal is decided: ADR-140 R3 (`B spec/06_DECISIONS.md:25157`). |
| 2 A new entity type | Still true | `ModelExtension` unchanged (`C packages/schemas/dataset_model.py:36-50`). Entity-type extensions are not composed (`C services/api/link_types.py:297` reads link types only). Decided, not built: Amendment 22 items 3 and 4 (`B spec/06_DECISIONS.md:41391-41395`); X7 (`:41149`). |
| 3 The classes | Still true | Five `PoleClass` values (`C packages/schemas/domain.py:56-74`). Amendment 22 item 3 (`:41391-41394`) fixes the five classes. |
| 4 Matching on a type | Still true | `match_on` must name an identifier or an indexed property (`C services/ingest/recipe_rules.py:247-264`). Decided: "the matching rule lives on the type record" (`B process/lanes/v062/RULINGS.md:331`). |
| 5 The pipeline as a graph | Still true, narrower | The staging container is dropped (Amendment 22 item 5). The root rule is still present (Q1). |
| 6 Staging containers | Still no | Amendment 22 item 5 (`spec/06_DECISIONS.md:41398`); `B spec/09_INGEST_STUDIO.md:23`. `TableKind` has no container (`C services/ingest/staging_catalogue.py:72`). |
| 7 Order between pipelines | Decided in part; code not re-checked | A failure stops dependents; the suggestion is shown, not enforced (ADR-141 Amendment 2 item 2, `:41420-41424`). The order is stored with the dataset (item 6, `:41435-41436`). The scout did not check for a stored-order field. |
| 8 An item not found | Still true | A miss creates a node (`C services/ingest/engine.py:1588-1613`). Two `on_match` values only (`C packages/schemas/ingest.py:692`). Decided, not built: X4 (`:41146`); Amendment 22 item 6 (`:41399-41401`). |
| 9 Load now | Still true | A non-deployed run is refused (`C services/api/studio_publish.py:799-800`); the assert at `:240` is unchanged. "Deploy and run now" at `C apps/workspace/src/ingest/publish/PublishScreen.tsx:487`. Decided: Amendment 22 item 7 (`:41402-41403`). |
| 10 The catalogue | Still true | Eight step kinds (`C packages/schemas/staging.py:74, 90, 129, 220, 267, 276, 290, 352`). Tooltip text not re-read. |
| 11 Preview | Still true; **conflicts with the decision** | Previews are 10 rows (`NodePreview.tsx:29`; `C services/api/studio_staging.py:71`). Whole-file reads: `studio_profile.py:195-201`, `studio_staging.py:245-247`, `studio_map.py:173-177`. ADR-140 Amendment 12 item 5 says a step's sample reads "each source's first ten rows" (`:29341`); the code reads all, then slices. |
| 12 Reference lists | Still true | Import is refused unless the live model names the list (`C services/api/list_connector.py:826-829`; `app.py:11069`). Decided: lists are created without Make live (Amendment 22 item 4, `:41395-41397`); X6 not built (`:41148`). |
| 13 Releases | Still true | The Releases words at `ReleasesTab.tsx:34` point to the placeholder. The words match the decided Model step; no change needed. |
| 14 CARRIES row 210 | **Changed** | The creator check is now in both stores: helper at `C services/api/target_models.py:92-112`, called at `:286, :304, :477, :520`. PUT and DELETE docstrings say so (`app.py:11797-11801`, `:11815-11816`). **No version on PUT** (`app.py:11802`); DELETE passes the version it has just read (`:11817-11820`), so it guards nothing stale. Decided: X5 (`:41147`). SE3 is merged (`7285411`; the scout could not confirm this, the conductor did). |

## B. The seven decisions the 18 November session left for the owner (MORNING.md items 12 to 18)

| # | Decided or open | Options and code cost | The scout's lean |
| --- | --- | --- | --- |
| 12 What a type record carries | **Decided in part.** Per dataset: Amendment 22 item 4 (`:41395`). Class, identifiers, matching rule: item 3 (`:41392-41394`). **Open: properties, pattern, resolution.** | (a) Class, identifiers, rule: three fields on `dataset_model.py:36-58`, TypeScript regenerated. (b) Add properties with an indexed flag (`recipe_rules.py:253` already accepts indexed properties, so matching needs this). (c) Add a resolution block copied from `domain.py:127-134`. | (b): option (a) leaves a type matchable only on its identifiers |
| 13 "Use it only" | **Decided: hold, not skip or report** (X4; Amendment 22 item 6). **Open: the label only.** | (a) A third option "use it only" in `ElementInspector.tsx:385-394`, a hold branch at `engine.py:1588` and the held-rows store (`C services/api/held_rows.py`). (b) Keep the two labels. | (a): the decided behaviour is a hold and the label should say so |
| 14 Load now | **Decided:** "Load now is Deploy and run now" (Amendment 22 item 7). Nothing open. | None; built at `PublishScreen.tsx:487`. The never-deployed staged path still asserts at `studio_publish.py:240` (a run is needed). | none needed |
| 15 The staging container | **Decided: dropped** (Amendment 22 item 5; `spec/09_INGEST_STUDIO.md:23`). Nothing open. | Restoring it would need an amendment. | drop it from E |
| 16 "Runs after" | **Decided in part.** Set order enforced on failure; the suggestion shown only (ADR-141 Amendment 2 item 2); stored with the dataset (item 6). IS3 shows no column until IS6 (`slices/IS3.md:7`, owner, 21 November). **Open: the record's shape.** | (a) An ordered list on the dataset's model record (`dataset_model.py`), exported with the release (`C services/ingest/release.py:221`). (b) A separate dataset run-order store: new route and table. (c) Per-pipeline "depends on": contradicts item 6. | (a): item 6 wants it versioned and exported, which the model already is |
| 17 Preview sampling | **Open, but the decision text already says "first ten rows"** (Amendment 12 item 5); **the code conflicts with it.** | (a) One bounded reader (first N rows, stop reading) at the three call sites in Q11, and one call from `NodePreview.tsx:73-79`. (b) Whole read, cached by file hash: needs invalidation and memory limits. (c) Record it as a known limit. The owner's choice of N for Preview. | (a): a conformance fix to a decision already made |
| 18 Row 210 (C186) | **Decided:** creator and version (X5; the SE3 brief). Creator half is on main. **Open: the expected version on PUT and DELETE.** | SE3 says not to change `TargetModelDraftInput` (`slices/SE3.md:33-35`). (a) Version as a request header on PUT and DELETE: route signature and a Glass send. (b) Leave it owed (accepted: `SE3.md:72-75`; `BACKLOG.md:223-227`), and IS2's first save has no stale check. | (a), before IS2 saves |

## C. Where today's main would mislead a builder

1. **Route numbers moved 11 to 40 lines.** Current (`C services/api/app.py`): draft GET, POST, PUT, DELETE at 11766, 11776, 11789, 11807; impact 11843; make-live 11852; proposals 11930; run 14185; preview-graph 13765; staging-preview 13543; reference-list import 11033 (offered 11011); release export and import 12166 and 12214; publish build 13987. The old citations (11753, 11769, 14099, 13894) are wrong.
2. The DELETE route supplies its own version (`app.py:11817-11820`), so it guards nothing stale.
3. PUT carries no version (`app.py:11789-11802`; `dataset_model.py:83-90`).
4. `ModelTab.tsx:1-20` is still the placeholder, fed the case's packs (`IngestStudio.tsx:209`). IS2 replaces it.
5. `ModelExtension` has no class, identifiers, properties or resolution (`dataset_model.py:36-50`).
6. There is no ontology composition for entity types (`link_types.py:297`; `packs.py:140-151`).
7. The root rule is enforced at `pipeline.py:104-110`.
8. "Reference existing" writes a node on a miss (`engine.py:1588-1613`; `ElementInspector.tsx:391`).
9. A reference-list import is refused until the model is live (`list_connector.py:826-829`).
10. The switcher's type has no kind (`datasets.ts:8-11`): no Drawn badge.
11. **PL4d3d is not merged:** the case-client file `investigation/cases.ts` in the shared package's `src` folder (PL4d3d's move) is absent on main, but IS3's brief names it.

## D. Runs still needed (none run; each is a seat on the test stack under the lease, rule 14)

1. Owner step and creator check: make-live with no owners (expect 409 `owner_needed`); a second principal's PUT and DELETE (expect 409 `model_refused`, draft unchanged). The Postgres cases in `test_target_models_store.py` are owed by SE3.
2. Q2: PUT an entity type "Vessel", read the impact, make live, confirm `/v1/ontology` lacks it, and test a row template that writes it (predicted refusal at `adapter.py:353`).
3. Q9: POST a run for a never-deployed staged draft; record 409 or 500 at `studio_publish.py:240`.
4. Q11: time a Preview (10 GETs), one staging-sample POST and one preview-graph POST on a synthetic 1-million-row CSV and a client-size file; record peak memory and `find_node` calls.
5. Q5 and Q7: open the 19 seeded pipelines and re-test each; load `pid_nomis_cell_stays` before R1 and R11 to see the effect.
6. Q12: import a reference list into an unmade-live draft (expect refusal), then make live and import.
7. Q13 (browser): import a release and confirm the Model tab shows no draft.
8. Q8 (optional): a miss under dry run and under load, to show it is created.

## What the scout could not read

No git (so no merge status; the conductor confirmed SE3 and found PL4d3d unmerged); the Glass callers of the model routes (not re-grepped); `pipeline.py:39-72` (the v1 chain); the Postgres store beyond `target_models.py:464-477`; `ReleasesTab.test.tsx`.
