# Slice GR1d · GR1 · A case's saved views as a GOV.UK page: the list the reader may see, saving a filtered view, sharing and deleting, scripts off (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper.

**Where it comes from.** The plan's row "GR1: Cases, case brief, saved views, history (R5)", `FUNCTIONS.yaml` row
`cases-and-views`. ADR-144 (a view is "a saved lens on a case", re-read each time it opens through the reader's own
principal). GG2b (drafted 25 November) opens one view at `/cases/{case_id}/views/{view_id}`; **nothing yet lists them**,
and GA1d (a view's conversation) and GG4c's "a board from a view" both need a way to choose one.

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The routes** (`services/api/app.py`). The comment above them (:4780-4781): "Saving, sharing and deleting need
  `investigate`, the Viewer's right to work the case; **listing and opening need only the level.**"
  - `GET .../views` (`list_case_views`, :4784-4797), the viewer gate only: "their own, and those shared with the case",
    each with its `first_item` as this reader may see it, never a hidden one.
  - `POST .../views` (`save_case_view`, :4800-4818), `INVESTIGATE`, the **viewer** gate, 201; audited
    `save_case_view`.
  - `GET .../views/{view_id}` (`open_case_view`, :4874-4900), the viewer gate only. **This answers GG2b's question 8:
    the missing `require_right` is deliberate, by the comment at :4780-4781.**
  - `POST .../views/{view_id}/share` (:4905) and `DELETE .../views/{view_id}` (:4929), `INVESTIGATE`.
- **The shapes** (`packages/schemas/case_views.py`).
  - `CaseView` (:73-109): `id`, `case_id`, `name`, `created_by`, `created_at`, `shared`, **`chosen`** ("how many of
    its chosen nodes *this reader* may see now … never the count its creator stored", C045), `first_item`, `filter`,
    `window`, `threshold`, **`drawing`** (a board), `converted_from_case`, `merged_load`. "What it never carries: the
    chosen nodes' ids or their positions."
  - `CaseViewInput` (:53-70): `name` 1 to 200; **exactly one of `node_ids` or `filter`**; `layout`, `window`,
    `threshold` (0 to 1). `ViewFilter` (:25-41): `entity_types`, `valid_from`, `valid_to`; "choose entity types, a date
    window, or both"; "the window ends before it starts".
- **So a filtered view can be saved with no canvas**, from a form; a view of chosen nodes needs a selection (GG2e).
- **The React screens.** `apps/workspace/src/views/`: `ViewsPanel.tsx`, `SaveViewForm.tsx`, `SavedViewOnTheLine.tsx`,
  `lens.ts`, `lensHandoff.ts`.
- **One page per row** (`apps/pages/server/pages.ts:133-136`): until GR1c, the list is a part of `/cases?case=<id>` or
  `/cases?case=<id>&views=1`, not a page of its own.

## Acceptance (red before, green after)

Scenario CS's views rows (after GR1b's), written first, and `apps/pages/test/govuk/case-views.test.ts`, red on GR1a's
page, green after.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **The list; saving a filtered view (entity types, a date window, or both); sharing and deleting one's
   own.** Saving a chosen set of nodes waits for the canvas (GG2e). (b) The list alone.
2. **Boards in the list.** A board is a view with `drawing` true, and **the route already leaves boards out**: the
   store lists with `drawing = $3` false (`services/api/case_views.py:407-419`). (a) **The list says "Drawing boards are
   listed on the case's boards page", with a link.** (b) Nothing about boards.
3. **What a row says.** (a) **The view's name as a link to GG2b's page; "shared with the case" or "only you"; for a view of
   chosen nodes, "N items you can see" from `chosen` and its `first_item`; for a filtered one, its filter in words** ("People and
   vehicles, from 1 March to 30 April 2026", synthetic). Never the creator's count (C045). Until GG2b merges, the name is
   not a link. (b) Your list.
4. **Who made a view.** `created_by` is an account's id, as in GR1a's question 2 and GG4a's question 2. (a) **The ruling
   on those covers this** (built as left out until then). (b) Your words.
5. **Saving a filtered view.** (a) **A form with the name, the case model's entity types as checkboxes and a date
   window as GOV.UK date inputs**, sending `filter` and nothing else; `node_ids` is never sent; the route's two
   refusals are said in words against their fields. The builder reads where the case's entity types come from (a route
   the page may read); **if none, the form offers the date window alone, and says so**. (b) Not in GR1d.
6. **Share and delete.** (a) **Offered only on the reader's own views** (`created_by` equal to the reader, read from
   `GET /v1/me` as the Studio does), share with "it cannot be undone" if no unshare route exists (the builder reads),
   delete after a confirmation page ("Deleting a view deletes nothing else"). (b) Offered to all, the refusal said.
