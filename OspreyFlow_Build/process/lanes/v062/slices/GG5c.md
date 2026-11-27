# Slice GG5c · GG5 · The heat layer and the hotspot cells on the case map: density from `geo_bins` drawn by MapLibre, the hotspot cells as a ranked table, scripts off whole (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M.** Release scope A-full (D273): in 0.7.0. **It needs GG5b built** (the map module, its worker, basemap and
glyphs on the page service, and the case map of a saved view's places). It draws nothing with Sigma, so decision 9's
first sentence does not hold it; GG5b's own exception was not given ("not GG5b", RULINGS.md 26 November about 10:35),
so this slice follows GG5b's order.

**Where it comes from.** `FUNCTIONS.yaml` row `map-and-site-plans` (`apps/pages/FUNCTIONS.yaml:388-394`: "heat layer,
hotspot histogram, …", scenarios A1, A2, A3, B17). `spec/02_GLASS_FRONTEND.md` §3.5 (:2044 onward), "Heat map: Density
layer from `AnalyticsPort.geo_bins`, server-side binned — never ship a million points to the client". Scenario A2
(`spec/08_ACCEPTANCE_SCENARIOS.md:383`): "The four hotspot cells are the top four by count, and together account for
~52% of incidents". The plan's row GG5c (`drafts_2026-11-26/CHAIN_PLAN.md:91`).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The density read.** `POST /v1/analytics/geobins` (`services/api/app.py:10057-10081`), `require_right(INVESTIGATE)`;
  the case in the body is gated at Viewer by `_case_event_filter` (:9953-9966, "a case the account cannot see answers 404
  and reads nothing"; it counts the case's own events alone). `GeoBinRequest` (`packages/schemas/analytics.py:295-304`):
  an `EventFilter` and `precision` 1 to 12. `GeoBin` (:307-311): `cell_id`, `centroid_lon`, `centroid_lat`, `count`.
  Audited `analytics_geo_bins`.
- **Access is in the adapter** (rule 3). `_predicate` joins the filter and the access predicate before aggregation
  (`packages/adapters/analytics_duckdb/adapter.py:244-250`; `access_filter.py:1-3`, "injected into the `WHERE` clause
  before aggregation"). The conformance suite has `test_unauthorised_geo_bin_count_matches_a_corpus_without_the_hidden_event`
  (`OspreyFlow_Build/tests/conformance/analytics_port/test_suite.py:1119`) and the same for the histogram (:1096) and the
  cross-filter (:1224). **Each of those plants a hidden *event*. None plants a visible event whose *end* is a node the
  reader may not read** (question 2).
- **The hotspot cells.** `apps/workspace/src/map/HotspotHistogram.tsx`: a categorical `cross_filter` dimension on
  `target_id` (:62-66), restricted to the link types that end at a `Location` (`locationEdgeTypeNames`, :41-43), ranked
  highest first (`rankTargetIdBuckets`, :31-36). Its header (:5-18) says why: `geo_bins` "cannot resolve individual grid
  cells at a single fixed site's scale" (ten yards fell into 2 bins at precision 12), and the categorical dimension
  "reproduced the acceptance figure almost exactly (51.1% vs. the spec's ~52%)". **A bucket's `label` is the target
  node's id** (`_categorical_histogram`, `adapter.py:458-470`: `SELECT {expr} AS label`), which the React panel shows as
  the bar's name. `POST /v1/analytics/cross-filter` (`app.py:10001-10025`) is gated as the geo-bin route.
- **The React heat layer.** `MapView.tsx:417-452`: a MapLibre `heatmap` layer over a GeoJSON source of the bins, weight
  by `count`, colours from the sequential ramp (`SEQ_HEX`). Fed by `followCrossFilterWithMapBins`
  (`apps/workspace/src/crossfilter/mapBins.ts:13-41`) at `GEO_BIN_PRECISION = 8` (`App.tsx:265`), with the cross-filter's
  window, selection and weekday-hour cells. The fetch wrappers are already in `glass-shared`
  (`packages/glass-shared/src/analytics/api.ts:66`, :90).
- **No route names a node by its id** outside a working set or a saved view: `/v1/investigations/{id}/nodes` is
  `DELETE` only (`app.py:5885-5916`).
- **GG5a's run** (`away/GG5a`, `away/GG5a_AWAY_REPORT.md`) took a vector, raster, sprite and glyph style. **It did not
  take a `heatmap` layer** (a WebGL program of its own); the policy table is MapLibre's, not this layer's.

## Acceptance (red before, green after)

Scenario **MP**'s heat and hotspot rows (after GG5b's), written first, with A2's figure on the page: the site fixture's
four hotspot cells ranked first and their share said. `apps/pages/test/govuk/map-heat.test.ts` (the server half and the
table) and the map page's browser spec (the layer drawn, I2 and I3 with the heat layer present), red on GG5b's page,
green after; GG5b's cases unchanged and green.

## Questions for the owner (the proposal first)

1. **What the heat and the cells are counted over.** GG5b's map draws a saved view's places. (a) **The saved view's
   events: `node_ids` is the view's nodes, never empty** (an empty `node_ids` is no restriction, so a view with no node
   would heat the whole case: case 7); the window, if the view has one. A whole-case heat with no view is a later
   question, with the live working set (GG2e). (b) The whole case's events, whatever the view.
2. **A visible event whose end the reader may not read (owner, security, rule 3).** The access predicate reads the
   event's own handling (`access_filter.py:57-82`). Nothing found on `origin/main` says an event is never visible to a
   reader who may not read one of its ends, and no conformance case plants it. If it can happen, a hotspot bucket
   names a node id the reader may not read, and its count says the node exists. (a) **The builder writes the case
   first** (`test_unauthorised_categorical_target_bucket_matches_a_corpus_without_the_hidden_end`, a visible event to a
   SECRET `Location`, read by an OFFICIAL reader), in the analytics conformance suite, on both adapters; **if it is red,
   the slice stops** and the fix is a Vault security part (SE-style), never a page-side filter. (b) Your words.
3. **Naming a cell.** A bucket's label is a node id, and the page shows no id (GG4a's rule). (a) **A bucket is named by
   the view's own node of that id** (the view's nodes come from GG2b's read, which the graph adapter filtered), and the
   hotspot read is restricted to the view's `Location` nodes with `edge_types` from `locationEdgeTypeNames`, so every
   bucket is a node the reader was sent. **This changes A2's denominator.** A2's own over-the-wire test counts over the
   whole case, with no `node_ids` (`OspreyFlow_Build/tests/scenarios/test_phase8_exit_over_the_wire.py:403-417`:
   `total = sum(counts)` over every bucket, share 0.45 to 0.60). So the page's share is the view's, and the scenario
   row's fixture view **holds every cell and every incident of the site fixture**, so that the page's share equals A2's;
   the page says "of this view's events" beside the share, and the builder records the measured share against the
   over-the-wire test's for the same fixture. A bucket whose id is not in the view is not expected (case 6); if one comes,
   the page says "This view's places could not be counted" and shows no table, never a guessed name. (b) A Conduit
   amendment: the categorical bucket carries its node's label, resolved in the adapter (decision 11, owner).
