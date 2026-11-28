# Slice GG4i1 · GG4 · The query builder as a GOV.UK page, scripts off: draw a pattern by forms, see its count first, run it, see the set it found, and add it to the case's graph (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M.** The first of GG4i's four parts (by function: GG4i1 the query builder, GG4i2 metrics, GG4i3 match strictness
and explain, GG4i4 cross-filter). Release A-full (D273): in 0.7.0.

**Where it comes from.** The `query-builder` row of `FUNCTIONS.yaml` (`apps/pages/FUNCTIONS.yaml:276-282`: "Query
builder, metrics, match strictness and explain, cross-filter", scenarios A3, A7, A8, A12, B9, B10, B19). **This part
takes B19** (`spec/08_ACCEPTANCE_SCENARIOS.md:570`: "Expand to common contacts across the two principal endpoints …
The intersection set is returned, with the estimated count shown before running"). ADR-030 (patterns drawn, never
typed), ADR-121 (conditions), ADR-032/036/040 (saved patterns, owner-only). The plan's row: GG4i needs GG2f and GG3
(`drafts_2026-11-26/CHAIN_PLAN.md:87`).

**This part draws nothing with Sigma.** The pattern is drawn as a list and a table, not a canvas. So decision 9's first
sentence does not hold it; its "the rest of R4 … waits to merge" does not name GG4 either. It merges after GG2f1 (the
add, below), which itself waits for WS4b, so **in practice it merges after WS4b** unless the owner allows the add to be
left out until then (question 7).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The routes** (`services/api/app.py`), each `require_right(INVESTIGATE)` and the case's gate:
  - `POST .../patterns/preview` (`patterns_preview_route`, :7157-7177), Viewer: `check_pattern_conditions`, then
    `preview_pattern` (`services/api/patterns.py:89-93`): the principal-filtered `match_count` up to
    `PREVIEW_COUNT_CEILING` (10,000, :42), answered as `PatternPreview` (`estimated_count`, `is_floor`, :51-58). Audited
    `patterns_preview`.
  - `POST .../patterns/run` (:7180-7201), Viewer: `run_pattern` (`patterns.py:96-121`) counts first, and **below
    `pattern.limit` answers `mode: "sync"` with the whole `Subgraph`**; at or above it, `mode: "job"` with a `job_id`
    and no subgraph (`PatternRunAccepted`, :77-86). The job re-runs at `PATTERN_MATCH_JOB_CEILING` (100,000, :48).
  - `POST .../patterns/save` (:7251-7284), **Editor** (`InvestigationEditorDep`, :7257): 201 `SavedPattern`; a
    `pattern_id` not the caller's is 404 `pattern_not_found` (`_pattern_not_found_handler`, :3366-3370).
  - `GET .../patterns` (:7287-7298) and `GET .../patterns/{pattern_id}` (:7301-7312), Viewer: the caller's own only,
    filtered in the query ("Saved patterns are private to the principal who saved them", `spec/03_CONDUIT_MIDDLEWARE.md:581` onward).
  - `POST .../patterns/ask` (:7204-7241) needs `ASK_MODEL` (:7206). **Not in this part** (question 8).
- **The pattern** (`packages/schemas/domain.py:780-823`): `PatternNode` (`var`, `entity_type`, `node_id` to pin a node,
  `where` of at most `PATTERN_WHERE_MAX` = 3 equality conditions, :777, :799-808), `PatternEdge` (`edge_type`,
  `from_var`, `to_var`), `PatternQuery` (`limit` default 1,000). "Never free-form Gremlin (ADR-003)" (:818-819).
- **The refusals.** A condition the ontology does not allow: 422 `pattern_condition_refused` with `var`, `property`,
  `reason` (`app.py:4123-4140`), the reasons `no_type`, `unknown_type`, `unknown_property`, `sensitive`, `not_indexed`,
  `unsupported_type` (`packages/ontology/pattern_where.py:62-90`). **A pattern with an unpinned second root is not
  refused by the route: the adapter raises a bare `ValueError`** (`packages/adapters/graph_arcadedb/builders.py:929-935`),
  and no `ValueError` handler exists in `app.py`, so the caller gets a 500. Its words name ArcadeDB and Gremlin; a 500
  sends none of them, but a page must never reach it (rule 7). The React builder prevents it in the browser:
  `unpinnedSecondaryRoots` (`apps/workspace/src/patterns/store.ts:188-197`) mirrors `MatchBuilder._render_matched`
  (`builders.py:900`) "on purpose" (:6-11).
- **The choices** come from `GET /v1/ontology` (`app.py:9323`): entity types, edge types, and each property's `indexed`,
  `sensitivity` and `type`, from which `conditionableProperties` (`store.ts:114-119`) offers what may carry a condition.
- **The fetch client is already shared**: `packages/glass-shared/src/patterns/api.ts` (`fetchPatternPreview` :69 and its
  siblings, imported by the React panel at `QueryBuilderPanel.tsx:37-47`). **The pattern logic is not**: `store.ts` is in
  `apps/workspace` (239 lines, no React).
- **A run returns items and no links.** `match()` answers `Subgraph(nodes=…, edges=[])` always
  (`packages/adapters/graph_arcadedb/adapter.py:1318-1324`), so a pattern's links are never sent, though its edges were
  matched. **A Conduit finding for the orchestrator**; this page shows items only.
- **What a run counts.** The count and the run take the same distinct union of every variable the primary chain binds
  (`_nodes_tail` and `_count_tail`, `builders.py:871-897`). On the pinned path the primary root is the first unpinned
  root, or `roots[0]` when every root is pinned (:926), and its chain's variables are returned
  (`_nodes_tail(sorted(primary_bound))`, :1030); a pinned *secondary* root is never returned (:1023-1024). So for B19's
  shape (two pinned Endpoints `a`, `b`, an open `contact`) the answer is `a` and the contacts: **the first pinned
  Endpoint is counted and returned with them.**
- **The React panel never shows what a run found.** `handleRun` stores the answer (`QueryBuilderPanel.tsx:265-271`) and the
  panel shows "`{matched_count}` node(s) matched" or "Large result — running as job `{job_id}`" (:478-481), nothing more;
  the `subgraph` is not drawn, listed or put on the canvas. B19's row says "the intersection set is returned": the route
  returns it, and no Glass shows it. **A finding for the orchestrator** (the React side is not this part's to change).
- **A job's result has no read route.** `spec/03_CONDUIT_MIDDLEWARE.md:550` lists `GET /v1/jobs/{id}/events` ("SSE
  progress stream") and `patterns.py:79` tells a caller to poll it; **no such route is in `app.py`** (the only job read is
  `GET /v1/resolution/jobs/{job_id}`, :9249-9262, for matching jobs, carrying no result). So a run at or above the
  pattern's `limit` is accepted and its answer is unreachable by any Glass. **A finding for the orchestrator (rule 11:
  `spec/03` names a route the Conduit does not serve)**, and question 4.
