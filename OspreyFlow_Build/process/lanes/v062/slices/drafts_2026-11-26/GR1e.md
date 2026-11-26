# Slice GR1e · GR1 · A case's history as a GOV.UK page, read-only: each step's fixed label and when it was made (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper. **Size S.**

**Where it comes from.** The plan's row "GR1: Cases, case brief, saved views, history (R5)"; `FUNCTIONS.yaml` row
`cases-and-views` names `apps/workspace/src/history/`. ADR-124 decision 8 (no size on a step), ADR-128 (a brief edit
holds no canvas snapshot).

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The read.** `GET /v1/investigations/{id}/history` (`get_investigation_history`, `services/api/app.py:6486-6503`):
  `require_right(INVESTIGATE)` and the case's viewer gate; audited `get_history`. It answers `list[HistoryStepSummary]`
  (`services/api/history.py:125-137`): `id`, `label`, `created_at`, `restorable`, "**metadata only: no node or edge
  bodies, and no size either** (ADR-124 decision 8). A step's size was counted over the stored snapshot, which is
  unfiltered, so it was a figure for material the reader may not be entitled to read. The label is fixed text
  (`history_labels.py`)." A label that is not fixed text is shown as `Changed` (`history.py:249-251`). The steps are the
  case's, in order (`list_steps`, :241-257).
- **Restore.** `POST .../history/{step_id}` (:6507 onward): `INVESTIGATE` and the **Editor** gate; it re-projects the
  step's stored bodies for the restorer ("never the visibility `step` was recorded with") into the case's working set,
  and refuses a step that is not restorable (409 `step_not_restorable`). **Restoring changes the working set, which no
  GOV.UK page shows until GG2e.**
- **The React panel.** `apps/workspace/src/history/HistoryPanel.tsx` and `lastChange.ts`.
- **One page per row** (`apps/pages/server/pages.ts:133-136`): until GR1c, history is a part of the case's page.

## Acceptance (red before, green after)

Scenario CS's history rows, written first, and `apps/pages/test/govuk/case-history.test.ts`, red on GR1a's page, green
after.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **Read-only: each step's label and its time, newest first or in the route's order (question 2), and
   whether it can be restored, said in words.** Restore waits for GG2e, where the person can see what it changed. (b)
   Restore as a form now, with "the case's graph was put back to this step" and nothing to show it.
2. **The order.** (a) **The route's order (oldest first, `seq`)**, as GR1a kept the Conduit's order (its question 5).
   (b) Newest first, reversed by the page.
3. **Where it sits.** (a) **A "History" part of the case's page** (GR1a's), linked from the page's contents, until GR1c
   gives `/cases/{case_id}/history`. (b) A page of its own now: not possible under the one-page-per-row rule.
4. **A long history.** The route sends every step, with no paging. (a) **All shown**, since each row is a fixed label and
   a time; the builder measures the largest synthetic world's count and reports it. If the route can send more than a
   page can draw well, that is a later Conduit paging part (an amendment). (b) The page shows the latest 100 and says
   so: a page-side slice of a whole answer, **not proposed** (rule 2: the cut would be the page's, not the route's).

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A case with five steps, one a brief edit | five rows, each its fixed label and time; the brief edit "cannot be restored" | the brief edit said as restorable |
| 2 | A label not in the fixed list (the fixture sends what the route would send: `Changed`) | "Changed" | the page mapping labels of its own |
| 3 | No steps | "Nothing has changed in this case yet" | an empty table |
| 4 | No size, no count | no number about a step's contents anywhere | a count of steps' nodes from another read |
| 5 | No level, another unit, no case, no `INVESTIGATE` | GR1a's 404 page | the 403 passed through |
| 6 | One render | exactly one `GET .../history` (one audit row) | a second read |
| 7 | A body missing a field `HistoryStepSummary` requires | "could not be read" | each required field removed in turn |
| 8 | No step id on the page | none | an id printed |
| 9 | The Conduit gives no answer, or 401 | the 502 page; 401 says to sign in again | an empty history |
| 10 | Keyboard and scripts off | the part whole (rule 13, I4) | a link out of the tab order |

## Files touched

`spec/08` (CS's history rows); `apps/pages/server/cases.ts`, `server/views/casesWords.ts`; `tree-govuk/cases.njk` and a
history partial; `test/govuk/case-history.test.ts`, `casesConduit.ts` (the history route and its refusals); the scenario
test's census of `HistoryStepSummary`.

## Checks (frozen when cut)

GR1a's list.

## Out of scope

Restore (with GG2e); the brief's own edit history; any Conduit change; `apps/workspace`.
