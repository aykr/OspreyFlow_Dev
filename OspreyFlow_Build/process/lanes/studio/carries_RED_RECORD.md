# studio carries · red record (rule 15), 12 November 2026

Every test of this step was seen red before it was trusted. Two ways: a test written before its code and run
red for its stated reason, or (where the code came first) the code's own guard taken out at its own call site
and the test run red, then the file restored byte for byte. All runs stack-free on the Mac (closed ports
59991–59994, no lease, no live file), `.venv` at main's lock.

## Item 1 · an import replacing an in-progress draft (CARRIES row 90)

Written first, run red before any code:

| Test | Red, and why |
| --- | --- |
| `test_studio_release_routes.py::test_another_persons_draft_is_refused_in_words_naming_them` (4 cases) | `KeyError: 'replaces_own_draft'`, and the import answered 200, replacing analyst-7's draft |
| `::test_the_importers_own_draft_is_refused_until_confirmed` (2) | the same: no refusal, no field |
| `::test_the_importers_own_draft_is_replaced_when_confirmed` | no field |
| `::test_with_no_draft_the_import_opens_one_without_a_confirmation` | no field |
| `::test_a_draft_opened_by_another_between_plan_and_write_is_refused_before_any_write` | 200: the write saved the bundle's model into analyst-7's draft opened after the plan (the defect itself) |
| `tests/cli/test_conduit_client.py::test_replace_own_draft_is_sent_only_when_given` (2), `::test_the_parser_takes_replace_own_draft` | `TypeError: … unexpected keyword argument 'replace_own_draft'`; the parser had no flag |
| `ReleasesTab.test.tsx` "shows another person's draft refused …", "asks the importer to confirm …", "never sends a confirmation …" | 3 failed: no checkbox, no `replace_own_draft` in the query |

## Item 2 · a source's declared default marking (ADR-140 Amendment 19)

Engine, written first: the eight new cases of `tests/ingest/test_staging_marked_rows.py` failed on import of
`carry_declared_marking` (no such function), then went green with it. The Glass's five cases in
`sources.test.tsx` ("the source page's default marking") failed before the section existed (no combobox, no
`SOURCE_WORDS`).

The route, its store and the call sites were written before their tests, so each guard was taken out at its own
site (`plants/carries_plant.py`: one exact replacement, the selection run, the file restored):

| # | Plant (file: what was taken out) | Red |
| --- | --- | --- |
| 1 | `sources.py`: the scheme check (`if marking not in levels`) | `test_a_default_marking_is_refused_in_words_and_nothing_is_set[not-in-the-scheme]` |
| 2 | `sources.py`: the approver's clearance check | `…[above-the-approver]` |
| 3 | `sources.py`: the deployment ceiling check | `…[above-the-ceiling]` |
| 4 | `sources.py`: never below the source's own marking | `…[below-the-source]` |
| 5 | `app.py`: the route's Deploy pipelines right and source-approver role, replaced by a source author's gate | `test_the_default_is_set_only_by_a_source_approver_reaching_the_dataset` (`assert 200 == 403`) |
| 6 | `app.py`: the dataset's gate, taken from the route's parameter **and** from `NoLoadingAComposite` (which holds it too: taking one alone stayed green, the other still answering 404) | the same test (`assert 200 == 404`) |
| 7 | `app.py`: deployed pipelines not flagged | `test_a_source_approver_declares_changes_and_clears_a_default_marking_audited` |
| 8 | `app.py`: the audit's *from* read from the new value | the same test |
| 9 | `app.py`: the source page's dataset gate (`dataset_id: str`) | `test_the_default_is_read_with_the_source_and_only_where_the_source_is_read` |
| 10 | `app.py`: the source page's Add ingest files right | the same test |
| 11 | `pipeline_run.py`: the load passes no `declared` to `source_tables` | `test_staged_pipeline_run.py::test_a_load_joins_an_unmarked_source_carrying_its_declared_default` |
| 12 | `recipe_run.py`: `source_store=None` in place of `deps.sources` | `test_recipe_run_path.py::test_a_recipe_run_hands_the_pipeline_runner_its_source_store` (first run of this plant found no test watching the seam; the test was written for it, then the plant re-run red) |
| 13 | `staging_catalogue.py`: the never-a-marked-table guard in `carry_declared_marking` | `test_the_default_never_touches_a_table_that_has_a_marking_column`, `test_a_bound_column_with_an_empty_cell_is_not_filled_by_the_default` |
| 14 | `staging_catalogue.py`: the refusal no longer names the setting | `test_no_default_declared_keeps_the_guard_fail_closed_and_names_the_setting`, and both cases of `test_a_load_joining_an_unmarked_source_is_refused_naming_its_default_marking` |
| 15 | `staging_catalogue.py`: the setting named for two marked rows too | `test_a_refusal_of_two_marked_rows_does_not_point_at_the_default` |
| 16 | `app.py`: the step preview passes no `declared` | `test_studio_staging_routes.py::test_a_preview_joins_an_unmarked_source_carrying_its_declared_default` |
| 17 | `studio_verify.py`: Test passes no `declared` | `test_test_reads_the_sources_declared_default_as_the_run_does[declared]` |
| 18 | `studio_staging.py`: the raw rows not carried (the reader check reads the unmarked raw row) | the preview's and Test's declared cases |