- **The keyboard ids** in `QUERY_BUILDER_ACTIONS` (`packages/glass-shared/src/keyboard/actionRegistry.ts:244-266`).
- **One page per row in a tree** (`apps/pages/server/pages.ts:133-142`), its path a plain path (:55, :116).

## Acceptance (red before, green after)

Scenario **PQ** (new; "pattern query"), written first in `spec/08`, with B19 as its last row run on the GOV.UK tree;
`apps/pages/test/govuk/patterns.test.ts` red on main, green after. B19's existing row and its over-the-wire test stay
green and unchanged.

## Questions for the owner (the proposal first)

1. **The address and the row.** (a) **`/cases/patterns?case=…`, the `query-builder` row's page**, GR1a's query form.
   GG4i2 to GG4i4 are panels of GG2e's graph page, not pages, so the row keeps one page and its `route` is set to this
   path only when GG4i4 merges (the row is the four functions). (b) Split the row into four rows, as GR4a's board page
   was given its own.
2. **Drawing without a canvas.** (a) **The pattern is a list of numbered parts, each a GOV.UK summary row ("a: a
   Person", "b: the Endpoint 'J. Ashdown's phone', pinned", "a is linked to b by CALLED"), with forms below: add a part by
   type; pin a found item; link two parts; add or remove a condition; remove a part.** Each form posts the whole pattern
   back in hidden fields and the page answers with the next state (`200`, nothing written, so no `303`: GG4c's
   post-then-`303` rule is for writes). (b) The pattern kept in the page service's session between steps (a store to
   clean up, and a back button that lies).
