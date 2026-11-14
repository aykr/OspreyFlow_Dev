# Step 5's sweep: what the code said

The docs lane, 14 November 2026, on `lane/docs-v052-sweep-early`, at the orchestrator's word: the parts of
`STEP5_CHECKLIST.md` that wait on neither the last features nor the cut, which are sections 3, 4, 7, 8 and 9. Checked
against main at 7ba248e. Each claim below was read in the code before the guide was changed, and each is held by a
test that reads that code. The red-first runs are in `process/lanes/docs/gates/v052-sweep-early-red-first.txt`.
Paths are relative to `OspreyFlow_Core/`.

## 3. Navigation outside the user guide

- **What is on the rail, and what is a view:** `apps/workspace/src/shell/railLayout.ts`. `ON_THE_RAIL` is explore,
  questions and history. `VIEW_SWITCH` is graph, map, boards and dashboards (labelled *Reports*). `MORE_VIEWS` is
  matrix, reports (*Figures*), ownership and strength. `RAIL_LABELS.questions` is "Ask & Chat".
  - The administration guide put Dashboards (§12) and Connection strength (§9.6) on the rail. They are views.
- **"Ask the case":** in no screen's words. It is only in a comment, `models/engines.tsx:1`. On screen the panel is
  *Ask & Chat*. *Ask to search* is still the query builder's own control (`patterns/QueryBuilderPanel.tsx:328`).
- **Admin's sections:** `apps/workspace/src/admin/sections.json` labels them. The guide's *Schedules and runs* is
  *Operations* (`admin/Schedules.tsx:1`: "formerly Schedules and runs"), *People* is *People and roles*, and
  *Dashboards* is *Dashboard identities*.
- **Left as the code words them, for its lane:**
  - The Conduit's refusals say "Admin › People", as administration guide §6a.7 quotes them: the guest refusal
    (`packages/principal_auth/__init__.py:549`, "an administrator can admit them in Admin › People") and the
    owner refusal ("is not a person Admin › People holds": `services/api/scheduler.py:672`, `list_schedule.py:85`,
    `rule_schedule.py:335`, `watch_status.py:26`).
  - `packages/schemas/deployment.py`'s description of `cloud_platform.claims.clearance` says "set in Admin › People".
    It is generated into Appendix A.
  - All three should name *People and roles*. The guide follows when the code changes. The test leaves quotations
    and the generated appendix to the code.
- **The sites:** ospreyflow.org's Home and Features said "**Questions.**", and the figure's caption said "Questions:
  …". They now say "Ask & Chat".
  - Figure captions are now HTML-escaped, as their alternative text always was.
  - The screenshot itself is replaced with item 6.

## 4. Search

- **`IndexFeedSource`** is `packages/ports/index_feed.py`. It is a `Protocol` apart from `GraphPort`, through which
  the indexer alone reads each node as stored, unfiltered, "so that no route, which is given a `GraphPort`, can reach
  the unfiltered read". Access is applied in the query to the index, `services/api/search_access.py`'s
  `index_access_filter`: classification against clearance, handling code, and the case's datasets.
  - The administration guide's tier section named two narrower ports too; it now names three. `spec/00_ARCHITECTURE.md`
    still says "Two narrower ports" (line 601): carried for the spec's owner (rule 11).
  - The ports are `GraphPort`, `AnalyticsPort`, `ComputePort` and `ModelPort`, with `MediaStore`, `RecognisePort` and
    `IndexFeedSource` beside them. `BulkGraphLoader` is GraphPort's own bulk path, in `ports/graph.py`.
- **"PostgreSQL full-text" is not built.**
  - `SearchBackend.POSTGRES_FULLTEXT` (`packages/schemas/deployment.py:111`) only drops OpenSearch from the render.
  - No `to_tsvector` or `tsquery` exists in `services/` or `packages/adapters/`.
  - Without an index, search is the graph store's exact search (`services/api/search.py`'s `search`, through
    `graph.search_nodes`). The page then says "Search is limited to exact identifiers: this deployment has no search
    index." (`search_service.py`'s `LIMITED_REASONS["no_index"]`).
  - The architecture guide, the administration guide's tier table, Features' Vault card and the overview's Vault
    chip now say so; the lane review found the last three still saying "or PostgreSQL" for search.
  - **For the platform lane:** `harness/render.py:1826-1827` writes into the rendered `INSTALL.md` that "full-text falls
    back to PostgreSQL", and so does `spec/05_DEPLOYMENT.md` §3's reduced variant. Neither is built.
