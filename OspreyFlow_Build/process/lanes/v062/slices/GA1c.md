# Slice GA1c · GA1 · Accepting or rejecting a model's proposal on the case's GOV.UK Ask page, scripts off: accepted is inferred, never confirmed

- **Build id:** GA1 (the `ask-chat` row)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8); planned as **one round** (size S), a second only for the verifier's findings
- **After:** GA1b. It needs only GA1a's page, but GA1b edits the same page module, words and template, so the two run
  one after the other, never side by side (the chain plan's "case pages share files", `drafts_2026-11-26/CHAIN_PLAN.md:139`).
- **Status:** a brief from an away drafting session (D246, D295), 28 November 2026, read from `origin/main` at
  `b79164850`. No question is the owner's.

## What

On GA1a's page (`/cases/ask?case=<id>`), each of an answer's **pending** proposals gets two buttons, *Accept as
inferred* and *Reject*, each a scripts-off form with the anti-forgery token. Accepting writes an inferred node linked
to its Document, never a confirmed one (rule 5). The Conduit already does that
(`services/api/questions.py:1443-1480`, `ProvenanceState.INFERRED` at :1465), and the page must say it as truly as the
Conduit does it. GOV.UK page only. Who proposed or reviewed is not shown ("who made it" is left out for 0.7.0).

**The answers (each (a), and why):**

1. **(a) One proposal at a time, in the case's own conversation.** A view's conversation (`view_id`) is GA1d's. Why
   (a): no route takes several at once.
2. **(a) The buttons only on a `pending` proposal**, and only when `GET /v1/me/rights` holds `extract_files` and the
   reader's level in the case is Editor or Author (read as GR1a reads it). A hand post otherwise is said as "You cannot
   review the model's proposals in this case", and the route refuses all the same. Why (a): it offers what the route
   allows, and nothing it does not.
3. **(a) The words say what accept does before it is pressed:** "Accept as inferred: it is added to the case marked as
   the model's, until a person confirms it". After it, the proposal reads "Accepted, inferred". Reject is "Reject:
   nothing is added". Never "confirm" for accept. Why (a): rule 5.
4. **(a) A proposal reviewed meanwhile by someone else** (409 `candidate_not_pending`) is said as "Someone has already
   reviewed this proposal", and the conversation is re-read to show its state now. Why (a): "a candidate is reviewed
   exactly once" (`services/api/review.py:121-123`).
5. **(a) After a review, a `303` back to the conversation at that answer** (`#answer-<n>`, a position, never an id),
   with a banner. Why (a): the reader keeps their place, and a reload sends nothing.

## What exists today (re-read at `b79164850`)

- **The routes** (`OspreyFlow_Core/services/api/app.py`):
  - `POST .../questions/candidates/{candidate_id}/accept` (:8386-8414): `require_right(EXTRACT_FILES)` (:8388) and
    `InvestigationEditorDep` (:8391); `view_id` as a query field (:8398). It publishes the delta to the case's stream,
    is audited `accept_question_candidate` (:8409), and answers `QuestionAccepted` (`node_id`, `delta`;
    `questions.py:310-312`).
  - `POST .../reject` (:8417-8442): the same right and gate; `view_id` (:8428). Nothing is written. It is audited
    `reject_question_candidate` (:8438) and answers `RejectedResponse` (`review.py:197-198`).
- **The refusals:**
  - Reviewed already: `CandidateNotPendingError` (`review.py:121-123`; raised at :578-579 and :618-619), handled as
    **409 `candidate_not_pending`** (`app.py:3918-3924`).
  - Another unit's candidate, or none: `ExtractionCandidateNotFoundError`, "deliberately, not a 403", the same as a
    missing one (`review.py:115-118`), handled as 404 `extraction_candidate_not_found` (`app.py:3740-3746`).
- **What the page has:** GA1a's `QuestionAnswer.candidates`, each an `ExtractionCandidateRecord` (`review.py:201-206`)
  whose `status` is `pending`, `accepted` or `rejected` (:109-112).
- **The rights:** `EXTRACT_FILES` is "I4, Editor" (`packages/schemas/rights.py:35`).

## Round 1's steps

1. Write Scenario AC's review rows (after GA1b's) and the acceptance test first. Show them red on GA1b's page: no
   buttons.
2. **Make the fixture Conduit refuse in the routes' real order:** the right (403), the level (the case's 404 or 403
   as the gate answers), the candidate (404), then not pending (409). Rule 15: the fixture refuses what the route
   refuses.
3. Add the `accept` and `reject` actions to the page's `POST` (one Conduit call each), the words and the template's
   forms. The candidate's id goes only in a hidden field.
4. Add the keyboard and scripts-off cases. Run the checks and every plant.

## Acceptance test (new, red on main)

`OspreyFlow_Core/apps/pages/test/govuk/ask-review.test.ts` (new; vitest) and GA1a's
`OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py`, extended with AC's review rows. Both are red on main.

| # | Case | Expected | The planted fault that shows it red (rule 15) |
| --- | --- | --- | --- |
| 1 | An Editor with `extract_files` accepts a pending proposal | one `POST .../accept`; `303` to `#answer-<n>`; the proposal now "Accepted, inferred" | the words "Confirmed" (rule 5) |
| 2 | Reject | one `POST .../reject`; "Rejected"; nothing added | the accept route called |
| 3 | An accepted or rejected proposal | no buttons | buttons drawn whatever the status |
| 4 | Reviewed meanwhile (the fixture answers 409 `candidate_not_pending`) | the sentence of item 4 and the state now, re-read | the 409's body shown |
| 5 | Another unit's candidate, posted by hand | the same 404 page as a missing one | "You cannot review this" (an oracle that it exists) |
| 6 | A Viewer, or an Editor without `extract_files` | no buttons; a hand post said in words | the buttons drawn from one of the two alone |
| 7 | No `_csrf` | refused, nothing sent (I17) | the `POST` outside the check |
| 8 | The Conduit gives no answer, or 401 | the 502 page says the review may not have been made and to look again; 401 says sign in again | "Accepted" on a 502 |
| 9 | One review | exactly one `POST` (one audit row); a reload sends nothing | no `303` (a reload posts again) |
| 10 | No candidate id in text | the id only in the form's hidden field | an id printed |
| 11 | Keyboard and scripts off | each button reachable and working (rule 13, I4) | a button out of the tab order |
| 12 | The fixture | refuses in the route's order: the right, the level, the candidate (404), then not pending (409) | a fixture that lets a second review through |

## Checks

GA1a's row's refrozen checks, with `test/server/csrf.test.ts` over the new actions.

## Where its scenario goes

`spec/08_ACCEPTANCE_SCENARIOS.md`: **Scenario AC's review rows, after GA1b's rows** in AC.

## Out of scope

- a view's proposals (GA1d);
- a document's own candidates (`.../documents/{id}/candidates`, GG3's);
- confirming an inferred node (the inspector's, GG3d);
- several at once;
- any Conduit change;
- `apps/workspace`;
- the Default tree.

## Proposed `slices.tsv` row (not added)

```
GA1c	GA1	Accepting or rejecting a model's pending proposal on the Ask page, one at a time by scripts-off form (Accept as inferred, never confirmed; a 409 said as reviewed already and the state re-read; a 303 back to the answer), offered to an Editor holding extract_files (the owner's standing (a), D274; draft drafts_2026-11-28)	GA1b	2	lane/slice-GA1c	full	OspreyFlow_Core/apps/pages/test/govuk/ask-review.test.ts,OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/ask-review.test.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GA1c uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GA1c uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_help_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_tree_parity.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GA1c uv run --frozen ruff check .
```
