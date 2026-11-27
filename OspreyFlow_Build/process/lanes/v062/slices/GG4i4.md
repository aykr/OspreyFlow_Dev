# Slice GG4i4 · GG4 · The cross-filter on the GOV.UK pages: one filter, carried in the address, that the timeline, the map, the hotspot cells and the graph all read; facets on an event's own fields; and the people of the reports that survive put on the graph (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size L, proposed as GG4i4a (the filter in the address and the facets, scripts off, on GG3c's and GG5c's pages) and
GG4i4b (the graph's dimming and the status bar's count, scripts on, on GG2e's page; and A7's add).** GG4i4a draws nothing
with Sigma; **GG4i4b dims the Sigma canvas, so by decision 9 it merges only after WS4b** (`spec/06_DECISIONS.md` about
lines 41091 to 41102).

**Where it comes from.** The `query-builder` row (`apps/pages/FUNCTIONS.yaml:276-282`). **This part takes A3 and A7**
(`spec/08_ACCEPTANCE_SCENARIOS.md:384`: "Select the hotspot cells … Canvas, timeline and histograms all restrict to those
cells; status bar shows the dimmed count"; :388: "Filter reports to one residential sub-unit and one item category …
The person entities named in the surviving reports are added to the working set as a named history step").
`spec/02_GLASS_FRONTEND.md` §2 rules 2 to 4 ("Filters dim, they do not remove"; "Everything cross-filters"; "the status
bar never lies"). `spec/08`'s "Closed — A7's 'item category' filter" (:439 onward): `EventFilter.value_filters`.

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The routes** (`services/api/app.py`), each `require_right(INVESTIGATE)`, a case read at **Viewer** with the case in
  the body (`_case_event_filter`, :9953-9967: "a case the account cannot see answers 404 and reads nothing"):
  `POST /v1/analytics/histogram` (:9974-9998), `POST /v1/analytics/cross-filter` (:10001-10025: several named
  histograms "against the same filter, so the timeline, the map and the histogram panel restrict in lockstep",
  `packages/schemas/analytics.py:425-447`), `POST /v1/analytics/first-seen` (:10028-10054: when each node and link first
  appears under the filter; the React dimming's one read).
- **The filter** (`EventFilter`, `analytics.py:185-245`): `window`, `node_ids` (a place's events, A3's cells), `edge_types`,
  `value_filters` (`{field: [value, …]}`, values OR-ed, fields AND-ed, equality only, compiled into the adapter's
  `WHERE` beside the access filter: :203-221), `weekday_hours` (at most 168, refused not thinned: :222-251). A field
  name that is not letters, digits and underscores is refused 422 `field_name_refused` (`spec/08:454` onward).
- **The React cross-filter** (`apps/workspace/src/crossfilter/store.ts`): the inputs `window`, `cells`,
  `selectedNodeIds` and the derived `dimmedNodeIds`, `dimmedEdgeIds`, `dimmedCount` (:35-62); `buildEventFilter`
  (:70-84) sends **no `value_filters`**; `refresh` reads `first-seen` once and dims what has no event under the filter
  (:126-166). The status bar says "214 dimmed by filter" (`statusbar/StatusBar.test.tsx:31-38`).
- **No Glass offers A7's item-category filter.** `value_filters` is sent by no client in `apps/` or
  `packages/glass-shared` (searched); the React hotspot panel chooses **one** cell at a time (`next ? [next] : null`,
  `apps/workspace/src/map/HotspotHistogram.tsx:126-130`) where A3 says "the hotspot cells". **Findings for the
  orchestrator**, not changed here.
- **The over-the-wire A7 step does not exercise the filter.** Its comment still calls the item-category filter
  "08's own recorded 'Known gap'" and it seeds three named people directly
  (`OspreyFlow_Build/tests/scenarios/test_phase8_exit_over_the_wire.py:462-477`), while `spec/08:70` names three A7 tests
  that do. A stale comment, and a step whose name is wider than what it proves (rule 12). **A finding for the
  orchestrator.**
- **The pages that read events, drafted 26 to 27 November:** GG3c's timeline (`/cases/timeline?case=…&view=time|week`,
  server-rendered charts and tables, no brush), GG5c's heat layer and hotspot cells (a saved view's map, one cell chosen
  by a link "Show only this cell", leaving "the canvas, timeline and histograms restricting too" to GG4i: GG5c question 6),
  and GG2e's live graph (`/cases/graph?case=…`).
- **The add.** `POST .../working-set/add-by-ids` (`app.py:5688-5722`), Editor, history label `SEEDED`; every label is
  fixed text with no number or name (`services/api/history_labels.py:1-9`, ADR-124 decision 8), so "a named history step"
  is the fixed label "Seeded".

## Acceptance (red before, green after)

Scenario **XF** (new; "cross-filter"), written first in `spec/08`, with A3 and A7 run on the GOV.UK tree as its last
rows; `apps/pages/test/govuk/cross-filter.test.ts` (GG4i4a, scripts off) and `live-cross-filter.spec.ts` (GG4i4b,
Playwright) red, green after. A3's and A7's existing tests stay green and unchanged.

## Questions for the owner (the proposal first)

1. **Where the filter lives.** (a) **In the address, as plain query parameters every case page that reads events
   honours alike**: `from` and `to` (the window, dates), `cell` (a weekday and hour, repeatable), `place` (a place's
   node id, repeatable, in a hidden field or the query string, never in visible text: the one rule for ids; GG4d
   question 5: "a form's hidden field or a link's own path, never in text"), and `facet`
   (`field:value`, repeatable). One shared function in `packages/glass-shared` turns them into the `EventFilter`, so every
   page builds the same filter (A3's "lockstep"); a "Filtered by" summary on each page names what is applied, with "Clear
   the filter". Scripts off whole. (b) Kept in the page service's session for the reader (a second state the address does
   not show; the back button lies).
2. **The split.** (a) **GG4i4a: the parameters, the shared function, the summary, and the facets, on GG3c's and GG5c's
   pages** (both server-rendered); **GG4i4b: the graph page's dimming and count, A7's add.** (b) One slice.
3. **Choosing several cells.** (a) **Each hotspot row is a checkbox in a `GET` form, "Show only these cells"**, so A3's
   four are chosen at once. (b) One cell at a time, as the React panel.
4. **Which facets.** (a) **The builder first reads where the scenario fixture's item category is held (an event column or
   a key in `properties`) and whether the ontology names an event's facet fields. If it does, those are offered; if it
   does not, the builder stops and proposes the list as a `spec/02` §2 addition (rule 11), not a list in the page's
   code.** Each facet's values come from one categorical `cross-filter` dimension on that field, under the rest of the
   filter. (b) A field typed by the person: **not proposed** (no expression in a page; the route would refuse most).
