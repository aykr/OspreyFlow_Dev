# Slice GG4i2 · GG4 · Metrics on the case's live graph page: rank what is in view by a network metric, compare two, and find the relay group by the Clique Metric (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M.** The second of GG4i's four parts. **It is a panel of GG2e's live graph page and it focuses the Sigma canvas,
so by decision 9 it may be written meanwhile but merges only after WS4b** (`spec/06_DECISIONS.md` about lines 41091 to
41102; the owner's one exception is GG2c).

**Where it comes from.** The `query-builder` row (`apps/pages/FUNCTIONS.yaml:276-282`). **This part takes A8 and A12**
(`spec/08_ACCEPTANCE_SCENARIOS.md:389`: "Rank the resulting people by appearance count and group affiliation … The
principal subject ranks first; the affiliated subset is identifiable by an `Organisation` edge"; :393: "Run the Clique
Metric on the working set … The relay group passing items between cells scores high on clique and low on degree
centrality"). ADR-029 (`ComputePort`), ADR-139 decision 6 (strength and rarity as metrics). PL8b's side column holds a
`metrics` panel (`drafts_2026-11-26/PL8b.md`: `panelOrder.ts:14`'s four ids).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The route.** `POST /v1/investigations/{id}/compute/{metric}` (`services/api/app.py:6083-6115`):
  **`require_right(RUN_ANALYSIS)`** (:6085, re-verified), the case's **Viewer** gate (`InvestigationViewerDep`, :6088).
  `{metric}` is `ComputeMetricName` (`services/api/compute_routes.py:81`): `degree`, `weighted_degree`, `betweenness`,
  `eigenvector`, `pagerank`, `clustering_coefficient`, `communities`, `clique_metric`. Body `ComputeMetricRequest`
  (`k_min` 4, `k_max` 30, read by `clique_metric` alone, :97-102). Answer `ComputeMetricAccepted` (:105-116): `values`
  (node id to a number) or `communities`, or `mode: "job"` with a `job_id`. Audited `compute_{metric}`.
- **Rule 3 is the route's.** The working set's membership is "deliberately unfiltered", so the route narrows it with
  `narrow_to_visible` before computing (`compute_routes.py:13-25`, `_build_visible_subgraph` :144-150), "so a hidden
  node's own existence [cannot] leak through a visible node's own degree or centrality score". Proven by
  `tests/services/api/working_set/test_compute_access_control.py`.
- **The sync and job split.** Below `SYNC_NODE_LIMIT` (20,000, :79) the values come back; at or above it, a job
  (:166-179). **No route reads a job's result** (`GET /v1/jobs/{id}/events` is in `spec/03_CONDUIT_MIDDLEWARE.md:550`
  and :593 and not in `app.py`; GG4i1's finding). The React panel reads only `values` (`MetricsPanel.tsx:71-72`), so
  over 20,000 nodes it shows nothing and says nothing.
- **Strength and rarity** (ADR-139 decision 6): `POST .../connection-strength` (`app.py:16122`) and `POST .../rarity`
  (:16144), each `INVESTIGATE` and **Viewer**, over the working set narrowed to the reader (`spec/03` "Connection strength
  and rarity", :553 onward). The React panel offers both beside its seven (`MetricsPanel.tsx:31-43`).
- **The React panel** (`apps/workspace/src/metrics/MetricsPanel.tsx`, 402 lines) offers seven of the route's metrics
  (`communities` is not among them) and strength and rarity (`METRIC_OPTIONS`, :31-43); a primary metric ranks the list; a
  second one is shown beside it under "Compare" (:5-10); a row focuses the node on the canvas (:12-17). **It shows the top
  20 (`MAX_ROWS`, :78) with a bare `.slice(0, MAX_ROWS)` (:238-242) and no words saying so**, and a value for an id the
  canvas does not hold is labelled with the raw id (`rowLabel`, :102-106). Both are reported for the orchestrator (rule 2;
  rule 7), not changed here. Its keyboard ids are `METRICS_PANEL_ACTIONS`
  (`packages/glass-shared/src/keyboard/actionRegistry.ts:216-227`).
- **The fetch client is shared** (`packages/glass-shared/src/metrics/api.ts`, `fetchComputeMetric`), and so are the
  strength and rarity clients.
- **"Appearance count" is not a metric anywhere.** The over-the-wire test reaches A8 by expanding along `MENTIONED_IN`
  and counting those links per person, because raw degree ranks a relay member first (7 against the principal's 1)
  (`OspreyFlow_Build/tests/scenarios/test_phase8_exit_over_the_wire.py:479-508`). The React panel has no such metric.
- **The affiliation half** of A8 is `MEMBER_OF` links to an `Organisation` (`test_phase8_exit_over_the_wire.py:510-527`).
- **The page it sits on.** GG2e's `/cases/graph?case=…` (drafted 26 November), its module holding the reader's own
  projection of the working set in GG2c's store. GG2e's question 2 was ruled (a): with scripts off that page says the live
  graph needs scripts, under a parity line the owner writes.

## Acceptance (red before, green after)

Scenario **MT** (new; "metrics"), written first in `spec/08`, with A8 and A12 run on the GOV.UK tree as its last rows;
`apps/pages/test/govuk/live-metrics.spec.ts` (Playwright, both browsers) red on GG2e's page, green after. A8's and A12's
existing tests stay green and unchanged.

## Questions for the owner (the proposal first)

1. **Where it sits.** (a) **The `metrics` panel of GG2e's graph page**, in PL8b's side column, a part of the
   `query-builder` row (GG4i1's question 1). (b) A page of its own (it would need the live working set again).
2. **Labels.** (a) **Each row names the item as the module's store holds it** (its type and label); **a value for an id the
   store does not hold is dropped, never shown with its id** (the explain overlay's "belt and braces" rule,
   `apps/workspace/src/resolution/explainView.ts:8-15`). (b) As the React panel: the raw id. **Not proposed** (rule 7).
3. **How many rows.** (a) **Every item in view is ranked, in pages of 20 with "Show the next 20", and the caption says
   "Ranked 1 to 20 of 1,204 in view"** (the count is of the reader's own store: rule 3 holds). (b) The top 20, with "The top
   20 of 1,204 in view" said. Either is not a silent cut; (a) is proposed because the page has no table elsewhere.
4. **A8's appearance count.** (a) **"Mentions" is offered beside the seven: for each item in view, the number of its
   `MENTIONED_IN` links the store holds, worked out in the module with no request.** It counts only what the stream sent
   this reader (rule 3); it is said "in view", since a mention not yet expanded onto the graph is not counted (the page
   says "Expand along MENTIONED_IN to count every mention", linking GG2f1's expand). (b) No such metric: A8 is met by
   degree after an expansion along `MENTIONED_IN` alone. The over-the-wire test shows degree ranks wrongly on A8's
   fixture. (c) A Conduit metric (an amendment).
5. **A large graph** (20,000 items or more). (a) **The page says "This graph is too large to rank here: 20,000 items or
   more. Narrow it, or save a view of part of it"**, and sends nothing. (b) **A Conduit read of a job's result (GG4i1's
   question 4 (b)): an amendment and a security part: owner.**
6. **Who sees it.** (a) **The panel is offered when `GET /v1/me/rights` lists `run_analysis` and the case's level is at
   least Viewer**, as the route asks; otherwise it says "You need the right to run analyses" (the words of
   `packages/glass-shared/src/help/roles.ts:59`). Strength, rarity and Mentions need only `investigate`, so they are
   offered without it. The metrics offered are the React panel's seven (degree, weighted degree, betweenness,
   eigenvector, PageRank, clustering coefficient, Clique Metric), strength, rarity and Mentions. (b) Hidden without the right.
7. **Communities, the hulls and the filters.** (a) **Not in this part.** The community hulls draw on the canvas and are
   the graph's "find groups" (GG2g); the metric threshold and the strength floor dim the canvas and go with GG4i4's
   dimming (GG4i4 owns their keyboard ids and cases). **The legend** (the strength influencers and the composition,
   ADR-139 decision 7 and Amendment 2) **is this part's**, beside strength. The `communities` metric is not offered in the ranking (it is a label, not a number). (b) All here.
8. **Clique Metric's bounds.** (a) **`k_min` 4 and `k_max` 30 as the route's defaults, not offered**, said in the
   metric's description. (b) Two number fields.
9. **Scripts off.** (a) **Covered by GG2e's ruled parity line ("the live working set needs scripts"), if its words cover a
   panel of that page; if they do not, a word added to that line is the owner's** (`PARITY_EXCEPTIONS.yaml` is the
   owner's file). (b) A server-rendered ranking: it would need a working-set read for the labels (an amendment, GG2e's
   question 2 (b), ruled out).

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A12: Clique Metric, after the setup A12 needs: the relay group and the principal subject expanded to depth 1 through GG2f1's expand (`test_phase8_exit_over_the_wire.py:604-614`; on the bare seeded set degree ranks a relay member first, :484) | the relay group's members rank at the top by clique, and low by degree under Compare | the second column fetched with the first metric's name |
| 2 | A8: Mentions | the principal subject first; with a filter to `MEMBER_OF`, the affiliated subset named by its `Organisation` | Mentions counting every link, not `MENTIONED_IN` alone (degree) |
| 3 | Two readers of different clearance | each ranking holds only items in that reader's store; no value for a hidden item, no rank gap where one was | at the page's call site: the module's compute answer cached by case and metric in the browser's shared storage, not per session, so a second reader signed in on the same browser is shown the first's values |
| 4 | A value for an id the store does not hold (the fixture sends one) | dropped; the caption counts only the shown | the row drawn with the id as its label |
| 5 | 1,204 items in view | "Ranked 1 to 20 of 1,204 in view"; the next 20 reachable | a bare cut to 20 with no words |
| 6 | 20,000 items or more | question 5 (a)'s sentence; no request | the `mode: "job"` answer drawn as an empty ranking |
| 7 | No `run_analysis` | the seven not offered; strength, rarity and Mentions are; a hand-made call refused 403 said in words | the right read from the role's name, not `GET /v1/me/rights` |
| 8 | Select a row | the canvas focuses that item (GG2e2's focus) and the live region names it | the focus sent to the first row whatever was chosen |
| 9 | A delta arrives while ranked | the ranking marked "out of date: rank again"; nothing re-sent by itself | a re-fetch on every delta (a request per frame) |
| 10 | A POST without `X-CSRF-Token` | refused by the page service, nothing sent (I17) | the module's call outside the check |
| 11 | No id in visible text or the live region | none (rule 7) | an id in a row's `aria-label` |
| 12 | Keyboard | one case per `METRICS_PANEL_ACTIONS` id this part offers (`ranking-opens-loaded-and-folds-by-keyboard`, `row-select-and-centre`, and the legend's `legend-lists-the-strength-influencers-by-keyboard` and `legend-shows-the-composition-by-keyboard`, `actionRegistry.ts:224-226`) in `test/govuk/keyboard/`; the four filter ids listed as GG4i4's, which has their cases (rule 13) | an offered id with no case |
| 13 | The policy | no `securitypolicyviolation`; every call same-origin through the forwarder (I2, I3) | a call to the Conduit's own address |

## Waits on

GG2e (the page and the store) and GG2e2 (the focus a row uses, case 8); GG2c (merged path); PL8b (the side column);
GG2f1 (A12's expansion, case 1); WS4b to merge. The owner only for question 5 (b) or 9.

## Files touched

`spec/08` (MT); `apps/pages/modules/graph/` (the metrics panel's module part, beside GG2e's), the graph page's template
and words (`tree-govuk/`, `server/views/`); `packages/glass-shared/src/metrics/` (the ranking's pure part: order, pages,
the dropped ids, Mentions, with unit tests); `test/govuk/live-metrics.spec.ts`, `keyboard/`, the fixture Conduit's
compute, strength and rarity answers (narrowed as the routes narrow).

## Checks (frozen when cut)

GG2e's list, plus `apps/workspace`'s `metrics/` suite (unchanged and green).

## Out of scope

Communities and hulls (GG2g); the metric filter and strength floor (GG4i4); a job's result (owner, question 5 (b)); the
React panel's bare cut and raw-id label (reported); any Conduit change.
