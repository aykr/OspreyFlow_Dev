# Slice GR4a · GR4 · Trends shown together: a pack's saved trends on one GOV.UK page, read-only (ruled by the owner, 25 November 2026)

**Status: ruled; an away round (D246).** It runs on the server's build account while the owner is away: **on the
branch `away/GR4a`, a commit at least every 15 minutes, nothing merged or pushed to the dev repository.** On the
owner's return he fetches `away/GR4a` from server-backup into this checkout; the conductor then starts GR4a from main
as any part, and **its round 1 merges `away/GR4a` in** (the owner's one exception to the 23 November rule, for D246's
away rounds only), so the Stop hook, the verifier and the merge judge it as any part's work.

## The owner's rulings (25 November 2026), which replace the questions below

1. **Read-only first:** one pack's trend items, in the pack's stored order, each as its figures drawn (plain SVG with
   classes and a table of the same figures), withheld items said as withheld (I21). Arranging is GR4b.
2. **The pack's own snapshots, with their counted-on date**, as the pack shows them; no live trend read.
3. **Whoever may read the pack now** (`record_assessment` for a working pack, `read_reports` for a published one);
   anyone else gets the same 404, words and status, as a pack that does not exist.
4. **"Trends shown together", at `/packs/{pack_id}/trends`** in the GOV.UK tree. No code, route or word reuses the
   drawing board's names.
5. **A new spec/08 scenario first** (TS), red first, from these rulings. **With the spec changes, correct ADR-152
   decision 10's citation** (`app.py:19494` is the trend preview route's right; a pack item names a trend at
   `packages/schemas/packs.py:128`, added through `app.py:19762`), with the decision log's own checks green.
6. **The page reads with the strict reader and the field census** the owner ruled for GR3a (a body missing a required
   field is "could not be read", never a zero; every field of the generated types drawn or named as left out), and its
   fixture models the real pack routes' shapes and refusals (rule 15).

## What exists today (a read-only scout, 25 November 2026)