Each plant took the shape the code receives at its call site: a real `InMemorySourceStore` with a registered
source and a set default; a real published recipe and CSV files through `run_published_pipeline`; the real app
and `get_principal` for the route.

**A finding from the reds, not a defect:** with no default declared, the preview and Test are refused before the
Join, by the row-reading guard (an empty bound marking cell reads as one the person may not view). The first draft
of those two tests expected the Join's words and failed; they now assert the withheld sample, the refusal a person
actually gets (Amendment 19, "What it costs").

## Round 2 · the lane-reviewer's findings at 77502ae, each red first

| Finding | Red before the fix |
| --- | --- |
| 1 · a default left below a raised source marking still carried (rule 3) | `test_staged_pipeline_run.py::test_a_default_left_below_a_raised_source_marking_is_not_carried`: `DID NOT RAISE` (the owners' rows carried OFFICIAL after the source was raised to SECRET, and joined) |
| 2 · the setting's answer, the whole source, given to someone the read refuses (rule 4) | `test_dataset_sources.py::test_an_approver_who_may_not_read_the_source_cannot_set_its_default`: `200 == 403`, the answer holding the source's location (the person: Deploy pipelines and Add ingest files, not Edit pipelines; the first two drafts of the case used a person the scoping or the read refused earlier, so they never reached the route, and were corrected) |
| 4 · the unmarked words for a marked table's empty cell | `test_a_bound_column_with_an_empty_cell_is_not_filled_by_the_default` (now asserting the words do not name the setting): failed |
| 5 · a case that passed with no carry at all | `test_a_default_marked_differently_from_the_other_table_is_still_refused` now asserts the carried cell and the words; plant 19 below |
| 7 · drafts not following a default change | `test_a_source_approver_declares_changes_and_clears_a_default_marking_audited`: `[] == [(ds-a, …, OFFICIAL)] * 3` |
| 9 · the Releases tab stuck after a refusal at the write | `ReleasesTab.test.tsx` "shows a refusal at the write as a refused check …": failed |
| 13 · the source page silent on a default no longer carried | `sources.test.tsx` "says a default left below the source's own marking is not carried": failed |

Plants for the seams the reviewer found untested (item 8) and the strengthened case (item 5):

| # | Plant | Red |
| --- | --- | --- |
| 19 | `staging_catalogue.py`: no carry at all (`carry_declared_marking` returns the table) | `test_a_default_marked_differently_from_the_other_table_is_still_refused` |
| 20 | `app.py`: Load Preview's `sources=` left out | `test_studio_staging_routes.py::test_load_preview_reads_the_sources_declared_default_as_the_run_does` |
| 21 | `cli/ospreyflow/main.py`: the dispatch's `replace_own_draft=` left out | `test_conduit_client.py::test_replace_own_draft_reaches_the_route_through_the_command[True]` |

Item 6's Postgres half (`test_studio_recipes_store.py::test_a_sources_default_marking_is_kept_read_back_and_refused_elsewhere_on_both_stores[postgres]`)
is a live case, run in the leased live set at the gate; its in-memory half passes here. Item 3's window inside
`save_draft`'s own lock is carried to the case lane (REPORT.md), not fixed here.
