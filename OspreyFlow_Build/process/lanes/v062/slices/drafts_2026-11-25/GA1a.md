# Slice GA1a · GA1 · A case's Ask & Chat as a GOV.UK page, read-only: the case's conversation as the reader may see it (a draft)

**Status: a draft, not ruled.** Written on the server's build account in an away round (D246), 25 November 2026, on the
branch `drafts/2026-11-25`. No row in `slices.tsv`; no builder starts from this paper. **Rewritten the same day on the
owner's correction:** the plan's row is "**GA1: Ask & Chat as server-rendered pages (R5)**", stage 1, **needs GG2**. The
first draft's reading (assessments) is withdrawn. Its access finding is kept on its own, in
`ACCESS_FINDING_assessments.md`.

## Question 0, rechecked against the plan's row

GA1 is the `ask-chat` row (`OspreyFlow_Core/apps/pages/FUNCTIONS.yaml:235-241`: "Ask & Chat", in
`apps/workspace/src/questions/`, slice "R5", no scenario, no route, planned). **It needs GG2.** The code shows two
reasons:
- **The conversation's visibility is read from the reader's working set.** `history` calls
  `self._working_set.visible_membership(investigation_id, principal)` and leaves out any answer drawn from graph facts
  the reader's view does not hold (`services/api/questions.py:1350-1370`).
- **The answer's actions put things on the canvas.** "Show all on graph" (`AnswerActions.tsx:57-66`) does this, and so
  does a graph citation's "bring into view" (`glass-shared/src/questions/graphFacts.ts:94`).

A read-only page needs neither action, but its scenario must say what the reader's view is before GG2's working set
exists on the page service (question 2).

## What exists today (read on 25 November 2026 at `4f77858a5`; re-read, lines move)

- **The routes** (`OspreyFlow_Core/services/api/app.py`):
  - **`GET /v1/investigations/{id}/questions`** (`list_questions_route`, :8300-8322): `require_right(INVESTIGATE)` and
    the case viewer gate. It answers `list[QuestionAnswer]`, "the case's questions and answers, as this reader may see
    them". With `view_id`, the conversation kept with that view, "only for a reader who may see the view ... 404 as for
    no view" (`views.get` first, :8317). Author names are resolved after the filter (:8320-8321).
  - **`POST .../questions`** (:8173): `ASK_MODEL` and the **editor** gate (:8177). It asks inside
    `model_calls.attributed` (:8202, SE8a's record of every model call: `services/api/model_calls.py:82-125`) and
    audits (:8218). *`rights.py:38` comments `ASK_MODEL` as "I7, Viewer", while the route is Editor and the module
    docstring says "Editor to ask" (`questions.py:19-20`): a disagreement for the owner (question 6).*
  - **`POST .../questions/will-read`** (:8234): `ASK_MODEL`, editor, nothing sent to a model.
  - Accepting and rejecting a proposal: **`POST .../questions/candidates/{id}/accept`** (:8325) and **`/reject`**
    (:8356), both `EXTRACT_FILES` and editor.
  - `POST .../patterns/ask` (:7153) is a separate pattern proposal, not this row's.

  **Nothing streams.** An ask is one synchronous POST with a client deadline (`questionsApi.ts:169-170`).
- **What a reader is shown, and what is left out silently** (`QuestionsService.history`, `questions.py:1340-1421`).
  An answer is skipped "without a word to say so (rule 3)" when any of these holds:
  - the reader cannot see every document it read (:1358-1359);
  - a record its search found is not visible to them (:1362-1364);
  - its graph facts are not all in the reader's view (:1366-1370);
  - its event counts were made from events the reader may not view, or from other cases' events (:1379-1385);
  - its scopes were not recorded and it holds graph facts, unless the reader is its author (:1373-1377).

  The citations shown are filtered again, per reader (:1386-1397). The model read only the asker's visible documents
  and facts when it answered (:751-767, :843-891).
- **The answer's shape.** `QuestionAnswer` (`questions.py:283-307`): `id`, `author`, `author_name` (resolved at read,
  never stored), `question`, `answer`, `citations` (document and title), `candidates` (the proposals of the reader's
  unit, each an `ExtractionCandidateRecord` whose `status` is `pending`, `accepted` or `rejected`,
  `services/api/review.py:110-112`, :183-188), **`unplaced: int`** ("proposals and graph citations left out: the words
  are not in the document named, or the fact is not in the brief": a count of the model's own unplaceable claims, not
  of hidden items), `created_at`, `graph_citations`, `engine` and `model` (ADR-135 decision 4), `read` (what was read,
  ADR-098 Amendment 7) and `search_citations` (ADR-129 Amendment 5).