- **The plan and ADR-152:** decision 10 (`spec/06_DECISIONS.md` about lines 41131 to 41134) and row D43 (about line
  40976): "'Build a report' on the GOV.UK theme is Trends and Packs as pages, and one new page, the **board**: a person
  arranges saved trends to view together. A board is a pack of trend items shown together on one page ... so it needs
  **no new Conduit route**." Invariant **I21** (about line 41243): "A board never shows a trend its viewer can no
  longer read, and says it is withheld rather than empty", test
  `test_a_board_shows_a_trend_its_viewer_can_no_longer_read_as_withheld_not_as_missing_data`, which no file has yet.
  (Decision 10 cites `app.py:19494` for "a pack item can already name a saved trend"; that line is the trend preview
  route's right. The field is `packages/schemas/packs.py:128`, the route `app.py:19762`. A one-line correction for the
  owner, with GR4a's other spec changes.)
- **Packs already order, withhold and refuse items.** `PackItem` (`packs.py:101`; `trend_id` at :112, a frozen
  `trend: TrendFigures` snapshot at :113, "the order of the list is the order"); `report_pack_items.position`
  (`services/api/packs.py:549`, listed `ORDER BY position` at :656); `PUT .../packs/{pack_id}/order`
  (`app.py:19912`, `reorder_visible` keeps withheld items' places, `packs.py:847` to 866); `readable()` returns the
  visible items in order and a withheld flag (`packs.py:127`, :750).
- **Rights:** trend routes `run_analysis` (Viewer); a pack's create, list, item and order routes `record_assessment`
  (Editor); published packs and the report route `read_reports` (Viewer) (`packages/schemas/rights.py:37`, 39, 90;
  `spec/02` about lines 1749 to 1752).
- **Saved trends have no order of their own** (`TrendDefinition`, `packages/schemas/trends.py:54`, listed by
  `created_at`). An arrangement of trends outside a pack would need a new field or route, which the plan rules out.
- **The React workspace:** `apps/workspace/src/reports/TrendsTab.tsx`, `TrendChart.tsx`, `PacksTab.tsx` (reorder at
  :146), `PublishedTab.tsx`, `PackItemView.tsx`. Clients in plain TypeScript already in
  `packages/glass-shared/src/reports/trendsApi.ts` and `packsApi.ts`; `packText.ts` `trendSentence` (:54).
- **The GOV.UK pattern:** a `server/<page>.ts` `PageModule`, its row in `server/pageList.ts`, its path in
  `tree-govuk/routes.yaml`, a words file in `server/views/`, a `.njk` in `tree-govuk/`; the route list pinned in four
  places (`test_pages_setting.py` about line 2352, `test_tree_parity.py`, `test_govuk_help_scenario.py`, HP9 in
  `help.test.ts`). GR3a (alert monitoring) is the nearest example, still on its branch.
- **"Board" already names the drawing board** (ADR-143: `services/api/boards.py`, `/boards` routes, `spec/02` about
  line 617). The page must not reuse those names in code, routes or words.
- **No acceptance scenario** for a GOV.UK trends page, packs page or board exists in `spec/08` (only C12, the
  Glass's). A missing scenario is the first item (the owner's rule for IS2 and the GR parts).

## The questions as put to the owner (ruled above: each (a), the proposal, was chosen)

1. **Scope of the first slice.** (a) **Read-only:** one pack's trend items, in the pack's stored order, each as its
   figures drawn (plain SVG with classes and a table of the same figures, as GR3a), withheld items said as withheld
   (I21); arranging stays in the Glass for now; GR4b adds arranging. (b) Read and arrange in one slice (a GOV.UK form
   posting the pack's new order to the existing order route).
2. **Live figures or the pack's snapshots.** A pack item's trend is frozen at add time (refresh is its own route).
   (a) **The pack's own snapshots, with their "counted on" date,** as the pack shows them; (b) each trend's live
   figures, read through the trend route (`run_analysis`), the pack giving only the order.
3. **Who may open it.** (a) **Whoever may read the pack now** (`record_assessment` for a working pack; `read_reports`
   for a published one), and anyone else gets the same 404 as a pack that does not exist (as your ruling 7 for the
   report route); (b) published packs only, `read_reports`.
4. **Its name and path.** "Board" collides with the drawing board. (a) **"Trends shown together"**, at
   `/packs/{pack_id}/trends` in the GOV.UK tree; (b) your words.
5. **The scenario:** a new `spec/08` scenario (say **TS**) written first, red first, from your answers.

## The table of cases (each red first, planted faults at the real call site: rule 15)

| # | Case | Expected |
| --- | --- | --- |
| 1 | A pack with three trend items, in a stored order other than creation order | the three trends, in the pack's order, each with its title, its period, a chart and a table of the same figures |
| 2 | A pack whose middle item the reader can no longer read | that item's place says it is withheld, in words, with no figure and no title; the others shown (I21) |
| 3 | A pack with no trend items (only notes or assessments) | a sentence saying the pack has no trends, and a link back; never an empty chart |
| 4 | A reader without the right to read the pack | the same 404 page, words and status, as a pack that does not exist (no "forbidden", no right named) |
| 5 | A pack in another case the reader cannot see | the same 404 |
| 6 | The Conduit gives no answer, or 401 | the 502 "could not be read" page; an ended session says to sign in again (as AD3a's AP4) |
| 7 | A body missing a field the generated types require | the "could not be read" answer, never a zero (the owner's (A) for GR3a, carried to every GOV.UK page) |
| 8 | Keyboard | every link and control reachable and working by keyboard, in a `keyboard/` spec per tree (rule 13) |
| 9 | No script | the page whole with scripts off: no control that needs one |

## Checks (to be frozen at the start)

GR3a's list, adapted: the pages workspace tests, lint, typecheck, `no_react_check.mjs`; the new scenario's test, the
page's tests, `test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`, `test_pages_foundation.py`,
`test_design_gates_reach.py`, `test_ui_words_check.py`, `test_copy_says_no_client.py`, `test_doc_citations_check.py`,
**`tests/harness/test_pages_setting.py`** (the route list), `ruff check .`, `design_check`, `colour_drift_check`. Its
fixture models the real pack routes' refusals and shapes (rule 15); when GR3b lands, its answers come from the real
routes.

## Out of scope

Arranging (if 1(a)); creating, editing or publishing packs; new kinds of figure; any new Conduit route; the drawing
board.
