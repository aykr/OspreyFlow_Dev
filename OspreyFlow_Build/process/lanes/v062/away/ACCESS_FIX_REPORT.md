# The assessments access fix (25 November 2026, D246 away round)

**Done.** In the gaps and assumptions routes, a linked entity or linked judgement the reader may not see is now left out
entirely: no count, no placeholder, no sign it exists (rule 3). This is exactly how a judgement whose evidence the reader
cannot see is hidden today (ADR-046), and it uses the same step.

The four red tests are green. The controls are green, with one exception named below: its assertion had recorded the fault
itself. Three planted faults at the real call sites each put one hidden link back and are found (this line said four; it was three, corrected in SE7c round 2, below).

Branch `away/access-fix`, from `away/access-assessments` (`2bb9e1750`). Commits `73b2fb292` (the fix, the spec line, the
tests) and `ea7114713` (line widths). Not pushed, not merged. Synthetic data only. Run through `~/osprey-d246/d246_ns.sh` from
`OspreyFlow_Core`.

## What changed, and where (at `ea7114713`)

**The spec first (rule 11).** `OspreyFlow_Build/spec/03_CONDUIT_MIDDLEWARE.md` lines 631 to 634, the route list, now says
what each of the four routes does with links, in the words its brief line already uses ("absent, with no count").

**`OspreyFlow_Core/services/api/assessments.py`**, a new section after `list_visible_judgements`:
- `:584` `_reference_visible`: one reference, read exactly as `judgement_visible_to` reads each `supporting` one. Visible when
  `GraphPort.get_node` gives it to the reader, or when the system superseded it and its successor resolves (owner ruling R7).
  The access decision stays the graph adapter's, under the reader's own principal (rule 3); the Conduit keeps only what that
  answer allows, as `list_visible_judgements` already does.
- `:593` `visible_judgement_ids`: the judgements `GET .../judgements` shows this reader in this case. It uses the same
  ownership query and ADR-046 rule, without the lazy review flag, so reading assumptions writes nothing.
- `:603` `list_visible_gaps`: each gap with only the linked entities the reader may see.
- `:617` `list_visible_assumptions`: each assumption with only the linked judgements the reader is shown. When no assumption
  links anything (`:627`) it reads no judgements, so the SQL is the same as before for that case.
- `:570` `UnverifiableLinkError`, `:636` `confirm_gap_links`, `:646` `confirm_assumption_links`: the write side, below.

**`OspreyFlow_Core/services/api/app.py`:**
- `:8831` `list_gaps_route` calls `list_visible_gaps` (it now takes `GraphDep`).
- `:8888` `list_assumptions_route` calls `list_visible_assumptions` (it now takes `JudgementsStoreDep` and `GraphDep`).
- `:8800` and `:8854`: the two save routes check their links before anything is written.
- `:3615`: the 422 handler.

The stores, the models and the generated types are unchanged. No other route was touched. Only these four routes read the
two tables, and nothing else in `services/` or `packages/` reads them.

## The write side: needed for the four tests, and a choice for the owner to confirm

Two of the four red tests are about saving: a gap and an assumption must not store a link their saver cannot confirm. A
read-side filter cannot turn them green, and the brief says "never accepted narrower". So the saves now refuse, mirroring a
judgement's citation rule (`JudgementStore.save` → `_unverifiable_citations`, `assessments.py:223`):
- A gap's linked entity must be a node the saver may see (`get_node`, as at a judgement's save).
- An assumption's linked judgement must be one the saver is shown in this case. An absent id, another case's judgement and
  one hidden by ADR-046 are all refused.
- **The answer is 422 `{"error": "unverifiable_link", "detail": ..., "link_ids": [...]}`.** It names only the ids the
  saver sent. An absent id and a hidden one are refused alike, in the same words and shape, so the refusal does not tell the
  saver which ids are real (`test_a_save_refusal_names_only_what_the_saver_sent_and_treats_absent_and_hidden_alike`).
  Nothing is written.

