# Slice GA1e · GA1 · "Show all on graph" and "Save as a view" under an Ask & Chat answer on the GOV.UK pages (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a` and from `away/GR1d`. No row in `slices.tsv`; no builder
starts from this paper. **Size S.** The two forms draw nothing with Sigma, but *Show all on graph* ends on GG2e's live
page, which merges after WS4b (decision 9), so **this slice merges after GG2e** (question 5).

**Where it comes from.** The plan's row GA1e ("*Show all on graph* and *Save as a view* from an answer"; depends on GA1a,
GG2e and GR1d); the `ask-chat` row of `apps/pages/FUNCTIONS.yaml` (:237 onward); v0.6.0 #5 and ADR-145 Amendment 17 as the
React workspace built them. GA1a (cut) left both out ("'Show all on graph' and 'Save as a view'": `slices/GA1a.md`, Out of
scope). It follows GR1d's write pattern (a page `POST` with `_csrf`, one Conduit call, a `303`, the sentence carried in
the session so a link cannot forge it: `away/GR1d`'s report).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The answer's ids.** `GET .../questions` (`services/api/app.py:8352-8373`, `INVESTIGATE`, Viewer gate) answers
  `list[QuestionAnswer]` (`services/api/questions.py:283-308`), the whole conversation, with **no read of one answer**.
  Each answer carries `graph_citations` (`GraphCitation`, :202-213: `node_ids`, `link_ids`, "The model is never given
  these ids (rule 7)") and `search_citations` (`SearchCitation`, :216-229: `node_ids`), "those the reader may see".
- **The React side** (`apps/workspace/src/questions/AnswerActions.tsx`, 82 lines): `answerIds(entry)` collects every
  node and link id the markers stand for, each once, graph facts then search records (:17-28); `answerViewName` makes
  "Answer: ‹question cut at 72›" or "Answer from Ask & Chat" (:31-35); the actions are shown only when there are ids,
  and *Save as a view* only when there is a node (:49-52). `App.tsx:773-808`: *Show all on graph* closes an open view
  first, puts the items on the case's canvas by id, then **selects them and brings them into view**, and says how many
  are not shown, never which; past the cap nothing is added and the refusal is said, "*Save as a view* beside it is the
  way to keep them all (rule 2)". *Save as a view* saves the nodes as a private view and says "Saved as a view: ‹name›.
  Open it from Saved views."
- **The routes.** `POST .../working-set/add-by-ids` (`app.py:5688-5722`): `INVESTIGATE` and **Editor**;
  `{node_ids, link_ids}` (at most 50,000 and 250,000, :5638-5643), each read through the Vault for this reader, a link
  kept only where both its ends are readable and on the canvas or in the add; answers `AddedByIds`: the outcome and
  `not_shown`, a count, never which (`services/api/working_set/models.py:342-351`); past the cap the 409
  `limit_exceeded`. `POST .../views` (:4803-4825): `INVESTIGATE` and the **Viewer** gate, `CaseViewInput`
  (`packages/schemas/case_views.py`): `name` 1 to 200, `node_ids` at most 10,000; private to its creator until shared.
- **The answer page** is GA1a's `/cases/ask?case=…` (`slices/GA1a.md`, point 4). GR1d's views list links each view to
  `/cases/views?case=…&view=…` (GG2b's form, `away/GR1d`'s report).

## Acceptance (red before, green after)

Scenario **AC**'s rows for the two actions (after GA1a's), written first; `apps/pages/test/govuk/ask-actions.test.ts`
(the forms, scripts off) and one Playwright case from an answer to the live graph with the items selected, red on GA1a's
page, green after; GA1a's rows unchanged and green.

## Questions for the owner (the proposal first)

1. **What the form carries.** (a) **Only the answer's own id, in a hidden field.** The server half reads the
   conversation once (`GET .../questions`), finds that answer, and works out the ids with `answerIds`, moved to
   `glass-shared` with `answerViewName` (I11; the React file re-pointed, behaviour unchanged). No node or link id is ever
   on the page, and none can be forged into the add (rule 7). An answer id not in the reader's conversation is the 404
   page. (b) The ids in hidden fields: not proposed.