- **Rule 5 holds already.** Accepting a proposal writes the node and its `MENTIONED_IN` link as
  `ProvenanceState.INFERRED` (`questions.py:1443-1480`). A proposal is `pending` until a person reviews it, once
  (`review.py:122-123`, :557, :591).
- **Stored, and kept apart by view.** The table is `case_questions` (`questions.py:588-619`, `PostgresQuestionStore`
  :630-710). The case's own conversation and each view's never mix (:574-585, :679-689). Every reader of the case sees
  other analysts' questions, filtered as above.
- **The React screen.** `apps/workspace/src/questions/`: `QuestionsPanel.tsx` (691 lines), `AskPage.tsx` (195),
  `useAskPage.ts` (192), `AnswerActions.tsx` (82: "Show all on graph" and "Save as a view", :57-66, each only when its
  parent passes it, :37-52), `showAnswer.ts` (43) and `askPage.css` (52). The shared client is
  `packages/glass-shared/src/questions/questionsApi.ts` (`listQuestions` :78, `willRead` :140, `askQuestion` :159,
  `acceptProposal` :180, `rejectProposal` :198).
- **The specification.** `spec/02_GLASS_FRONTEND.md`: the rail entry (about lines 205 to 206), the answer actions
  (about 248 to 260), **§2.0d, the Ask & Chat drawer and page (about 734 to 810)**, and questions in a view (about 1091
  to 1096). `spec/03` route table, about lines 506 and 530 to 533. ADR-098 (`spec/06` about line 10234), ADR-106
  (about 10811), ADR-129 (about 20178), ADR-135 (about 21341) and ADR-144 (about 26990, decision 4, the view rule).
  **`spec/08` has no scenario about asking a question.**