**For the owner:**
- The error's name `unverifiable_link` and its `link_ids` field are new. They are modelled on `unverifiable_citation` and
  `citation_ids`; rename if you prefer.
- The Glass (`packages/glass-shared/src/assessment/api.ts`) names only the judgement refusal specially, so a refused gap or
  assumption save reaches the analyst as its generic "failed: 422" message. The Glass only links what it shows the analyst,
  so its normal path is unaffected. Wording the refusal there is a Glass part, not done here ("no other behaviour changes").

## The tests

File: `OspreyFlow_Build/tests/services/api/test_assessment_links_access.py`. **15 passed.** They use the real routes, the real
stores and the real `list_visible_judgements`, in process. `_PinnedPool` answers only the stores' own SQL; `_ClearanceGraph`
refuses above clearance and unknown ids (the previous report has the reasons).

| Test | Before the fix | After |
| --- | --- | --- |
| `test_a_gap_never_names_to_its_reader_a_node_they_may_not_see` | FAILED | **passed** |
| `test_an_assumption_never_names_to_its_reader_a_judgement_hidden_from_them` | FAILED | **passed** |
| `test_a_gap_cannot_link_a_node_its_saver_cannot_confirm` | FAILED | **passed** |
| `test_an_assumption_cannot_link_a_judgement_its_saver_cannot_see` | FAILED | **passed** |
| `test_a_gap_names_to_its_reader_a_node_they_may_see` (control) | passed | passed |
| `test_an_assumption_names_to_its_reader_a_judgement_they_may_see` (control) | passed | passed |
| `test_the_graph_stand_in_hides_the_secret_node_from_the_official_reader` (control) | passed | passed |
| `test_a_judgement_cannot_cite_a_node_its_saver_cannot_confirm` (control) | passed | passed |
| `test_the_pinned_pool_refuses_a_query_it_does_not_model` (control) | passed | passed |
| `test_the_graph_stand_in_refuses_above_clearance_and_unknown_ids` (control) | passed | passed |
| `test_the_real_list_queries_are_the_ones_the_pool_models` (control, **changed**) | passed | passed |
| `test_a_hidden_link_put_back_at_the_gaps_routes_call_site_is_found` (plant) | new | passed |
| `test_a_hidden_link_put_back_at_the_assumptions_routes_call_site_is_found` (plant) | new | passed |
| `test_a_filter_that_lets_one_hidden_node_through_is_found` (plant) | new | passed |
| `test_a_save_refusal_names_only_what_the_saver_sent_and_treats_absent_and_hidden_alike` | new | passed |

**The one control that changed, said plainly.** `test_the_real_list_queries_are_the_ones_the_pool_models` had two halves:
- its SQL pin, which is **unchanged and still green**: exactly two INSERTs and the two pinned list queries ran;
- the assertion `world.graph.asked == []`, "the graph was never asked about a gap's links". That assertion recorded the
  fault itself, so no fix could leave it green.

It now asserts the opposite: `[(VISIBLE, SECRET_EDITOR.id), (VISIBLE, OFFICIAL_READER.id)]`. That is, the saver's link is
confirmed as the saver and the reader's list is checked as the reader. The other six controls are unchanged.

**The planted faults, at the real call sites (rule 15).** Each is the real code with one thing changed, run through the same
check that finds nothing in the real route:
- `services.api.app.list_visible_gaps`, the name `list_gaps_route` calls, is wrapped to put the one hidden link back. The
  check reports exactly "the OFFICIAL reader was sent the SECRET node's id".
- `services.api.app.list_visible_assumptions` is wrapped the same way, with the hidden judgement's id. The check reports
  exactly "the OFFICIAL reader was sent the id of a judgement hidden from them".
- `services.api.assessments._reference_visible`, the filter's own decision, is planted to let the hidden node through and
  nothing else. The gap check reports the hidden id and nothing more; the visible link is still sent.

