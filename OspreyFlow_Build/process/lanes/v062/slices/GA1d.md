# Slice GA1d · GA1 · A saved view's own conversation on the GOV.UK Ask page: read, asked in and reviewed in the view, never mixed with the case's

- **Build id:** GA1 (the `ask-chat` row)
- **Dial setting:** balanced · **Rounds limit:** the dial's (8); planned as **one round** (size S), a second only for the verifier's findings
- **After:**
  - GA1c (GA1b's asking and GA1c's review, which this part sends with `view_id`; the same files);
  - **GR1d** (the case's saved-views list, where *Ask about this view* is offered).

  **GR1d has no row in `slices.tsv`:** it is built on `away/GR1d` (`7ca66c123`), and its away report's six questions
  wait for the owner. GA1d waits with it.
- **Status:** a brief from an away drafting session (D246, D295), 28 November 2026, read from `origin/main` at
  `b79164850`. No question is the owner's.

## What

ADR-144 decision 4 (*Ask the model about these*): a question asked in a view reads that view's documents alone, "and the
conversation is kept with it". A reader opens **`/cases/ask?case=<id>&view=<id>`** (the query form) from GR1d's list of
the case's saved views, by the link *Ask about this view*. They see the view's own conversation, can ask in it (GA1b)
and can review its proposals (GA1c). The case's own conversation is never shown there, nor the view's on the case's
page. GOV.UK page only. Who asked is left out.

**The answers (each (a), and why):**

1. **(a) Reached from GR1d's list,** "Ask about this view", opening the Ask page with the view named. The heading is
   the view's name, then "Asked in the view *name*: the model reads only this view's documents". The name and whether
   it is shared come from one `GET .../views` (`list_case_views`, `services/api/app.py:4794`). The heavy
   `GET .../views/{view_id}` is not read. Why (a): a view's conversation belongs where the views are listed, and the
   list already carries what the heading needs.
2. **(a) GA1b's asking and GA1c's review work the same in a view.**
   - The ask's body carries `view_id` (`ScopeRequest`, `services/api/questions.py:334`: "the model reads its Documents
     alone").
   - Accept and reject carry `view_id` as a query field (`app.py:8398`, :8428).
   - The conversation is read with `GET .../questions?view_id=…` (:8363-8383).
   - Why (a): the routes already scope every call by the view, and one page has one way of asking.
3. **(a) A private view is said in the React workspace's words**, "private to you until you share it"
   (`apps/workspace/src/questions/QuestionsPanel.tsx:312`), above the form, when the view is not shared. A view the
   reader can see that is not shared is their own (`CaseView.shared`, `packages/schemas/case_views.py:90`), so the
   page never compares ids. Why (a): one sentence for one fact, in both front ends.
4. **(a) A view the reader may not see, or one deleted meanwhile, is the same 404 page as a missing page.** The route
   answers "404 as for no view" (`app.py:8376-8379`, `views.get(investigation.id, view_id, principal.id)`). Why (a): a
   different answer would tell a reader that another person's private view exists (rule 3).

## What exists today (re-read at `b79164850`)

- **The scope rule.** `read_in_view` (`services/api/dataset_scope.py:384-387`) lets one request read what is kept with
  that view, "after the view store let the reader see the view". `view_clause` (:390-394) keeps every other read to
  records kept with no view or with that one. The case's conversation and a view's never mix
  (`questions.py`, about :575-584 and :680-689).
- **The list route** (`app.py:8363-8383`): `INVESTIGATE` and the Viewer gate; with `view_id`, it calls `views.get(...)`
  and then `read_in_view(view_id)`.
- **GR1d** (`away/GR1d`) lists the case's saved views on the case's page (`/cases?case=<id>`) with save, share and
  delete as forms. It is not on main, and no row exists.

## Round 1's steps

1. Write Scenario AC's view rows (after GA1c's) and the acceptance test first. Show them red on GA1c's page: no `view`
   in the query.
2. **Make the fixture Conduit's view check and scope the real ones' shape:**
   - a view the reader may not see is a 404 on every route that takes `view_id`;
   - a candidate kept with a view is found only with that view named, and is a 404 without it;
   - the conversations are kept apart.