- **The page service.** No Ask page and no case page (GR1a, drafted beside this, has the case's path).

## Questions for the owner (the proposal first)

1. **The first slice's scope.** (a) **Read-only:** the case's conversation at `/cases/{case_id}/ask`, as the route
   sends it, oldest first. Each entry shows:
   - the question, who asked it and when;
   - the answer's words;
   - its document citations by title;
   - which engine and model answered ("Answered by the local model <name>");
   - what was read (the `read` summary in words);
   - its proposals, each with its state in words ("proposed by the model, not yet reviewed", "accepted", "rejected").
     A proposal is never drawn as a fact (rule 5).

   No asking and no reviewing. (b) Read and ask in one slice (a form posting the question, with the anti-forgery token
   and the route's deadline said in words). That is GA1b in (a).
2. **"Needs GG2", and the reader's view.** (a) **GA1a waits for GG2's first page with a working set (GG2b)**, as the
   plan's row says. The page asks the route exactly as the workspace does, so an answer drawn from graph facts appears
   only when the reader's view holds them. The scenario says so with one answer of each kind (from documents only, from
   graph facts in the view, from graph facts outside it). (b) Start after GR1a without GG2. The route's own filter
   still holds, so nothing leaks, but on a page with no graph a reader would see fewer answers than in the workspace
   and could not tell why.
3. **A view's conversation.** (a) **The case's own conversation only** in GA1a. A view's (`?view_id=`) comes with the
   saved views page (GR1's). (b) Both, with the view chosen from a list.
4. **What is never said.** (a) **Nothing about left-out answers.** The route leaves them out "without a word"
   (rule 3), so the page shows no count, no gap and no "some answers are hidden". **`unplaced` is shown in words**
   ("2 of the model's claims could not be matched to what it read"), because it is about the model's answer, not
   about the reader's access. (b) `unplaced` left out too, named as left out in the census.
5. **The proposals' actions.** (a) **None in GA1a.** Accept and reject (`EXTRACT_FILES`, editor) are a form each in a
   later slice, with the anti-forgery token. Accepting writes `inferred`, never confirmed (rule 5), and the words say
   so. (b) In GA1a.
6. **The right to ask, for the record.** `ASK_MODEL` is commented "Viewer" (`rights.py:38`), while the route needs an
   editor. (a) **The route's rule stands (editor), and the comment is corrected** in the spec change of whichever slice
   first offers asking (GA1b). (b) Viewers may ask: a Conduit change, outside GA1.
7. **Who may open it.** (a) **Whoever the route lets read it** (`INVESTIGATE` and a level in the case). Every refusal is
   the same GOV.UK 404 page, words and status, as a page that does not exist (as GR1a question 4 (a)). (b) The route's
   403 passed through for a level too low.
8. **The scenario.** (a) **A new `spec/08` scenario, AC, written first and red first, from these rulings**, its id in
   the `ask-chat` row for this page only. (b) Your words.
9. **The fixture.** (a) **The strict reader and the field census (GR3a's)** over `QuestionAnswer` (with
   `graph_citations` and `search_citations` drawn as their labels or named as left out). The fixture **hides as the
   route hides**: an answer that read a document above the lower reader is absent from that reader's answer, as
   `history` makes it absent. Answers come from the real route when GR3b lands (rule 15).

## The table of cases (each red first; planted faults at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A case's conversation of three answers | each question, author, time, answer, cited documents by title, the engine and model, what was read, in the route's order | the engine left out (the census turns red) |
| 2 | An answer with two proposals, one pending and one accepted | each in words with its state; the pending one never shown as a fact | a pending proposal drawn as part of the answer's facts (rule 5) |
| 3 | Two readers of different clearance; one answer read a document above the lower reader | the lower reader's page has one answer fewer, with no gap, no count and no sentence | the fixture sending the hidden answer and the page dropping it (the page must never filter: the fixture models the route, which leaves it out) |
| 4 | An answer with `unplaced: 2` | the sentence of question 4 (a) | `unplaced` drawn as a count of hidden answers |
| 5 | A citation the route sends without a title | "a document with no title", never its id | the document id printed |
| 6 | A case with no questions | "Nobody has asked a question in this case yet" | an empty list |
| 7 | An answer kept before engines were recorded (`engine` absent) | "The model that answered was not recorded" | the field shown blank |
| 8 | No level, another unit, no case, no `INVESTIGATE` | the same 404 page, words and status | the route's 403 passed through |
| 9 | The Conduit gives no answer, or 401 | the 502 "could not be read" page; an ended session says to sign in again | an empty conversation |
| 10 | A body missing a field `QuestionAnswer` requires | "could not be read", never an empty conversation | each required field removed in turn |
| 11 | One render | exactly one `GET .../questions` | the page reading twice |
| 12 | No internal id on the page | no question, candidate, document or node id in the HTML outside a link's own path | an id printed |
| 13 | Keyboard | each link reachable and working, one case in the GOV.UK keyboard folder (rule 13) | a link out of the tab order |
| 14 | Scripts off | the page whole | none: it holds no script; the spec proves it |

## Checks (frozen when cut)

GR3a's list, adapted: `npm test --workspace apps/pages`, lint, typecheck, `no_react_check.mjs`; the new scenario's test
and the pages' tests; `test_functions_yaml.py`, `test_tree_parity.py`, `test_no_react_check.py`,
`test_pages_foundation.py`, `test_design_gates_reach.py`; `test_ui_words_check.py`, `test_copy_says_no_client.py`,
`test_doc_citations_check.py`; `tests/harness/test_pages_setting.py` (the route list); `ruff check .`;
`make -C OspreyFlow_Build design-check`; the cheap checks of 20 November.

## Out of scope

Asking (GA1b); accepting and rejecting proposals (a later GA1 slice); a view's conversation (question 3); "Show all on
graph" and "Save as a view" (with GG2's canvas and GR1's views); pattern asks (`patterns/ask`, the query builder's,
GG4); any Conduit change; `apps/workspace`.