2. **Show all on graph.** (a) **One `POST .../working-set/add-by-ids` with the answer's ids, then `303` to
   `/cases/graph?case=…&answer=<answer id>`**; the module reads the conversation once through the forwarder and selects
   and brings into view those of the answer's nodes now in its store, as the React does. The banner says "‹n› items put
   on the case's graph." and, when `not_shown` is above 0, "‹k› could not be shown.", never which. Past the cap, GG2f1's
   refusal page with the three choices, *Save as a view* first ("the way to keep them all"). (b) No selection on arrival:
   the React selects them, so this would be a parity difference, a line in `PARITY_EXCEPTIONS.yaml` (the owner's file).
3. **Who is offered what.** (a) **As the routes are: *Show all on graph* to an Editor and above, *Save as a view* to
   every reader holding `investigate`**, the level read from the case list as GR1a reads it and the right from
   `GET /v1/me/rights` (`app.py:20664`), both routes requiring `require_right(INVESTIGATE)`; a hand post below Editor gets
   the route's 403 in the page's words. (b) Both to Editors only.
4. **Save as a view.** (a) **A small form: the name, filled with `answerViewName`, then one `POST .../views` with the
   answer's node ids alone (no layout, no window)**, then `303` back to the answer with "Saved as a view: ‹name›." and a
   link to it. More than 10,000 nodes is refused on the page with the figure, never cut (rule 2). Not offered for an
   answer with links and no nodes (as the React). (b) Saved with no name asked.
5. **Merge order.** (a) **After GG2e**, since *Show all on graph* has no page to land on before. (b) *Save as a view*
   alone first (it draws nothing and the `ask-chat` row is R5, not held by decision 9), *Show all on graph* after GG2e.
6. **With scripts off.** (a) **Both forms work with scripts off**; *Show all on graph* then lands on GG2e's parity
   sentence, after the banner, with a link to the case's saved views. (b) Offered only with scripts on.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | An answer citing two graph facts and one search record (synthetic: "Pier office", "J. Ashdown") | both actions offered | the actions offered on an answer with no ids |
| 2 | Show all, by an Editor | one `GET .../questions`, one `POST .../working-set/add-by-ids` whose ids equal `answerIds` of that answer, each once; `303` to the live graph with `answer=` | the ids of every answer in the conversation sent |
| 3 | The live page after it | the answer's nodes selected and in view | none selected |
| 4 | `not_shown: 2` | "2 could not be shown."; no id, no name | the missing ones named |
| 5 | Past the cap (409) | the three choices, *Save as a view* first; nothing added | a part of the ids sent again to fit |
| 6 | Save as a view | the name filled as `answerViewName` gives; one `POST .../views` with `{name, node_ids}` and nothing else; the sentence and the link | a `layout` or `filter` sent |
| 7 | An answer with links and no nodes | *Save as a view* not offered; *Show all on graph* offered | save offered and refused by the route |
| 8 | 10,001 nodes | refused on the page with the figure; nothing sent | the first 10,000 sent |
| 9 | An answer id not in the reader's conversation, or empty, or repeated | GR1a's 404 page; nothing written | the add sent with no ids |
| 10 | A Viewer | *Save as a view* only; a hand post of Show all gets the 403 in words | Show all offered by the page |
| 11 | No node or link id in the HTML | none (only the answer's id, in a hidden field) | a node or link id written into a hidden field |
| 12 | No `_csrf` | refused, nothing sent (I17) | a handler outside the check |
| 13 | I11 | the moved `answerIds` and `answerViewName` unit tests pass in `glass-shared`; the React suite unchanged | a behaviour change in the move |
| 14 | Keyboard and scripts off | each form reachable and working (rule 13, I4) | a button out of the tab order |

## Waits on

GA1a (the answer page); GG2e (the live page *Show all on graph* lands on, and its selection); GG2f1 (its refusal page,
for the cap); GR1d (the write pattern); GG2b (`/cases/views?case=…&view=…`, the saved view's link); **WS4b to merge**,
through GG2e (decision 9).

## Files touched

`spec/08` (AC's rows); `packages/glass-shared/src/questions/` (the two moved functions, their unit test),
`apps/workspace/src/questions/AnswerActions.tsx` re-pointed (I11); `apps/pages/server/` (the ask page's two handlers, its
words file), `tree-govuk/` (the answer's actions, the name form); `apps/pages/modules/graph/` (selecting on arrival);
`test/govuk/ask-actions.test.ts`, `keyboard/`, `scripts-off/`, the fixture Conduit's routes.

## Checks (frozen when cut)

GA1a's list, plus GG2e's live-page specs and the React workspace's suite (the move, I11).

## Out of scope

Asking (GA1b); proposals (GA1c); a view's conversation (GA1d; the same actions inside a view are a later part); the
cap's batch choice (GG2f2); any Conduit change; `apps/workspace` beyond the one re-pointed import.