**Red to green on this branch, observed.** I ran the file twice by a script that swaps only `services/api/app.py` and
`assessments.py` for their base versions and restores them (restore checked; `git status` showed only the intended edits):
- base product files: **9 failed, 6 passed**. The failures are the four, the changed control, the three plants (their
  functions do not exist yet) and the refusal-shape test. The six unchanged controls are green.
- the fix: **15 passed**.

## Everything else run

- Ruff: `ruff check .` (Core) clean. Ruff on the test file clean, line width aside: the Build tree has no ruff width rule in
  CI. `ruff format --check` on `assessments.py` reports one pre-existing difference, at
  `flag_judgements_citing_superseded_node`; the base file reports the same, and CI runs `ruff check` only.
- `mypy services/api/assessments.py services/api/app.py`: no issues.
- `make authorized-query-check route-coverage-check schemas-check test-file-coverage-check domain-model-coverage-check
  citation-check product-tree-link-check`: all green.
- `test_investigation_levels.py`, `test_route_rights.py`, `test_openapi_published.py`, `test_prefetch.py`,
  `test_review_routes.py`: 280 passed, 6 failed. The 6 are the same with the base product files, so they are not this change:
  - `test_route_rights.py`: three cases that sign in for real against Postgres on port 59992, which D246 closes;
  - `test_prefetch.py`: three cases that need the network.

## What is owed, and could not be done here

- **The live route tests.** `tests/services/api/test_assessment_routes.py` and the live half of `test_route_rights.py` need
  real Postgres and ArcadeDB. This machine has neither, and D246 runs no container. They should run under the stack lease
  before the merge. The finding's two real-store tests (in `ACCESS_FINDING_assessments.md`) should be added there too: the
  in-process stand-in graph models clearance only, not handling codes or owning units.
- **The owner's confirmations:** the write side's error name, and that this is the shape ruled. The finding's question 2(a)
  is done: hidden links dropped and the gap still shown, not the gap hidden in full.
- **The Glass's wording** of the new refusal (above).

## Correction and additions, SE7c round 2 (25 November 2026)

The verifier found three test gaps in round 1. Each is closed in `test_assessment_links_access.py` (now 21 tests, all passed):

- **The report said four planted faults; the file had three, all on the read side.** Four are now on the write side as
  well, so there are seven. At the real call sites (`services.api.app`): `confirm_assumption_links` replaced by one that
  stores the row and then confirms (`test_a_save_that_checks_its_links_after_storing_them_is_found`), `confirm_assumption_links`
  replaced by a no-op (`test_an_assumption_save_that_confirms_nothing_is_found`), `confirm_gap_links` replaced by a no-op
  (`test_a_gap_save_that_confirms_nothing_is_found`); and inside the filter's own decision, `visible_judgement_ids` that also
  counts the other case's judgements (`test_a_judgement_filter_that_ignores_the_case_is_found`).
- **The assumption save's refusal** (`test_an_assumption_save_refusal_names_only_what_the_saver_sent_and_stores_nothing`)
  asserts the same as the gap's: 422 `unverifiable_link`, `link_ids` the ids sent, a hidden and an absent judgement refused
  in the same words, nothing stored, and the SECRET reader of the case served no assumption.
- **Another case's judgement** (`test_an_assumption_cannot_link_a_judgement_of_another_case`): a judgement the saver is shown in
  its own case is refused when linked from this one; a judgement of this case is accepted (the control). This pins spec/03
  line 633's "another case's".

**Observed against the product's own code** (the real `app.py` or `assessments.py` edited, then restored from a saved copy,
`git status` clean after): the assumption confirmation moved after `assumptions_store.save` fails four tests (the two new
refusal tests and two plants); the gap confirmation removed fails four (the old gap test, the SQL-pin control, the refusal
shape test and the plant); a `visible_judgement_ids` that also reads the other case fails two (the case test and its plant).
Before round 2, the first of these passed every test in the file.
