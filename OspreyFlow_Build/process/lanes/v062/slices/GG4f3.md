# Slice GG4f3 · GG4 · *Promote…* from a board, scripts off: the sheet, the ticks, one load, and *Promotions from this board* (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a` and from `away/GG4a`. No row in `slices.tsv`; no builder
starts from this paper. **Size M.** The third of GG4f's three parts.

**Where it comes from.** ADR-143 decision 8 (`spec/06_DECISIONS.md` :26650-26659): "*Promote…* opens a sheet listing the
board's drawn items not yet promoted, each ticked or not; links follow their items and go only when both ends will be
in the dataset … The sheet shows: what goes; the checks …; undecided matches as warnings; and how it will be recorded.
Promoting writes **one load** … it stays `analyst_drawn` for good". Decision 10 (:26667-26672): "The analyst sees the
outcome on the board's *Promotions from this board* list". Decision 13 (:26682-26686): under GOV.UK "the promotion
sheet's lists as a summary list". ADR-145 decision 8 (a dataset's policy: the Author promotes, or a second person
reviews).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The routes** (`OspreyFlow_Core/services/api/app.py`). `_PROMOTES` is `promote_to_dataset` and `investigate`
  (:5406-5409), with the case's **Author** level (`InvestigationAuthorDep`):
  - `GET .../boards/{board_id}/promotion-sheet` (`promotion_sheet`, :5511-5525), `own_board` first: `PromotionSheet`
    (`packages/schemas/promotions.py`): `board_id`, `dataset_id`, `dataset_name`, `highest_marking`, `policy`
    (`author_promotes` or `second_person_reviews`), `items` (`SheetItem`: `item_id`, `element_id`, `kind` one of node,
    link, picture, match, `type`, `label`, `marking`, `follows`, `source`, `target`, `problems`), `checks`
    (`PromotionCheck`: `name`, `passed`, `words`), `warnings`, `recorded_as` (words), `refused` (words, when nothing on the
    board can be promoted). All `extra="forbid"`.
  - `POST .../boards/{board_id}/promotions` (`promote_drawn_items`, :5528-5552), 201, body `PromotionInput` (`item_ids`, 1
    to 500, `extra="forbid"`): "every check run again here, then one load, committed at once or sent for review"; audited
    `promote_drawn_items`; answers a `Promotion`.
  - `GET .../boards/{board_id}/promotions` (`list_board_promotions`, :5555-5582), behind `_READS_BOARDS` and the
    **Viewer** gate: every reader of the board; "a promotion carrying an item above the reader's clearance is not listed to
    them, in the store's query; each listed with the counts of what this reader is shown".
- **What `promote` refuses** (`services/api/promotions.py:602-622`, `_plan` :480-544, `_record` :546-600): **409
  `nothing_to_promote_into`** with the target's own words (a case reading no dataset, a drawn dataset, a composite:
  `_target`, :214 onward); an unknown ticked id is `ItemNotFound`; **422 `check_failed`** "… cannot be promoted: {first
  problem}" (:496-502); **422 `nothing_goes`** "Nothing ticked can be promoted: see what was left out and why."
  (:562-566); `AboveTheDeploymentCeiling` before the record (:206-212, :590). Handlers: `PromotionRefused` sends `error`
  and `detail` (:5469-5471); `PromotionNotFound` a 404 (:5474-5479).