3. **Pinning a node.** (a) **A search step on the same page** (the person types words; the server half calls the same
   search route GG3a's page calls, `POST /v1/investigations/{id}/search` (`app.py:6684`), and lists the results, each with "Pin in the pattern"), the id
   carried in a hidden field or the address's query string, never in visible text (the one rule for ids across these
   drafts; GG4d question 5: "a form's hidden field or a link's own path, never in text"). (b) A link from GG3a's search
   results into this page.
4. **A large run.** (a) **The page counts first and never sends a run whose preview is at or above the pattern's
   `limit`:** it says "About N matches: too many to show here. Add a condition or pin a part" and offers the pattern's
   parts again. Nothing is cut (rule 2): the page shows a whole result or none. **(b) A Conduit read of a job's result
   (`spec/03:550` names only `GET /v1/jobs/{id}/events`, an SSE progress stream, which no route serves; a result read
   would be a new route), with its own access rule that only the principal who ran it may
   read it, is an amendment (decision 11) and a security part: owner.** Proposed: (a) now, and (b) raised to the owner
   as the finding above.
5. **The second root.** (a) **The server half runs the shared `unpinnedSecondaryRoots` before Preview or Run and says
   "Part c is not linked to the first part. Pin it to a known item, or link it to a part already in the pattern"**,
   naming the part, never the adapter; the route is not called. This needs `patterns/store.ts` moved to
   `packages/glass-shared` first, behaviour unchanged (I11, as GG2c moved the delta client), its unit tests with it.
   (b) Let the route answer 500 and say "could not be run". **Not proposed** (a 500 is not a refusal in words).