- **The suggestions box** (`apps/workspace/src/search/`):
  - `SearchFilters.tsx` labels the filters Ignore case; Match, with Starts with, Contains and Exact; Entity types,
    with "None ticked searches every type."; Only nodes on screen; and Reset filters.
  - `GlobalSearch.tsx`:
    - `SUGGEST_MIN_CHARS` is 2;
    - the more line is "Showing the first ${results.length}; more match. Keep typing to narrow.";
    - `LIMITED_SUGGESTIONS` is shown only when the Conduit answers `limited` (`services/api/search.py`'s
      `SuggestResponse.limited`).
  - The 50-character limit **is** in the code, where there is an index: `services/search_index/mapping.py`'s
    `PREFIX_MAX_CHARS = 50`, refused by `search_index_query.py` ("a suggestion is at most 50 characters", a 422), and
    the box shows a refusal as "Suggestions are unavailable." (`GlobalSearch.tsx`'s `!response.ok`). This file's
    first draft said otherwise, from `SuggestRequest.query`'s minimum length alone; the lane review found it.
  - *Only nodes on screen* starts at one character, and asks the Conduit nothing (`GlobalSearch.tsx`'s
    `onScreenOnly`).
  - The limited line is for a *Starts with* search alone: `search_service.py`'s `suggest` sets `limited` only for
    `request.mode == "starts_with"`; *Contains* and *Exact* always read the graph.
- **`opensearch_signing`** is `harness/cloud_platform/settings.py`'s `PlatformSettings.opensearch_signing`,
  `Literal["sigv4", "none"]`, `sigv4` by default.
  - `harness/cloud_platform/runbooks.py`'s `_opensearch_needs` words it in the rendered `INSTALL.md`: "no
    fine-grained access control, so there is no user or master password to keep"; with `none`, the platform's proxy
    signs.
  - `services/search_index/client.py` reads `OPENSEARCH_SIGNING`.
- **What replaces FGAC has four parts**, not three: `index_access_filter` builds `classification`, `handling_code`,
  `datasets` and `text_unit` (a Document's text only for the unit that holds it). It is given to the results page's
  search, the box's suggestions and *Whole case*'s search (`search_route`, `suggest_route`, `case_search_with`).
- **§6a.11's question 13**, an IAM-only OpenSearch access policy without fine-grained access control: a ruling,
  brought to the orchestrator with a recommendation and approved on 14 November with one addition, to name where each
  reader's access is applied instead (`search_access.py`'s `index_access_filter`, given to every search by the route,
  `access_filter=index_access_filter(index.scheme, principal)`). CARRIES: platform builds FGAC if the client's
  standard requires it, open until the client answers.

## 7. Built since it was called "coming"

- **A drawn dataset merged into another** is built: `services/api/drawn_merge.py` (ADR-143 Amendment 2 decisions 6
  and 7, Amendment 3, Amendment 7), its routes in `services/api/app.py` (`merge_datasets` on every route), and the
  Studio's screen `apps/workspace/src/ingest/runs/drawnMerge.tsx`.
  - The screen is *Merge into a dataset…* in 4 Runs. Its steps are headed "1. Map the models", "2. Match" and "3. Dry
    run", then "4. Merge", or "4. Send for review" unless the target's policy is `author_promotes`.
  - Matches are written as scored, `inferred` `SAME_AS`, with nothing collapsed in storage.
  - After the merge, the home case reads the target and the drawn dataset read-only, the boards become views, and
    annotations are read through each reader's handling.
  - A keyboard harness exists for it (`keyboard/drawn-merge-harness.tsx`).
  - The developer guide §7.8 and the architecture guide §5 said "**Coming:**". They now describe it as built.
- **The writers that read in full** are every module in `services/` that enters `sources_in_full()`
  (`packages/ontology/handling.py:321`). There are nine: `alert_queue`, `case_gazetteers`, `drawn_merge`,
  `entity_pictures`, `grading`, `link_changes`, `pipeline_run`, `extract/writer` and `resolve/trigger`, and outside
  the Conduit `scripts/build_local_basemap.py` (a gazetteer's load). The guide named six.
- **"How lists raise alerts is rewritten with the alerts journey (coming)":** no such rewrite is planned in the code.
  A list raises alerts through a rule on a screening list, and when it changes (user guide §7.4 to §7.6 and §7.10),
  so the line now points there.

## 8. What v0.5.1 shipped that the guides had not said

- **A refresh** (ADR-050 Amendment 3):
  - `App.tsx`'s `signInAtLoad` asks `renewSilently` first, and shows the screen only when the identity provider says
    no.
  - `auth/refreshPlace.ts` keeps the place (home, case, admin, studio, rules) in `sessionStorage`. A place the rights
    do not offer is kept as Home (`placeOnScreen`). Of the Glass's views only `RESTORED_GLASS_VIEWS`, the graph, the
    map, the Matrix and Figures, are put back; on any other a refresh opens the Glass's first view (the lane review).
  - `auth/userManager.ts`'s `signOut` calls `forgetPlace`.
- **GOV.UK's slim top** (ADR-132 Amendment 8):
  - `brand/BrandFrame.tsx` draws the header and phase banner `brand-chrome--compact` unless a screen claims the full
    frame. Only `home/HomePage.tsx` and `auth/SignInScreen.tsx` do.
  - `shell/ContextBanner.tsx` folds the GOV.UK notification banner into one row.
- **The profile:** `cli/ospreyflow/deployments.py`'s `PROFILE_NAMES` includes `cloud-platform`.
  - The administration guide §6a.1's *Moving to a new release (poc shape)* is the only upgrade path written. §6a.10
    lists the standard shape's runbooks as coming.
  - Whether `ospreyflow update` refuses a cloud-platform deployment was not found in `harness/update.py`, so §14's
    row says neither way.

## 9. §9's refusals both ways

- `services/api/entra_people.py`'s `_refused(...)` arguments are the refusals, an f-string's among them, read with
  each value it fills in as "…": "Here … come from Entra ID, and are changed there." (`check_administrator_access`,
  a value Entra sends, given under the administrator fallback). The first check read plain strings alone and could not
  see it; it was in no guide, and §9 now quotes it.
- §9's one sentence ("What Entra holds is refused here, in words, …") now lists only those, and the words each opens
  with ("On this deployment Entra ID holds people's accounts…") are the code's. A refusal the code drops turns the
  test red, as the dashboard identity's did after the code stopped raising it.

## After the lane review

The review's findings, all taken:
- the false search and port claims left in the administration guide and the sites;
- the suggestion limits;
- what a refresh keeps;
- question 13's fourth part;
- tests holding a docstring or a comment instead of the code: the merge's right, its `INFERRED` matches and
  `merge_boards`; the filter's parts; `placeOnScreen`;
- §9's f-string refusal;
- §9.6's Administrator;
- who may merge, the drawing's home case and its unit;
- the cloud-platform images;
- the tenth writer;
- §7.10;
- the figure's caption and the generated pages read by the navigation test.

Left as they are:
- *Whole case* in the administration guide's two "Ask & Chat" lines: the engine answers every Read from choice, not
  only *Whole case*.
- The tests' copied `fold` and `guide` helpers.

**Its re-check** found the record's plant results printed as `{summary}` (a string the script failed to format), §9
contradicting itself on the administrator fallback, and three weaker checks (the match's own link, the sites' search
phrases, and the fallback). All are fixed, the record is taken again, and the f-string refusal's field names are carried
for admin.

## The whole sweep, after the freeze (the orchestrator's word, 14 November)

### 1. The freeze's last features

- **3f and 3f′, the batch job**, were written by their own lane: user guide 1.60, `test_user_guide_batch_expansion.py`.
- **3g, the administrator fallback**, was written by its own lane: administration guide 2.06. §9's "No administrator
  can give a missing clearance or unit" is now qualified by it (the re-check's finding B).
- **U, the index rebuilt on install, update and restore** (ADR-150 Amendment 2, merge 022bb57):
  - `harness/search_rebuild.py`'s `renders_opensearch` and `rebuild_argv`, called by `harness/apply.py`'s step 4d
    (after the start, before the seed: a failed rebuild fails the install) and by `harness/update.py` (or the update
    fails and is rolled back);
  - the cloud-platform `INSTALL.md`, `runbooks.py`'s `_SEARCH_REBUILD`, appended to the rollouts wherever the values
    carry `searchIndex`: a Job from `cronjob/ospreyflow-search-rebuild`, five minutes to start and 30 to finish,
    deleted and named if it does not.
  - The same merge made `INSTALL.md` count its Entra registrations, `2 + superset + sync`
    (`entra_registrations`), so §6a.11's question 11 said two where there may be four.
- **3h, clusters on entry** (ADR-124 Amendment 19, merge 041533f):
  - `services/api/working_set/service.py`'s `_reader_clusters`, sent as `resolution_on_entry` on a seed's or an
    expansion's own answer;
  - `_without_cluster` on every shared read;
  - another reader's threshold reaches a canvas at its next sync or expand.
  - User guide §5.2 now says so.
- **The install test's date**: §6a.1 said 25 November, but the route gives step 6 as 16 November (main's
  `route.tsv`). The test reads the route, so it is red on a branch whose `route.tsv` is older, and green once
  rebased.
- **ADR-124 Amendment 20** (`edges_among` in chunks): reserved, not merged when this was written. It goes in when it
  lands.

### 5. The D-items and R7

- **D5:** `python -m harness.cloud_platform.manifest tables` exists and prints the poc tables from
  `poc_manifest.yaml`.
  - §6a.2 now carries that output between `manifest:begin` and `manifest:end`, put in by
    `python -m tests.test_guide_poc_manifest --write` and held to it byte for byte.
  - The per-shape table stays, held by the sizing tests: the manifest covers the poc shape alone.
- **D7:** waits for step 6 (the install test).
- **D1 to D4:** done. **D6:** 4b and 4c done; 4d is not ruled. **D8:** done in part (AG 2.00); the rest is part 4's.
- **R7:** step 1 is built. `GlassCanvas.tsx`'s *Mark for suppression* and *Remove suppression mark*; marks in their
  own table, never a graph write (`services/api/suppression.py`); listed in Explore with who, when and why.
  - Step 2, the suppression taking effect through ingest, is not built: nothing in `services/ingest` suppresses.
  - User guide §5.2 says so. The ruling's three questions went to the orchestrator for the owner.

### After the third review (14 November, evening)

Fixed:
- R7's paragraph said "with your reason" and that *Remove suppression mark* takes the mark off. The canvas sends
  "Marked from the canvas" and asks for no reason, and its marks are its own session's (`suppressionMarks` starts
  empty and is never read back), so after a reload the menu offers the mark again. The guide now says what is
  built; spec 02 §9.5 and ADR-046 say the marker is not built, and CARRIES carries both for the case lane.
- Case-b's line for the menu's new label ("Mark for suppression (hides nothing yet)", on main since its merge) is
  folded into the same paragraph, held to the label as the code gives it.
- 3h's "follows the next time you expand it": only a snapshot (a reload) brings every cluster; an expansion brings
  those its new records touch.
- `start --build` does not rebuild the index (`scripts/refresh.py`): §14's row says how to, and CARRIES has it for
  platform.
- 3f′'s limits: the Editor level, the expand right, the progress words and the ten minutes.
- The install's order (the demo accounts before the rebuild).
- The Job's failure.
- The manifest tables' reporting.
- The install test's date, with "route step 6", out of the guide.
- After main's suggest-fixes (ADR-059 Amendment 2), §5.5's limited line gives its reason, and a 422 is shown in the
  Conduit's words ("a suggestion is at most 50 characters"); K, the results page's per-group line, is in §5.5.
- The tests read code, not comments: the Job's `seq 60` × `sleep 5`, the add path's `_reader_clusters`, the store's
  table and its one graph read, update's `try` that rolls back, and `INSTALL.md`'s use of `entra_registrations`.

Left: the administration guide has no section on what the job worker runs, where batch expansions would be named.