5. **A bucket that names a node** (`place`, and A7's people, are categorical buckets on `target_id` or `source_id`, whose
   label is a node id). (a) **As GG5c question 3 (a): named by a node the page already holds (the view's, or the live
   store's); one that is not held is not shown, and the page says the figures could not be named.** **This waits on GG5c's
   question 2 (owner, security):** whether a visible event can name an end the reader may not read; if the conformance case
   it proposes is red, this part stops with it. (b) A Conduit amendment for labelled buckets (owner).
6. **The graph's dimming (GG4i4b).** (a) **The module reads the same parameters, makes one `first-seen` read through the
   forwarder, and dims what has no event under the filter, never removes it; the status bar says "214 dimmed by
   filter"**, counted over the reader's own store (rule 3). A filter set on another page follows the person to the graph
   page in its address. The metric threshold and strength floor (GG4i2 question 7) dim the same way and are added to the
   same count. (b) The graph page ignores the filter.
7. **A7's add (GG4i4b). This waits on GG5c's question 2 (owner, security) as question 5 does:** the person ids come from
   event ends, and if a visible event can name an end the reader may not read, the ids sent would include it and the
   answer's `not_shown` would count it, telling the reader it exists (rule 3). The add is built only once that question's
   conformance case is green; if it is red, the add stops with question 5 and the fix is the Vault's. (a) **On the graph page, with a filter applied, an Editor is offered "Add the people named in
   the reports shown"**: one categorical `cross-filter` read on the person end of the report links under the filter, then
   one `add-by-ids` with those ids (hidden fields), a `303` and GG2f1's banner (what was added, `not_shown` as a count,
   the cap's refusal with its three options); the history step is "Seeded" (a fixed label: ADR-124 decision 8). **If the
   fixture's reports do not reach their people through an event's ends, the builder stops and reports** before writing
   any other way. (b) Leave A7's add to the query builder (GG4i1).
8. **What a page says when the filter matches nothing.** (a) **"Nothing matches this filter", the filter summary kept, and
   "Clear the filter"**; never an empty chart. (b) The empty chart.
9. **A refused field** (`field_name_refused`, a hand-edited address). (a) **"That filter could not be used", the rest of the
   page read without it**, as A7's third test makes the events table survive a refused name. (b) The 422 shown.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A3 on the GOV.UK tree (GG4i4a): the four hotspot cells chosen on the map page | the address carries four `place`s; the timeline page opened from it shows only those cells' events, and its weekday-hour figures match the over-the-wire A3 figures | the timeline page building its filter without `node_ids` |
| 2 | The same filter (a window, two cells and a facet) on two pages | the two pages' `EventFilter`s equal, field for field | the map page's own copy of the conversion dropping `value_filters` (and, separately, `weekday_hours`) |
| 3 | A7's facet (GG4i4a): one item category and one sub-unit | only matching events counted; values OR-ed within a field, fields AND-ed | two values of one field AND-ed |
| 4 | Two readers of different clearance, one address | each page counts only that reader's events | at the page's call site: the server half's analytics answer cached by the address, not by session, so the second reader opening the same address is served the first's figures |
| 5 | A bucket for a node the page does not hold | not shown; the sentence | the bucket shown with its id as its name |
| 6 | Nothing matches | question 8's sentence | an empty chart |
| 7 | A hand-edited `facet` with a bad field name | "That filter could not be used"; the rest of the page whole | the whole page refused |
| 8 | 169 `cell` parameters | refused in words, as the route refuses (at most 168) | the list thinned to 168 (rule 2) |
| 9 | A3's dimming (GG4i4b) | the nodes with no event under the filter dimmed, none removed; "N dimmed by filter" with N counted from the store | dimmed nodes removed from the graph |
| 9b | The metric threshold and the strength floor (question 6, GG4i4b) | nodes below the threshold, and links below the floor, dimmed and added to the same "N dimmed by filter"; sliding back brightens them | the count left as the event filter's alone |
| 10 | A filter cleared | nothing dimmed; "0 dimmed" gone; one read cancelled if in flight | an older read landing after the clear |
| 11 | A7's add, as an Editor (GG4i4b) | one categorical read, one `add-by-ids` with exactly those ids; "Seeded" in the history | the add sent without the filter (every person in the case) |
| 12 | A Viewer | no add offered; a hand post refused and said in words | the add offered from `investigate` alone |
| 13 | No id in visible text, and no `_csrf` on the add | no id in visible text; the add refused without `_csrf` (I17) | an id in the "Filtered by" summary |
| 14 | Keyboard | the cells form, the facets, "Clear the filter" and the add each a case in `test/govuk/keyboard/` (rule 13); and the four filter ids of `METRICS_PANEL_ACTIONS` (`filter-section-sets-a-strength-floor-by-keyboard`, `filter-section-dims-below-a-metric-value-by-keyboard`, `…-connection-strength-…`, `…-shared-attribute-rarity-…`, `actionRegistry.ts:219-223`) each a case (GG4i4b) | the cells form's submit not reachable |
| 15 | Scripts off | GG4i4a whole; the graph page's dimming under GG2e's parity line | a facet that needs a script |

## Waits on

**GG4i4a:** GG3c and GG5c (so GG5b), and the owner's ruling on GG5c's question 2 (security). **GG4i4b:** GG2e, GG2f1,
GG4i2 (the metric values the threshold dims by), the same GG5c question 2 ruling for the add, and WS4b to merge.

## Files touched

`spec/08` (XF); `spec/02` §2 (only if question 4 finds no facet list); `packages/glass-shared/src/crossfilter/`
(the parameters to `EventFilter` function, with unit tests); GG3c's and GG5c's server halves and templates (the filter's
parameters, the summary, the facets, the cells form), a shared `tree-govuk` partial for "Filtered by"; the graph page's
module (GG4i4b) and its status bar; `test/govuk/cross-filter.test.ts`, `live-cross-filter.spec.ts`, `keyboard/`,
`scripts-off/`; the fixture Conduit's three analytics answers (filtered as the principal, refusing as the routes refuse).

## Checks (frozen when cut)

GG3c's and GG5c's lists for GG4i4a; GG2e's for GG4i4b; `apps/workspace`'s `crossfilter/` suite unchanged and green.

## Out of scope

The timeline's brush and playback (GG3c's module, later); the boundary filter (GG5d, which sets `place` the same way);
any Conduit change; the React panel's one-cell choice and the missing facet (reported).