4. **Scripts off.** (a) **Two tables, whole:** the hotspot cells (name, events, share of the view's events as the route's
   `total` gives it), highest first; and the density areas (each area's centre in words, "51.50° N, 0.12° W", and its
   count), highest first. No page cut: the route's answer is shown whole (rule 2); the builder reports the largest
   synthetic world's bin count. (b) The hotspot table only.
5. **The precision.** (a) **8, the React workspace's, moved to `glass-shared` as one constant** both read (I11), so the
   two front ends bin alike. (b) A page setting of its own.
6. **Choosing a cell (A3's first half).** (a) **Each cell row has a link "Show only this cell"**, the cell carried in the
   link's query (an id in a link, never in text); the page then draws the heat and the places of that cell's events
   only, and says "Showing one cell: <name>. Show every cell". The canvas, timeline and histograms restricting too
   (the rest of A3) is the cross-filter's (GG4i). (b) No choosing in this slice.
7. **The layer's look.** (a) **The React layer's paint, its colours read from the tokens' sequential ramp** (no colour
   outside the tokens), drawn under the places' circles. (b) Your words.
8. **How the data reaches the module.** (a) **The server half reads once per render (one geo-bin read, one cross-filter
   read) and gives the module the bins in the page**, as GG5b gives it the places; the module fetches nothing. (b) The
   module fetches through the forwarder.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | The site fixture's view, scripts on | the heat layer drawn under the circles; `idle` reached | the layer added before the style's `load` (MapLibre refuses it), the readiness check on `load` alone |
