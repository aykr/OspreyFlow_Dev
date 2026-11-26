# Slice GA1a · GA1 · A case's Ask & Chat as a GOV.UK page, read-only: the case's conversation as the reader may see it (the owner, 26 November 2026)

- **Build id:** GA1 (the `ask-chat` row of `apps/pages/FUNCTIONS.yaml`, about line 237)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8) · **After:** GR1a. **It starts after GR1a merges, by the
  owner's exception** (26 November, about 10:35 UTC, `RULINGS.md`: "Early starts: … GA1a … after GR1a"), not after GG2b:
  this is question 2's (b).
- **The owner's rulings:** the draft `slices/drafts_2026-11-25/GA1a.md`, every proposal (a) except question 2 (the
  exception above); **question 6: Editor**, as the routes are. Read the draft whole.

## The rulings, as built

1. **Q1 (a):** read-only, the case's conversation as the route sends it, oldest first: the question and when it was
   asked; the answer's words; its document citations by title; the engine and model in words; what was read; its
   proposals each with its state in words (never drawn as a fact: rule 5). No asking, no reviewing.
2. **Who asked:** "who made it" is left out for 0.7.0 everywhere (the owner, 26 November). **The questions route already
   sends `author_name`, resolved from `principal_names.display_names` (`services/api/app.py` about lines 8372 and 8373).**
   Leave the asker out, name `author` and `author_name` as left out in the census, and say in your report that the route
   already resolves the name, so the conductor can ask the owner whether this page is the exception.
3. **Q2 (b), the exception:** with no working set on the page, an answer drawn from graph facts outside the reader's view
   is left out by the route, as in the workspace. The scenario says so with one answer of each kind (documents only, graph
   facts in the view, graph facts outside it).
4. **The address is GR1a's query form, `/cases/ask?case=…`,** as GR1a merges it (the draft's `/cases/{case_id}/ask`
   needs GR1c, not ruled). If GR1a merges with another form, follow GR1a's and say so.
5. **Q3 (a), Q4 (a), Q5 (a), Q7 (a), Q8 (a), Q9 (a):** the case's own conversation only; nothing about left-out answers,
   `unplaced` in words; no proposal actions; one 404 page for every refusal; scenario AC written first; the strict reader
   and the field census over `QuestionAnswer`, the fixture hiding as the route hides.
6. **Q6, Editor:** the route's rule stands. **Correct the comment on `ASK_MODEL` in `services/api/rights.py` (about line
   38, today "I7, Viewer") to say what the routes enforce (Editor to ask; Viewer to read the conversation, as
   `services/api/questions.py` lines 19 and 20 say)** and the matching words in `spec/02` or `spec/03` if either says
   Viewer. A comment and spec words only: no code change in the Conduit.

**Re-read every citation:** the draft read `4f77858`; on today's main the list route is about `app.py:8357` and the ask
route about :8225.

## The table of cases

The draft's table, cases 1 to 14, each red first at the real call site (rule 15), with case 1's "author" read as point 2.

## Acceptance test

`OspreyFlow_Core/apps/pages/test/govuk/ask.test.ts` and `OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py`
(both new; red on main, green after).

## Checks (pure; store ports pinned to 9)

`npm test --workspace apps/pages`; `npm run lint`; `npm run typecheck`; `node scripts/no_react_check.mjs`; the GOV.UK
scenario tests (ask, cases, help, admin people), `test_functions_yaml.py`, `test_tree_parity.py`,
`test_no_react_check.py`, `test_pages_foundation.py`, `test_design_gates_reach.py`, `test_ui_words_check.py`,
`test_copy_says_no_client.py`, `tests/harness/test_pages_setting.py`; `ruff check .`. (`test_doc_citations_check.py` is
left out while main is red on it; the merge's full gate runs `citation-check`.)

## Out of scope

Asking (GA1b); accepting and rejecting proposals (GA1c); a view's conversation (GA1d); "Show all on graph" and "Save as
a view"; pattern asks; any Conduit change but the one comment; `apps/workspace`.