- **A `Promotion`** (`packages/schemas/promotions.py:108-145`): ids (`id`, `load_id`, `dataset_id`, `case_id`, `board_id`,
  `proposed_by`, `reviewed_by`), names (`dataset_name`, `case_name`, **`proposed_by_name`, `reviewed_by_name`**, resolved
  by the Conduit from `principal_names.display_names`, `app.py:5460`), `proposed_at`, `status` (`awaiting_review`,
  `committed`, `rejected`, `reverted`, :37), `reviewed_at`, `reason`, `nodes`, `links`, `left_out` ("given to its proposer
  alone", :137-138), `revert_command` (an operator command, for a reader holding `revert_loads`, :139-142), `may_review`,
  `why_not`.
- **`may_promote`** on the opened board is "exactly the promotion routes' check" (`app.py:5054-5059`, `_may_promote`
  :5082-5095).
- **The React sheet** (`apps/workspace/src/boards/PromoteSheet.tsx`, 231 lines): "Nothing here is waiting to be
  promoted.", "Left out, and why", the GOV.UK error summary; ticks start as every item with no problem
  (`startingTicks`); the shared words `STATUS_WORDS` ("Waiting for review", "Committed", "Rejected", "Reverted") and
  `addsInWords` ("2 items and 1 link") are plain TypeScript in `packages/glass-shared/src/boards/promotionsApi.ts:69-88`.
  After a promotion: "Promoted into {dataset}." or "Sent for review into {dataset}." (`BoardEditor.tsx:619`).

## Acceptance (red before, green after)

Scenario BD's promotion rows (after GG4f2's), written first, and `apps/pages/test/govuk/boards-promote.test.ts`, red on
GG4f2's page, green after; every earlier BD row unchanged and green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **The sheet, promoting the ticked items, and *Promotions from this board* (read-only).** Reviewing,
   approving and reverting are the Studio's (*Analyst promotions*, decision 10), not the board's. (b) The list alone first.
2. **Where it sits.** (a) **The sheet at the board page with `&promote=1`** (one page, the `drawing-boards` row), offered
   by a link only when `may_promote`; *Promotions from this board* as a part of the board page for every reader. (b) A
   page of its own (a new row).
3. **The ticks with scripts off.** (a) **GOV.UK checkboxes, each item with no problem ticked at the start (the shared
   `startingTicks`), each item with a problem shown unticked and disabled with its problems in words; links, pictures and
   match decisions that `follows` are listed beneath their items as "Goes with its items" with no box**, as the route
   decides them. (b) Every box unticked at the start.
4. **Undecided matches and a *Same*.** (a) **The route's `warnings` said as they come, in a GOV.UK warning text**, and
   one fixed sentence above the button when a match decision goes: "A *Same* that goes into the dataset is read by every
   case that reads it." (`promotions.py:628-630`). (b) The warnings alone.
5. **After promoting.** (a) **`303` to the board with the banner "Promoted into {dataset_name}." or "Sent for review into
   {dataset_name}."** as the React editor says it, and what goes in words (`addsInWords`); then *Left out, and why* from
   the answer's `left_out` (the proposer's alone), every one listed (rule 2). (b) The banner alone.
6. **Who proposed and who reviewed.** The route sends names. (a) **Not shown in 0.7.0**, as the owner's ruling on who made
   a case, a board or a view (26 November, `RULINGS.md` :69); the backlog part that adds names takes these too. (b)
   Shown, since the Conduit already resolves them.
7. **The revert command and ids.** (a) **Never shown on this page**: `revert_command` is an operator's, in the Studio's
   Runs; `load_id` and every id stay off the page (rule 7). (b) The command shown to a reader holding `revert_loads`.
8. **Refusals.** (a) **`nothing_to_promote_into` and `refused`: the route's own words** (they are written for the
   person); `check_failed` and `nothing_goes` the route's words above the sheet, the ticks kept; `ItemNotFound`, `not_the_boards_creator` and a level refusal the board's 404 page. (b) Page
   sentences of its own for each.
8b. **The deployment ceiling's words** **(owner: security).** A sheet item's problem and the write-side refusal name the
   deployment's highest marking: "above this deployment's highest marking, {ceiling.marking}." (`promotions.py:204`;
   `AboveTheDeploymentCeiling(ceiling.marking, …)`, :212). The GG4j ruling (a refusal names only the capped ceiling the
   board already sent the reader, `RULINGS.md` :46) is about the case's ceiling; whether it covers the deployment's is not
   said. A deployment's highest marking may sit above a reader's clearance. (a) **The page says these words as the route
   sends them only once the owner confirms the deployment's highest marking is not withheld from any signed-in reader;
   until then the page says "above the highest marking this deployment holds", naming none.** (b) The route's words as
   sent.