| 2 | The same, scripts off | both tables whole, the hotspot table's top four the fixture's four, their share about 52% (A2) | the share counted over the cells shown, not the route's `total`; and a fixture view missing one cell (the share then differs from A2's measured figure, and the case says so) |
| 3 | Ranking | highest count first; ties in the route's order | the route's alphabetical order kept |
| 4 | One render | exactly one geo-bin read and one cross-filter read (two audit rows) | a second read for the table |
| 5 | Two readers, OFFICIAL and SECRET, one SECRET event in a cell | the OFFICIAL reader's counts and share as if the event were not there | at the page's call site: the map page's render cache keyed by the case and view, not the session, so the OFFICIAL reader is served the SECRET reader's render (or the SECRET reader's token reused for the OFFICIAL reader's read) |
| 6 | Question 2's case, in the conformance suite | an OFFICIAL reader's buckets as a corpus without the SECRET end | written against today's adapters first: **red there means the slice stops** (question 2 (a)); green there means something already keeps the end out, and the builder names it and shows the case red with that one thing taken away |
| 7 | A view with no node | "Nothing in this view has an event"; no read with an empty `node_ids` | `node_ids: []` sent (the whole case heated) |
| 8 | A bucket whose id is not among the view's nodes | the "could not be counted" sentence; no table | the id printed as the name |
| 9 | No id on the page | none, in either table or the page's data | a cell's id in the row's text |
| 10 | "Show only this cell" | the heat and the places of that cell's events only; the sentence and the way back | the cell kept in the page but not sent as `node_ids` |
| 11 | The policy (I2) and other origins (I3) with the heat layer | no violation, Chromium and WebKit; no request but the page's own | a heat colour set as an element style by the module |
| 12 | Colours | every heat colour a token's | a hex literal in the module's paint |
| 13 | The Conduit's refusals | no `INVESTIGATE` or no level: GR1a's 404 page; no answer: the 502 page, the place table still shown | the 403 passed through |
| 14 | A body missing a field `GeoBin` or `Histogram` requires | "The map's counts could not be read"; never a zero | each required field removed in turn |
| 15 | Keyboard | the tables and each "Show only this cell" link reached and working (rule 13), one case each in `test/govuk/keyboard/` | a link out of the tab order |
| 16 | I11 | one precision constant, imported by both front ends | the page's own `8` |

## Waits on

GG5b built (the map module and the case map of a saved view); GG2b's saved-view read (the view's nodes). Question 2
(owner, security): if its case is red, a Vault security part first. GG4i for the rest of A3 (not this slice's).

## Files touched

`spec/08` (MP's heat and hotspot rows); `spec/02` §3.5 (the page service's heat layer, one line);
`apps/pages/modules/map/` (the heat layer); `apps/pages/server/` (the map page's two reads), `server/views/` (the
words); `tree-govuk/` (the two tables); `packages/glass-shared/src/analytics/` (the precision constant) and
`apps/workspace/src/App.tsx` (its import, nothing else); the tests above; for question 2,
`OspreyFlow_Build/tests/conformance/analytics_port/test_suite.py` (one case, test only).

## Checks (frozen when cut)

GG5b's list, with the analytics conformance suite on both adapters (question 2's case) and the workspace's unit suite
(the precision's import).

## Out of scope

The cross-filter across panels (GG4i); the timeline (GG3c); the boundary filter (GG5d); the site plan's own image and
grid (GG5e1); the graph drawn over the map (GG5f); any Conduit change (question 3 (b) would be an amendment).


## The owner's answers (the owner's answers of 27 November 2026, after 09:40 UTC; RULINGS.md)

1. **Q2 (a): the conformance case comes first, on both analytics adapters** (DuckDB and ClickHouse): a visible event whose end the reader may not read. Write it before any page code.
   - **If it is red on either adapter, stop the slice and say so.** The fix is a Vault security part, **never a page filter.**
   - If it is green on both, build the page.

Every other question in this draft stays (a) on the owner's standing word.
