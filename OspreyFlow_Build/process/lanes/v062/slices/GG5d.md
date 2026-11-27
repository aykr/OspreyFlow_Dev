# Slice GG5d · GG5 · The boundary filter and the gazetteers on the case map: a drawn boundary by pointer, by keyboard and by form; the place search; the case's gazetteers added and removed (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M** (two surfaces; if the builder's count passes 15 cases, split as GG5d1 the gazetteers and the place search,
GG5d2 the boundary). Release scope A-full (D273). **It needs GG5b built.** It draws nothing with Sigma.
**It can be built beside GG5c**: both add to the map page, so the second to merge takes both sides of the page's
template and module (the plan's append-only rule does not cover these two files; the conductor runs them one after the
other, or the second rebases).

**Where it comes from.** `FUNCTIONS.yaml` row `map-and-site-plans` (`apps/pages/FUNCTIONS.yaml:388-394`).
`spec/02_GLASS_FRONTEND.md` §3.5 (:2044 onward): "Gazetteer search: place lookup against the gazetteer datasets the
case reads … choosing a place moves the map there; no hosted geocoder is ever called"; "Boundary layers: … a drawn or
selected boundary is a spatial filter like any other". ADR-147 Amendments 1 and 2 (the place search; the case's
gazetteers, the owner's ruling 6).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The place search.** `POST /v1/investigations/{id}/map/places` (`services/api/app.py:9365-9393`): Viewer and
  `INVESTIGATE`; "the loaded gazetteer's places in the case's datasets … read with the case's principal in the store,
  rule 3 … never a hosted geocoder"; audited `map_place_search`. `PlaceSearchRequest`
  (`packages/schemas/mapconfig.py:386-397`): `query` 2 to 100 characters, stripped; `limit` 1 to 25, default 10.
  `MapPlace` (:400-408): `id`, `name`, `lon`, `lat`, "never the gazetteer's own identifier" (rule 7).
  `PlaceSearchResponse` (:411-417): `places`, and `more`, "counted after the access filter" (rule 2).
- **The case's gazetteers.** `GET .../map/gazetteers` (`app.py:9436-9447`), Viewer and `INVESTIGATE`: "names only,
  never a count of places"; a case reading a composite or nothing has none (`_own_dataset`, :9397-9403). Adding and
  removing are dataset-level: `PUT` and `DELETE /v1/datasets/{dataset_id}/gazetteers/{gazetteer_id}` (:10638-10678,
  :10683-10712), each behind `RUN_PIPELINES`, the dataset route's own gate (`StudioDatasetDep`) and
  `NoLoadingAComposite`; a gazetteer of another unit is the same 404 as none (:9459-9475); a removal answers
  `REMOVED_WORDS` (:9408-9411) in `said`. The React client tells the empty list's four states apart with
  `GET .../datasets` (`apps/workspace/src/map/gazetteers.ts:37-66`, the route at `app.py:4324`) and says each refusal
  in its own words (:68-101).
- **Keyboard ids.** `MAP_VIEW_ACTIONS` (`packages/glass-shared/src/keyboard/actionRegistry.ts:992-998`):
  `find-a-place-by-keyboard`, `add-a-gazetteer-by-keyboard`, `remove-a-gazetteer-by-keyboard` (and the basemap
  switch), each with its case in `apps/workspace/keyboard/map-view.spec.ts:105-224`.
- **The boundary.** `apps/workspace/src/map/BoundaryFilterTool.tsx`: only the drawn half; "scoped to the current working
  set" (:16-24); points placed by map clicks (`onNextMapClick`, `site/siteLayer.ts:138-150`, a `MouseEvent` listener),
  "Close boundary" at three points, the places inside found by `pointInPolygon` (`map/geometry.ts:14`), handed to the
  cross-filter as the selection (`BoundaryFilterTool.tsx:75-85`). **It has no keyboard route**: no id in any registry,
  and no keyboard spec names it (rule 13; a workspace finding, not this slice's to fix).
- **Stored boundaries.** `AnalyticsPort.list_boundaries` (`packages/ports/analytics.py:263-273`) exists in both adapters
  with its access case (`test_suite.py:1453`), **but no Conduit route calls it.**

## Acceptance (red before, green after)

Scenario **MP**'s place-search, gazetteer and boundary rows (after GG5b's), written first;
`apps/pages/test/govuk/map-places.test.ts` and `map-boundary.test.ts`, and the map page's browser spec for the drawn
boundary, red on GG5b's page, green after; GG5b's cases unchanged and green.

