# Slice GA1d · GA1 · A saved view's own conversation on the GOV.UK Ask page: read, asked in and reviewed in the view (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 26 November 2026, on the
branch `drafts/2026-11-26`. No row in `slices.tsv`; no builder starts from this paper. **Size S.**

**Where it comes from.** ADR-144 decision 4 (*Ask the model about these*: a question asked in a view reads the view's
documents alone, "and the conversation is kept with it"). GA1a's question 3 left a view's conversation for "the saved
views page (GR1's)"; GR1d drafts that page. GA1b asks and GA1c reviews in the case's own conversation; this slice does
the same in a view's.

## What exists today (read on `origin/main` at `042c882f2`; re-read, lines move)

- **The routes take the view as a query field.** `GET .../questions?view_id=…` (`list_questions_route`,
  `services/api/app.py:8353-8373`): "only for a reader who may see the view … 404 as for no view", by
  `views.get(investigation.id, view_id, principal.id)` first, then `read_in_view(view_id)` ("its proposals are read only
  through it"). `POST .../questions` takes `view_id` in its body (`ScopeRequest`, `services/api/questions.py:332-334`:
  "the model reads its Documents alone"); accept and reject take `view_id` as a query field (`app.py:8388`, :8418) and
  check the view the same way.
- **The scope rule.** `read_in_view` (`services/api/dataset_scope.py:384-387`) lets one request read what is kept with
  that view, "after the view store let the reader see the view"; `view_clause` keeps every other read to records kept
  with no view or with that one (:390 onward). **The case's conversation and each view's never mix**
  (`questions.py:574-585`, :679-689, as GA1a's draft read).
- **The React words**: "Asking in the view … private to you until you share it." (`QuestionsPanel.tsx:312`).

## Acceptance (red before, green after)

Scenario AC's view rows, written first, and `apps/pages/test/govuk/ask-view.test.ts`, red on GA1c's page, green after.

## Questions for the owner (the proposal first)

1. **Where it is reached.** (a) **From GR1d's list, "Ask about this view", opening the Ask page with the view named**
   (`/cases/ask?case=…&view=…`, the query form until GR1c), with the view's name in the heading and "Asked in the view
   *name*: the model reads only this view's documents". (b) A choice of view on the Ask page itself.
2. **What carries over.** (a) **GA1b's asking and GA1c's review work the same in a view, each sending `view_id`**, and
   nothing of the case's own conversation is shown on a view's page, nor the other way round. (b) Read-only in a view.
3. **A private view.** (a) **The React workspace's words, "private to you until you share it"**, above the form, when
   the view is not shared; the route already refuses a view the reader may not see as a missing one. (b) Your words.
4. **A view the reader may not see, or deleted meanwhile.** (a) **The same 404 page as a missing page** (the route's
   404 "as for no view"). (b) A sentence on the Ask page.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A view with two answers; the case with three | the view's page shows the two, the case's page the three; none on both | the page reading both conversations and merging them |
| 2 | Ask in the view | one `POST .../questions` with `view_id` and `read_from: "case"` (GA1b's) | `view_id` left out (the answer then lands in the case's conversation) |
| 3 | Accept a proposal in the view | one `POST .../accept?view_id=…` | `view_id` left off the query (the route then finds no such candidate: the fixture models it as a 404, as the real scope does) |
| 4 | Another person's private view | the same 404 page | "This view is private" (an oracle) |
| 5 | A view deleted meanwhile | the same 404 page | a stale page drawn |
| 6 | A private view of one's own | the private sentence | none shown |
| 7 | One render | exactly one `GET .../questions?view_id=…` | a second read without it |
| 8 | Keyboard and scripts off | the page whole and its forms working (rule 13, I4) | a form out of the tab order |

## Files touched

`spec/08` (AC's view rows); `apps/pages/server/ask.ts`, `server/views/askWords.ts`; `tree-govuk/ask.njk`; GR1d's list
template (the link); `test/govuk/ask-view.test.ts`, `askConduit.ts` (the view check and scope); the keyboard and
scripts-off specs.

## Checks (frozen when cut)

GA1a's list, with `csrf.test.ts` (I17).

## Out of scope

Saving an answer as a view ("Save as a view", GA1e); a selection's question (GG2e); any Conduit change.