9. **More than 500 ticked.** `PromotionInput` takes at most 500 (`packages/schemas/promotions.py:97`). (a) **The page
   says before sending: "You can promote up to 500 items at once. Untick some and promote the rest after."**, with the
   count ticked; nothing sent. (b) Send and say the 422: not proposed (a cap the page knows is said before, not after).

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A reader with `may_promote` | the *Promote…* link; a reader without it sees none | the link drawn from the case's level alone |
| 2 | The sheet: two items, one failing "Not graded", a link between them, a match decision | the first ticked; the second unticked, disabled, "Not graded" said; the link and the match "Goes with its items"; the checks as a summary list with each `words` | the failing item ticked and sent |
| 3 | Promote with the first ticked | one `POST .../promotions` with exactly `{"item_ids": [<first>]}`; `303`; "Promoted into Port records." (a synthetic dataset name) and "1 item" | `_csrf` or the `follows` items in the body (`extra="forbid"`; links are the route's to decide) |
| 4 | A dataset that reviews (`second_person_reviews`) | "Sent for review into Port records." | the banner read from the policy rather than the answer's `status` |
| 5 | `left_out` in the answer | each item and its reason under *Left out, and why* | the list cut to the first few |
| 6 | `refused` on the sheet (a case reading no dataset) | the route's words; no form, no button | an empty sheet with a button |
| 7 | `check_failed` (the item changed since the sheet was read) | the route's words above the sheet; ticks kept; nothing promoted | the 422 shown as the 404 page |
| 8 | `warnings` and a match decision going | the warnings and the fixed *Same* sentence | the sentence shown with no match decision going |
| 9 | 501 ticked by hand | question 9's sentence; nothing sent | the post sent |
| 10 | *Promotions from this board* for another reader | each promotion's dataset, status in `STATUS_WORDS`, counts in `addsInWords` and when, in the route's order; no name, no id, no command | `proposed_by_name` or `revert_command` drawn |
| 11 | No promotion yet | "Nothing has been promoted from this board yet." and no table | an empty table |
| 12 | Another reader's sheet (403 `not_the_boards_creator`), and a reader below the Author level (403 from the level gate, `app.py:2944-2946`) | both shown as the board's 404 page | either said in words |
| 13 | No `_csrf` | refused, nothing sent (I17) | the post outside the check |
| 14 | A body missing a field `PromotionSheet`, `SheetItem`, `PromotionCheck`, `Promotion`, `LeftOut` or `Promotions` requires | "could not be read" | each required field removed in turn |
| 15 | One render of the sheet | one `GET` of the board and one of the sheet; the post sends one `POST` | a read of the list on the sheet's page |
| 16 | Keyboard and scripts off | the sheet's boxes and button reachable and working, one case in `keyboard/boards.spec.ts` (rule 13); the sheet whole with scripts off | a disabled box left in the tab order |
| 17 | The fixture | refuses as the routes do (`_PROMOTES`' rights, Author level, `own_board`, then `promote`'s checks in order) and lists to a reader only promotions within their clearance | a fixture listing a promotion above the reader's clearance |

## Waits on

GG4f2 (the board page's parts); GG4c, GG4b and GG4j merged; the owner on question 8b.

## Files touched

`spec/08` (BD's promotion rows); `apps/pages/server/boards.ts`, `server/views/boardsWords.ts` (using `STATUS_WORDS`,
`addsInWords` and `startingTicks` from `glass-shared`, never written again); `tree-govuk/boards.njk` and a sheet
template; `test/govuk/boards-promote.test.ts`, `boardsConduit.ts`, `keyboard/boards.spec.ts`,
`scripts-off/boards.spec.ts`; `OspreyFlow_Build/tests/glass_trees/test_govuk_boards_scenario.py` (the promotion models in
the census).

## Checks (frozen when cut)

GG4c's list.

## Out of scope

Review, approval, rejection and revert (the Studio's *Analyst promotions*, `studio-runs-promotions`); a drawn dataset's
merge (`studio-runs-drawn-merge`); any Conduit change; `apps/workspace`.