7. **Where it sits.** (a) **On the case's page, below the brief, as "Saved views"**, a part of GR1a's page until GR1c;
   with GR1c, `/cases/{case_id}/views`. (b) A page of its own now: impossible under the one-page-per-row rule.
8. **Converted and merged views** (`converted_from_case`, `merged_load`). (a) **Said in words** ("made from the case
   this view replaced", "a drawing merged into the dataset"), with nothing more. (b) Left out, named in the census.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | Three views: the reader's private one, a shared one of another's, a filtered one | three rows in the route's order, each with its words | a view of another's that is not shared (the fixture sends none, as the route does; the page must not add one from another read) |
| 2 | A shared view of 40 chosen nodes, 12 of which the reader may see (the route sends `chosen: 12`) | "12 items you can see" | `chosen` read as the view's size ("a view of 12 items"), which would be wrong for every other reader |
| 3 | `first_item` absent | no first item said, no "hidden" | "1 hidden item" |
| 4 | Boards on the case | the sentence with the link; the list holds no board (the fixture, like the store, sends none) | the sentence missing |
| 5 | Save a filtered view of two types and a window | one `POST .../views` with `name` and `filter` only | `node_ids: []` sent too (the route refuses both) |
| 6 | A window ending before it starts | the error summary against the date fields, nothing sent | the 422's detail |
| 7 | Neither types nor dates | the error summary: "choose entity types, a date window, or both" in the page's words | the post sent |
| 8 | Share one's own view | one `POST .../share`; `303`; "shared with the case" | the button shown on another's view |
| 9 | Delete after confirmation | one `DELETE`; `303`; the banner | the delete on the first click |
| 10 | No level, another unit, no case | GR1a's 404 page | the list read before the case gate |
| 11 | A reader without `INVESTIGATE` | the list shown (the level suffices); no save, share or delete offered; a hand post said as "You cannot save views in this case" | the list hidden (the route lists to the level alone) |
| 12 | A body missing a field `CaseView` requires | "could not be read" | each required field removed in turn |
| 13 | No `_csrf` on a write | refused (I17) | the route outside the check |
| 14 | Keyboard and scripts off | every link and form reachable and working (rule 13, I4) | a form out of the tab order |

## Files touched

`spec/08` (CS's views rows); `apps/pages/server/cases.ts` (the views part and its `POST`), `server/views/casesWords.ts`;
`tree-govuk/cases.njk` and a views partial; `test/govuk/case-views.test.ts`, `casesConduit.ts` (the views routes and
their refusals), `keyboard/cases.spec.ts`, `scripts-off/cases.spec.ts`; the scenario test's census of `CaseView`,
`CaseViewInput` and `ViewFilter`.

## Checks (frozen when cut)

GR1a's list, with `csrf.test.ts` (I17) over the new `POST`.

## Out of scope

Opening a view (GG2b); saving a chosen set of nodes (with GG2e); a view's conversation (GA1d); boards from a view
(GG4c's question 1); history (GR1e); `apps/workspace`.
