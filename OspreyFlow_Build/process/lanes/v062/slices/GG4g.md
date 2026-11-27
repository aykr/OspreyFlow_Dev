# Slice GG4g · GG4 · Graph extras on the GOV.UK pages: the case's Explore figures and *Find connections*, read-only, scripts off (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M** (L if question 1 is (b); split then as GG4g1 Explore, GG4g2 Find connections).

**Where it comes from.** `FUNCTIONS.yaml` row `graph-extras` ("Graph extras: Explore panel, find connections",
`apps/pages/FUNCTIONS.yaml:253-259`, slice R6, scenarios A9 and B21). ADR-100 (the Explore panel,
`spec/06_DECISIONS.md` :10391 onward) and `spec/02_GLASS_FRONTEND.md` :1151-1180 (its blocks and words); ADR-116 (Find
connections, `spec/06` :14078 onward) and `spec/02` :988. The plan's row: "GG4g | Graph extras: the Explore panel and
find connections | GG2e and GG3".

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The Explore routes** (`OspreyFlow_Core/services/api/app.py:6792-7049`), each `require_right(INVESTIGATE)` and the
  case's **Viewer** gate, each audited, "each figure … of the case's datasets and the analyst's clearance only (rule 3); a
  ranking carries its total and offset, so a page never passes for the whole (rule 2)" (:6792-6797):
  `GET .../explore/counts` (`TypeCounts`, :6810-6828); `.../most-connected` (`RankedNodes`, `entity_type`, `limit` 1 to
  `EXPLORE_MAX_PAGE = 50`, `offset`, :6800, :6831-6854); `.../busiest-links` (`RankedLinks`, also `node_id`,
  :6857-6889); `.../busiest-days` (`BusiestDays`, :6892-6924); `.../groups` (`Groups`; "a case over the working set's caps
  is `limit_exceeded`, never a sample", :6927-6948); `.../whats-new` (`WhatsNew`, :6951-6973); `.../starter-questions`
  (`StarterQuestions`, :6976-6997). **`POST .../starter-questions/{id}/run`** (:7008-7049) is the Editor's and **writes
  the working set** (`working_set.seed`, `publish_delta`, a history step).
- **The models** (`packages/schemas/explore.py`): every ranking has `total` and `offset`; `Groups` has
  `not_shown_groups` and `total_bridges`; several have `computed_at` ("Counted at …", ADR-100 Amendment 3). **`WhatsNew`
  names people by id**: `ConfirmedNode.confirmed_by`, `MarkedNode.marked_by` (principal ids), and a load by `load_id`
  and `recipe_id`.
- **Find connections** (`app.py:9192-9218`): `POST /v1/investigations/{id}/connections`, `INVESTIGATE`, Viewer gate, body
  `ConnectionsRequest` (`packages/schemas/domain.py`: `source`, `target`, `degree` 1 to `CONNECTIONS_CEILING`,
  `edge_types`; the same node twice refused in words); answers `Connections` (`degree`, `paths` of hydrated `Path`s,
  `more`, `searched_to`); "at most ten routes come back for a degree, and more than that is said, not hidden"
  (`CONNECTIONS_SHOWN = 10`, `domain.py:736`); "a hidden end and an unknown one answer alike". The React panel
  (`apps/workspace/src/connections/FindConnectionsPanel.tsx:1-31`): From and To "by search over the case's datasets or
  taken from the node selected on the canvas"; widened a degree at a time to eight, "each degree keeps its own group so a
  longer route never hides a shorter one".
- **Finding a node by name** is the case's own suggest, `POST .../suggest` (:6743-6789, `INVESTIGATE`), as the React
  Ownership place uses it (`packages/glass-shared/src/ownership/api.ts:37-44`).
- **Every Explore node is a button that puts it on the canvas** (`spec/02` :1172-1174). No GOV.UK page holds a canvas
  before GG2e, and a working-set write before GG2f.
- **Decision 9** (`spec/06` :41092-41102) holds a page that draws with Sigma, and "the rest of R4". This row is R6 and
  this slice draws nothing; CHAIN_PLAN (:108-109) still counts it held (question 0b).

## Acceptance (red before, green after)

A new scenario, **EX** ("A case's Explore figures and Find connections as GOV.UK pages, read-only"), written first in
`spec/08`, and `apps/pages/test/govuk/explore.test.ts` and `connections.test.ts`, red before the pages exist, green after.

## Questions for the owner (the proposal first)

0. **Starting before GG2e and GG3** (the plan's row says GG4g needs both). (a) **Read-only, so it needs neither the
   canvas nor a selection: it starts after GG3a (for its search words)**, the actions that put things on the graph coming
   with GG2f. (b) Wait for GG2e.
0b. **Merging before WS4b** **(owner: decision 9).** CHAIN_PLAN (:108-109) counts GG4g to GG4i among the slices decision 9
   holds. This slice draws nothing with Sigma, so decision 9's first sentence does not hold it, and its row is R6, not R4;
   but holding it or not is a reading of decision 9, and merging before WS4b is the owner's alone. (a) **It merges when
   ready, before WS4b, being R6 and drawing nothing with Sigma**, by the owner's word. (b) It waits for WS4b, as the plan
   counted it.
1. **Scope.** (a) **Explore's read-only blocks (what the case holds, most connected and by entity type, busiest links,
   busiest days, groups and bridges, what's new) and Find connections, in one slice.** Starter questions, *Add…* and *Show
   on the graph* wait for GG2f (they write the working set). (b) Two slices, GG4g1 Explore, GG4g2 Find connections.
2. **Where they sit.** One page per `FUNCTIONS.yaml` row (`apps/pages/server/pages.ts:133-136`). (a) **Two pages,
   `/cases/explore?case=<id>` and `/cases/connections?case=<id>`; the `graph-extras` row keeps Explore, and a new row
   `find-connections` takes the second**, as GR4a's board page was given its own row; both linked from the case's page.
   (b) One page with two parts.
3. **Paging.** (a) **By link, the route's own offset**: "The 10 most connected of 3,204", a link "Show the next 10" until
   "All 3,204 shown", as `spec/02` words it; one block paged at a time (the others keep their first page), each figure
   read once per render. (b) Everything on one long page: not proposed (rule 2 is met by the route's totals either way;
   the page would make up to 50 reads).
4. **A node in a figure.** (a) **Its name and type as text, no link, until GG3d gives a node a page** (its own question
   then); never its id (rule 7). (b) A link to a search for its name.
5. **What's new.** (a) **Loads said as "A load of {n} items and {m} links, {when}", with no recipe: `LoadSummary` carries only
   `recipe_id` and `recipe_version` and no name (`packages/schemas/explore.py:112-116`), and the React panel prints the id
   (`ExplorePanel.tsx:418-419`); an id is not shown (rule 7 forbids a source-system identifier; a recipe id is the
   deployment's own, but the page shows no id, as GG4a's rule), so the recipe waits for a name the route sends; no
   `load_id`; "confirmed by" and "marked by" left out** (the owner's ruling on who made a
   thing, 26 November, `RULINGS.md` :69); a mark's reason as written and "hides nothing yet". (b) The React rows whole,
   ids included: not proposed (rule 7 and the ruling).
6. **Groups past the cap.** (a) **The route's 409 `limit_exceeded` said with both figures, as `spec/02` :1166 words it
   ("a case too large to group says so with both figures"), and no option offered**: rule 2's three options (save a
   smaller view, filter, a batch job) are choices about what to put in a working set, and this read-only page cannot take
   any of them, so it names none it cannot carry out. The other blocks are still shown. (b) The three options in words,
   as BD8: not proposed (a choice the page cannot take).
7. **From and To, scripts off.** (a) **Two steps on one form: a name for each, matched by the case's suggest; the
   matches as radios for each end; then *Find connections***, the chosen ids carried in hidden fields only. (b) Ids typed:
   not proposed (rule 7).
8. **The degrees.** (a) **The fewest degrees first, then a link "Show routes at {n+1} degrees" to eight; each degree
   asked shows its own group, and the page re-asks each degree shown** (one `POST` per degree on the page, at most
   eight), so a longer route never hides a shorter one. (b) One degree at a time, the earlier ones gone.
9. **A route in words.** (a) **"{From} → Communicated with → {B} → Uses → {To}", the link type by its name in the case's
   model; "More routes at this degree than are shown (10 shown)." when `more`** (rule 2). "No route was found up to
   {searched_to} degrees." when `degree` is `None`; a hidden end is answered the same (the route's own rule 3). (b) A table
   of each route's nodes.
10. **Link types to follow.** (a) **Not offered in this slice** (every type, the route's default). (b) A checkbox list.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | What the case holds | a table of each entity type and its count and each link type and its count, types with none left out; "Counted at 09:05 UTC" from `computed_at` | the counts summed in the page into a total the route does not send |
| 2 | Most connected, `total` 3,204 | "The 10 most connected of 3,204" and "Show the next 10"; the next page asks `offset=10` | `total` read as the number of rows shown |
| 3 | The last page | "All 3,204 shown." and no next link | the next link drawn past `total` |
| 4 | By entity type, one type opened | its five most connected, paged the same way | the type's figure counted in the page |
| 5 | Busiest links | "R. Halloran → Clearwater Freight · Communicated with · 50 emails" (synthetic) | the ends looked up in another read |
| 6 | Groups past the cap (409 `limit_exceeded`) | both figures in words, no option offered; the other blocks drawn | a first part of the groups drawn |
| 7 | What's new | loads, confirmed and marked, each latest first with "The latest 10 of 14 loads"; no `load_id`, `recipe_id` or person's id | `confirmed_by` or `recipe_id` printed |
| 8 | No node or link id anywhere on the page | none | a node's id in a `data-` attribute |
| 9 | Find connections: names matched, ends chosen | one `POST .../connections` with exactly `{"source", "target"}`; the routes at the fewest degrees, in words | `_csrf` or the names in the body |
| 10 | Widen to 3 degrees | the groups at 2 and 3 both shown, one `POST` each | the 2-degree group dropped |
| 11 | `more` at a degree | the question 9 sentence | `more` dropped |
| 12 | No route up to the default reach (`CONNECTIONS_DEFAULT_REACH = 6`, `packages/schemas/domain.py:733`, :750-751) | "No route was found up to 6 degrees." from `searched_to` | `searched_to` replaced by a fixed figure |
| 13 | The same node chosen as From and To | the route's words ("From and To are the same node; choose two different ones") | the 422 shown raw |
| 14 | No level, another unit, no case, no `INVESTIGATE` | GR1a's 404 page for both pages | the 403 passed through |
| 15 | A body missing a field the models require (`TypeCounts`, `RankedNodes`, `RankedLinks`, `BusiestDays`, `Groups`, `WhatsNew`, `Connections`, `Path`) | "could not be read" | each required field removed in turn |
| 16 | The Conduit fails, or 401 | the 502 page; 401 says to sign in again | an empty figure |
| 17 | Keyboard and scripts off | every paging link and the connections form reachable and working (rule 13), the pages whole with scripts off (I4) | a link out of the tab order |

## Waits on

GR1a merged (the case's page); GG3a (its search words); question 0b for the merge before WS4b.

## Files touched

`spec/08` (scenario EX); `apps/pages/server/explore.ts` and `connections.ts` (new), `server/pageList.ts`,
`server/views/exploreWords.ts`; `tree-govuk/explore.njk`, `connections.njk`, `routes.yaml`; `apps/pages/FUNCTIONS.yaml`
(the `graph-extras` row's route, and the new `find-connections` row); `test/govuk/explore.test.ts`,
`connections.test.ts`, `exploreConduit.ts`, `keyboard/explore.spec.ts`, `scripts-off/explore.spec.ts`;
`tests/harness/test_pages_setting.py`'s route list; a scenario census test in `OspreyFlow_Build/tests/glass_trees/`;
`cases.njk` (the two links).

## Checks (frozen when cut)

GR1a's list.

## Out of scope

Starter questions and every action that puts a node on the graph (with GG2f); Shares contacts (the inspector's, GG3d);
the pathfinder (`POST .../paths`, B21's, which the row names but this slice does not use: a later question); any Conduit
change; `apps/workspace`.

## Corrections found on the way

- `FUNCTIONS.yaml:257` names scenario B21 for this row; B21 is the pathfinder (`POST .../paths`, `spec/08` :572), not
  Find connections (ADR-116). The row's scenario list needs EX, and B21 only if the pathfinder is put on this page.
- The pathfinder's audit row names no case (`app.py:9183-9188`, no `investigation_id`), though the route is under one;
  its comment (:9158) still says "Not investigation-scoped". A backlog note, not this slice's.