## Questions for the owner (the proposal first)

1. **The place search, scripts off.** (a) **A GET form on the map page (`&find=…`)**; the server half posts the search
   once and lists each place's name and its position in words, with "More places match: say more of the name" when
   `more` is true (rule 2). Choosing a place is a link that opens the map centred on it at `PLACE_ZOOM` (13, moved from
   `MapView.tsx` to `glass-shared`, I11). A query under 2 characters is said in the page's words, and nothing is sent.
   (b) Scripts on only.
2. **Where the gazetteers are changed.** (a) **On the map page, as in the workspace**: the list (names, added or not),
   with Add and Remove as POST forms with the anti-forgery token, the server half calling `PUT` or `DELETE`, then a `303`
   to the map page; `said` shown as given. Offered only when `GET /v1/me/rights` holds `run_pipelines` (`app.py:20664`);
   the Conduit refuses anyone else all the same. (b) In the Studio's dataset pages.
3. **The four empty states.** (a) **As the React client says them** (`gazetteers.ts:54-64`), from `GET .../datasets` (reads nothing; not one
   source; a drawing; none built). (b) One sentence for all.
4. **Refusals.** (a) **The React client's sentences** (`gazetteers.ts:82-100`): 403 the right; 404 "cannot be changed
   for this case's dataset now"; 409 composite or drawing; never the Conduit's detail. (b) Your words.
5. **Drawing a boundary with scripts on.** (a) **By pointer (click to place a point) and by keyboard**: the map takes
   focus, the arrow keys move a centre mark, Enter places a point, Backspace takes the last one away, and "Close
   boundary" needs three points. Each is a keyboard case (rule 13). **Its id cannot go in `MAP_VIEW_ACTIONS`**: the workspace's
   `map-view.spec.ts:225-227` asserts every id there has a workspace case, and the workspace has no keyboard route for
   its boundary. So (a) is: the id `draw-a-boundary-by-keyboard` in a registry of the page service's map actions,
   covered by the page's keyboard spec; the workspace's gap goes to the backlog. (b) The same key route built in the
   workspace in this slice, and the id in `MAP_VIEW_ACTIONS` (a larger slice, two front ends). (c) Pointer only.
   **Not proposed** (rule 13).