6. **What a run shows.** (a) **One table of the items found (label, type, marking), whole, with the count in the
   caption; the pinned item the route returns with them is marked "pinned" ("4 items: 3 found and the pinned
   Endpoint"); "None found" when only the pinned item comes back.** No links table: the route sends none (above). Labels are the node's own label
   property, as the React canvas labels (`nodeAttributes.ts`); no id is printed. (b) The count alone, as the React panel
   does today. **Not proposed**: B19 says the set is returned.
7. **Adding the set to the case's graph.** (a) **"Add these to the case's graph"**, offered to an Editor only, posting
   `POST .../working-set/add-by-ids` (`app.py:5688-5722`, Editor) with the ids shown (hidden fields), then a `303` back
   with a banner in GG2f1's words: what was added, the answer's `not_shown` said as a count ("2 could not be added: you
   may not see them, or they are no longer held", rule 3: the ids came from this reader's own answer), and a refusal past
   the cap with its three options in GG2f1's words (rule 2). (b) Leave the add out until GG2f1, so this part may merge
   before WS4b.
8. **Ask to search** (`ASK_MODEL`). (a) **A later part, GG4i1b, in 0.7.0**: it needs GA1b's long-post pattern (the
   model's bounds) and the engine choice. (b) In this part.
9. **Saved patterns.** (a) **Save (Editor), list and load (Viewer), the caller's own only**, as the routes are; "Saved as
   version 3"; no share control (ADR-040 is not accepted). *Save as a watch* is B20's and the watches' (not here).
   (b) Load only.
10. **Conditions.** (a) **The property list offers only `conditionableProperties` of the part's type; at most three**,
    and a refusal sent by hand (`pattern_condition_refused`) is said in the page's words for each `reason`, the person's
    value kept. (b) Every property, the route's refusal after.
11. **The estimate's words.** (a) **"About 42 items" for an exact count and "10,000 or more items" for a floor** (the route
    counts items, the pinned primary included, not matches)
    (`is_floor`), as `PatternPreview`'s docstring asks (`patterns.py:52-56`). (b) The React panel's "~42" and "10000+".

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | B19 on the GOV.UK tree: two pinned Endpoints, an open Endpoint linked to both by `COMMUNICATED_WITH` (B19's own shape, `OspreyFlow_Build/tests/scenarios/test_phase8_exit_criterion_end_to_end.py:1075-1085`), a synthetic world with three common contacts | Preview first: "About 4 items" (the three contacts and `a`, `_count_tail`'s union); Run: four rows, `a` marked pinned | the run sent before the preview is shown |
| 2 | A part added, a link drawn, a part removed | each step's summary rows; a removed part takes its links with it | `removeElement`'s link removal left out |
| 3 | A pattern with an unpinned second root (question 5) | the sentence naming the part; no route called | the check skipped and the 500 shown as "could not be run" |
| 4 | Preview at or above `limit` (question 4 (a)) | "too many to show here"; no run sent | the run sent and its `mode: "job"` shown as an empty result |
| 5 | `is_floor` true | "10,000 or more items" | the floor shown as an exact "About 10,000" |
| 6 | Two readers of different clearance, the same pattern | each preview and table counts and lists only what that reader may see | at the page's call site: the server half's preview answer cached by case and pattern, not by session, so the second reader is served the first's |
| 7 | A condition on a `sensitivity: high` property posted by hand | the `sensitive` sentence, the value kept | the 422's `detail` printed |
| 8 | A fourth condition posted by hand | refused by the page in words; nothing sent | the fourth sent (the route's 422 shown raw) |
| 9 | Add these to the case's graph, as an Editor, one id no longer held | one `add-by-ids` with exactly the ids shown; `303`; "1 could not be added" | the ids re-read from a second run |
| 10 | The add past the cap | the three options in GG2f1's words; nothing added | the 409 shown raw |
| 11 | A Viewer | no add and no save offered; a hand post refused as the route refuses it, said in words | the controls offered from the level alone, not from `GET /v1/me/rights` and the case level |
| 12 | Save, then load, then save again | "Saved as version 1", the loaded pattern drawn, "Saved as version 2" | a load that loses a pinned part's label |
| 13 | Another's pattern id posted by hand | the same 404 page as a missing case | 404 `pattern_not_found` said as "That pattern is someone else's" |
| 14 | No id in visible text (hidden fields and the query string only), no compiled query, no adapter word anywhere | none (rule 7) | a node id printed in the summary row |
| 15 | No `_csrf` on any post | refused, nothing sent (I17) | the builder's step posts outside the check |
| 16 | Keyboard | one case per `QUERY_BUILDER_ACTIONS` id this part offers, in `test/govuk/keyboard/`; the ask ids listed as GG4i1b's (rule 13) | an offered id with no case |
| 17 | Scripts off | the whole journey of case 1 (I4) | a step that needs a script |
| 18 | The moved `store.ts` | the React panel's whole suite green before and after (I11) | one function's behaviour changed in the move |

## Waits on

GR1a (merged); GG3a (the search the pin step calls); GG2f1 (the add's words and refusal; it merges after WS4b, so this
part does too unless question 7 (b)); the owner only if question 4 (b) is taken.

## Files touched

`spec/08` (PQ); `packages/glass-shared/src/patterns/store.ts` (moved from `apps/workspace/src/patterns/store.ts`, with
its tests; the React panel's import re-pointed); `apps/pages/server/patterns.ts` (new), `server/views/patternsWords.ts`,
`server/pageList.ts`; `tree-govuk/patterns.njk`, `tree-govuk/routes.yaml`; `FUNCTIONS.yaml` (only when GG4i4 merges:
question 1); `test/govuk/patterns.test.ts`, `patternsConduit.ts` (a fixture that counts and matches as the principal and
refuses as the route does, 500 included), `keyboard/patterns.spec.ts`, `scripts-off/patterns.spec.ts`;
`OspreyFlow_Build/tests/glass_trees/test_govuk_patterns_scenario.py` (the census over `PatternPreview`,
`PatternRunAccepted`, `SavedPattern`); `tests/harness/test_pages_setting.py`'s route list.

## Checks (frozen when cut)

GR1a's list, plus `apps/workspace`'s `patterns/` suite and `keyboard/query-builder.spec.ts` (unchanged and green after
the move).

## Out of scope

Ask to search (GG4i1b); watches and alerts from a pattern (B20); pattern sharing (ADR-040); a job's result (question
4 (b), owner); any Conduit change; the React panel's missing result (reported, not changed).
