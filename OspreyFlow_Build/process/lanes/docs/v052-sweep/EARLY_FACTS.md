# Step 5's sweep, the early part: what the code said

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
  - The ports are `GraphPort`, `AnalyticsPort`, `ComputePort` and `ModelPort`, with `MediaStore`, `RecognisePort` and
    `IndexFeedSource` beside them. `BulkGraphLoader` is GraphPort's own bulk path, in `ports/graph.py`.
- **"PostgreSQL full-text" is not built.**
  - `SearchBackend.POSTGRES_FULLTEXT` (`packages/schemas/deployment.py:111`) only drops OpenSearch from the render.
  - No `to_tsvector` or `tsquery` exists in `services/` or `packages/adapters/`.
  - Without an index, search is the graph store's exact search (`services/api/search.py`'s `search`, through
    `graph.search_nodes`). The page then says "Search is limited to exact identifiers: this deployment has no search
    index." (`search_service.py`'s `LIMITED_REASONS["no_index"]`).
  - The architecture guide now says so.
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
  - The survey's "50-character limit" is not in the code. `SuggestRequest.query` has a minimum length alone, so the
    guide gives none.
- **`opensearch_signing`** is `harness/cloud_platform/settings.py`'s `PlatformSettings.opensearch_signing`,
  `Literal["sigv4", "none"]`, `sigv4` by default.
  - `harness/cloud_platform/runbooks.py`'s `_opensearch_needs` words it in the rendered `INSTALL.md`: "no
    fine-grained access control, so there is no user or master password to keep"; with `none`, the platform's proxy
    signs.
  - `services/search_index/client.py` reads `OPENSEARCH_SIGNING`.
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
  `entity_pictures`, `grading`, `link_changes`, `pipeline_run`, `extract/writer` and `resolve/trigger`. The guide
  named six.
- **"How lists raise alerts is rewritten with the alerts journey (coming)":** no such rewrite is planned in the code.
  A list raises alerts through a rule on a screening list (user guide §7.4 to §7.6), so the line now points there.

## 8. What v0.5.1 shipped that the guides had not said

- **A refresh** (ADR-050 Amendment 3):
  - `App.tsx`'s `signInAtLoad` asks `renewSilently` first, and shows the screen only when the identity provider says
    no.
  - `auth/refreshPlace.ts` keeps the place (home, case, admin, studio, rules) in `sessionStorage`. A place the rights
    do not offer is kept as Home.
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

- `services/api/entra_people.py`'s `_refused(...)` literals are the refusals.
- §9's one sentence ("What Entra holds is refused here, in words, …") now lists only those, and the words each opens
  with ("On this deployment Entra ID holds people's accounts…") are the code's. A refusal the code drops turns the
  test red, as the dashboard identity's did after the code stopped raising it.