3. Teach the page's `GET` and its three actions the `view` query: one `GET .../views` for the heading and the private
   sentence; `view_id` on every call.
4. Add *Ask about this view* to GR1d's list template, one link a row.
5. Add the keyboard and scripts-off cases. Run the checks and every plant.

## Acceptance test (new, red on main)

`OspreyFlow_Core/apps/pages/test/govuk/ask-view.test.ts` (new; vitest) and GA1a's
`OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py`, extended with AC's view rows. Both are red on main.

| # | Case | Expected | The planted fault that shows it red (rule 15) |
| --- | --- | --- | --- |
| 1 | A view with two answers; the case with three | the view's page shows the two, the case's page the three; none on both | the page reading both conversations and merging them |
| 2 | Ask in the view | one `POST .../questions` with `view_id` and `read_from: "case"` | `view_id` left out (the answer would land in the case's conversation) |
| 3 | Accept a proposal in the view | one `POST .../accept?view_id=…` | `view_id` left off the query (the fixture answers 404, as the real scope does) |
| 4 | Another person's private view | the same 404 page | "This view is private" (an oracle) |
| 5 | A view deleted meanwhile | the same 404 page | a stale page drawn from an earlier read |
| 6 | A private view of one's own (`shared: false`) | the private sentence above the form | none shown |
| 7 | One render | exactly one `GET .../views` and one `GET .../questions?view_id=…` | a second conversation read without the view |
| 8 | GR1d's list | *Ask about this view* on each row, to `/cases/ask?case=…&view=…` | a link carrying the view's name instead of its id |
| 9 | No internal id in text | the view's id only in the link's query and hidden fields | an id in the heading |
| 10 | Keyboard and scripts off | the page whole and its forms working (rule 13, I4) | a form out of the tab order |

## Checks

GA1a's row's refrozen checks, with `test/server/csrf.test.ts`, and GR1d's own case-views test over its list
(`apps/pages/test/govuk/case-views.test.ts` on `away/GR1d`).

## Where its scenario goes

`spec/08_ACCEPTANCE_SCENARIOS.md`: **Scenario AC's view rows, after GA1c's rows** in AC.

## Out of scope

- *Save as a view* and *Show all on graph* (GA1e);
- a selection's question;
- a choice of view on the Ask page itself;
- any Conduit change;
- `apps/workspace`;
- the Default tree.

## Proposed `slices.tsv` row (not added)

```
GA1d	GA1	A saved view's own conversation on the Ask page at /cases/ask?case=…&view=…, reached by Ask about this view from GR1d's list: read, asked in and reviewed with view_id on every call, never mixed with the case's; a private view said in the workspace's words; one 404 page for a view the reader may not see (the owner's standing (a), D274; draft drafts_2026-11-28)	GA1c,GR1d	2	lane/slice-GA1d	full	OspreyFlow_Core/apps/pages/test/govuk/ask-view.test.ts,OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py	cd OspreyFlow_Core && npm exec --workspace apps/pages -- vitest run test/govuk/ask-view.test.ts && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GA1d uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py	cd OspreyFlow_Core && npm test --workspace apps/pages && npm run lint && npm run typecheck && node scripts/no_react_check.mjs && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GA1d uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q ../OspreyFlow_Build/tests/glass_trees/test_route_pins.py ../OspreyFlow_Build/tests/glass_trees/test_page_lists_merge.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_ask_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_cases_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_help_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_govuk_admin_people_scenario.py ../OspreyFlow_Build/tests/glass_trees/test_functions_yaml.py ../OspreyFlow_Build/tests/glass_trees/test_tree_parity.py ../OspreyFlow_Build/tests/glass_trees/test_no_react_check.py ../OspreyFlow_Build/tests/glass_trees/test_pages_foundation.py ../OspreyFlow_Build/tests/glass_trees/test_design_gates_reach.py ../OspreyFlow_Build/tests/test_ui_words_check.py ../OspreyFlow_Build/tests/test_copy_says_no_client.py ../OspreyFlow_Build/tests/harness/test_pages_setting.py && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=/Users/ayankar/dev/osprey-acceptance/GA1d uv run --frozen ruff check .
```