6. **A boundary with scripts off.** (a) **A form of points, one "latitude, longitude" per line**, three to 50, each
   checked (a number, in range), refused in words otherwise; the same filter follows. 50 is the page's bound on what it
   is sent, said as such, never a cut of what it reads. (b) Scripts on only, with a parity line in
   `PARITY_EXCEPTIONS.yaml` (the owner's file).
7. **What the boundary filters.** (a) **The saved view's places on this page**: the map and the table show the places
   inside, said as "Showing the places inside your boundary. Clear the boundary", the inside test by `pointInPolygon`
   moved to `glass-shared` (I11) and run by the server half for the table and by the module for the map. With GG5c
   built, its heat and cells are read for those places' ids. The boundary travels in the page's address as its points.
   The cross-filter across panels is GG4i's. (b) The boundary sent to the Conduit as a filter: an amendment.
8. **Stored boundaries** (`list_boundaries`, no route). (a) **Out of this slice**; a Conduit route would be an amendment
   (decision 11), brought when a tier-1 boundary set ships. (b) Cut the route now (owner).

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | "Ash" searched, three synthetic places held | one `POST .../map/places` with `{"query": "Ash"}`; three rows, name and position in words | the search posted twice in one render (two audit rows), or the page's `find` field sent in place of `query` |
| 2 | `more: true` | the "More places match" sentence | `more` dropped |
| 3 | "A" (1 character) | the page's sentence; nothing sent | the 422 shown raw |
| 4 | Choosing a place | the map opened on it at zoom 13 | the camera fitted to the view's places instead |
| 5 | The gazetteer list, a reader with `run_pipelines` | each name, added or not, with Add or Remove | a count of places shown |
| 6 | The same reader without `run_pipelines` | names only, no form; Tab passes by | the forms offered |
| 7 | Add | one `PUT` to the dataset's route; `303` to the map page; the list as returned | the case's id sent in place of the dataset's |
| 8 | Remove | one `DELETE`; `said` shown word for word | `said` dropped |
| 9 | 403, 404, 409 from the change routes, and no answer | each in its sentence; the 502 page for no answer | the Conduit's detail shown |
| 10 | The four empty states (`reads_nothing`, `drawn`, `not_one_source`, `none_built`) | each in its words | one sentence for all; `drawn` read as `not_one_source` |
| 11 | No `_csrf` on Add or Remove | refused, nothing sent (I17) | the route outside the check |
| 12 | A boundary drawn by pointer around 4 of the view's 12 places | the map and table show 4; the sentence; **then the map is panned and the boundary drawn again around the same 4**: still 4 | the inside test run on the places' screen positions (red only after the pan, so the case pans) |
| 13 | The same by keyboard | the same 4 | a step that only a click can take |
| 14 | The same by the scripts-off form | the same 4 | the points read as longitude, latitude |
| 15 | A form with 2 points, or a point out of range, or 51 points | each refused in words; nothing filtered | the boundary closed on two points; the 51st dropped silently (rule 2) |
| 16 | Two readers of different clearance | each filters only what the route sent them; the place search lists only what each may read | at the page's call site: the map page's render cache keyed by the case, not the session (the second reader served the first's places), or the first reader's token reused for the second's search |
| 17 | No id on the page | none (a place's id travels in no text) | a place's id printed |
| 18 | Keyboard ids | `find-a-place`, `add-a-gazetteer` and `remove-a-gazetteer` (`MAP_VIEW_ACTIONS`) and `draw-a-boundary` (the page's own registry) each with a page case, checked by `assertAllCovered` as the workspace does | one id left without a case; the workspace's `map-view.spec.ts` red because an id was added to its registry |

## Waits on

GG5b built. GG5c only for the heat read after a boundary (question 7); GG5c and GG5d share the map page's template and
module, so they run one after the other. GG4i for the boundary as a filter of other panels.

## Files touched

`spec/08` (MP's rows); `spec/02` §3.5 (the page service's boundary by keyboard and by form, one paragraph);
`apps/pages/modules/map/` (the boundary's drawing and keys); `apps/pages/server/` (the search, the gazetteer forms, the
boundary), `server/views/` (the words); `tree-govuk/` (the map page's parts); `packages/glass-shared/src/map/` (it exists, with `conduitRequest.ts`, `contrast.ts` and `providers.ts`; added:
`pointInPolygon` and `PLACE_ZOOM`, moved, with their tests) and `packages/glass-shared/src/keyboard/actionRegistry.ts`
(the page service's map registry, one id); `apps/workspace/src/map/geometry.ts`, `MapView.tsx` (imports only); the tests above,
`test/govuk/keyboard/map.spec.ts`, `test/govuk/scripts-off/map.spec.ts`.

## Checks (frozen when cut)

GG5b's list, with the workspace's unit and keyboard suites (the moved functions and the new registry id).

## Out of scope

Stored boundary layers (question 8); the boundary as a filter of other panels (GG4i); the heat layer (GG5c); site plans
(GG5e); the workspace's own missing keyboard route for its boundary tool (a finding for the workspace's owner of rule
13); any Conduit change.
