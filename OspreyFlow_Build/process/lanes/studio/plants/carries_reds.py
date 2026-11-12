"""The carries step's plants (rule 15), re-runnable: each takes one guard out at its own call site
(an exact old -> new replacement, which must occur once), runs the tests that should go red, puts the
file back byte for byte, and checks that the named test failed. Raw output: `carries_reds.log`.

Run from OspreyFlow_Core, stack-free (closed ports, no lane):

    unset OSPREY_LANE; ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 VALKEY_PORT=59993 \\
      CLICKHOUSE_HTTP_PORT=59994 .venv/bin/python ../OspreyFlow_Build/process/lanes/studio/plants/carries_reds.py

Exit 0 only if every plant went red for the test it names, and every file is back as it was.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CORE = Path.cwd()
T = "../OspreyFlow_Build/tests"
LOG = Path(__file__).with_name("carries_reds.log")


@dataclass(frozen=True)
class Plant:
    n: int
    what: str
    path: str
    old: str
    new: str
    tests: tuple[str, ...]
    #: A test id that must be among the failures.
    red: str


DS = f"{T}/services/api/test_dataset_sources.py"
STAGED = f"{T}/ingest/test_staged_pipeline_run.py"
MARKED = f"{T}/ingest/test_staging_marked_rows.py"
ROUTES = f"{T}/services/api/test_studio_staging_routes.py"
RELEASE = f"{T}/services/api/test_studio_release_routes.py"
CLI = f"{T}/cli/test_conduit_client.py"

PLANTS = [
    Plant(1, "the scheme check", "services/api/sources.py",
          "    if marking not in levels:\n        return [", "    if False:\n        return [",
          (DS,), "test_a_default_marking_is_refused_in_words_and_nothing_is_set[not-in-the-scheme]"),
    Plant(2, "the approver's clearance check", "services/api/sources.py",
          "    if principal.clearance not in levels or levels.index(marking) > levels.index(",
          "    if False and levels.index(marking) > levels.index(",
          (DS,), "test_a_default_marking_is_refused_in_words_and_nothing_is_set[above-the-approver]"),
    Plant(3, "the deployment ceiling check", "services/api/sources.py",
          "    if ceiling.above(marking):", "    if False:",
          (DS,), "test_a_default_marking_is_refused_in_words_and_nothing_is_set[above-the-ceiling]"),
    Plant(4, "never below the source's own marking, at the route", "services/api/sources.py",
          "and levels.index(marking) < levels.index(own):", "and False:",
          (DS,), "test_a_default_marking_is_refused_in_words_and_nothing_is_set[below-the-source]"),
    # The approver's gate is held twice (Deploy pipelines among the route's dependencies, and the
    # source approver's role on its principal): taking one alone stays green, so both go here.
    Plant(5, "the approver's gate (right and role), a source author's instead", "services/api/app.py",
          "    dependencies=[\n        Depends(require_right(Right.PUBLISH_PIPELINES)),\n"
          "        # The answer is the whole source, so the write needs what reading it needs (rule 4; the\n"
          "        # lane review, item 2): Add ingest files and the source author's Edit pipelines.\n"
          "        Depends(require_right(Right.ADD_INGEST_FILES)),\n"
          "        Depends(require_studio_role(StudioRole.SOURCE_AUTHOR)),\n"
          "        NoLoadingAComposite,\n    ],\n)\n"
          "async def set_dataset_source_default_marking(\n"
          "    dataset_id: StudioDatasetDep,\n    source_id: str,\n    body: SourceDefaultMarkingInput,\n"
          "    principal: Annotated[Principal, Depends(require_studio_role(StudioRole.SOURCE_APPROVER))],",
          "    dependencies=[\n"
          "        Depends(require_right(Right.ADD_INGEST_FILES)),\n"
          "        Depends(require_studio_role(StudioRole.SOURCE_AUTHOR)),\n"
          "        NoLoadingAComposite,\n    ],\n)\n"
          "async def set_dataset_source_default_marking(\n"
          "    dataset_id: StudioDatasetDep,\n    source_id: str,\n    body: SourceDefaultMarkingInput,\n"
          "    principal: SourceAuthorDep,",
          (DS,), "test_the_default_is_set_only_by_a_source_approver_reaching_the_dataset"),
    # The dataset's gate is held twice too (the route's parameter and `NoLoadingAComposite`).
    Plant(6, "the dataset's gate, from the parameter and the composite refusal", "services/api/app.py",
          "        NoLoadingAComposite,\n    ],\n)\nasync def set_dataset_source_default_marking(\n"
          "    dataset_id: StudioDatasetDep,",
          "    ],\n)\nasync def set_dataset_source_default_marking(\n    dataset_id: str,",
          (DS,), "test_the_default_is_set_only_by_a_source_approver_reaching_the_dataset"),
    Plant(7, "deployed pipelines not flagged", "services/api/app.py",
          "    flagged = await studio_recipes.flag_for_source(\n"
          "        dataset_id, edited.location, SOURCE_GOVERNANCE_CHANGED\n    )\n"
          "    # Each draft reading it",
          "    flagged: list[str] = []\n    # Each draft reading it",
          (DS,), "test_a_source_approver_declares_changes_and_clears_a_default_marking_audited"),
    Plant(8, "the audit's from taken from the new value", "services/api/app.py",
          '"default_marking_before": previous,', '"default_marking_before": edited.default_marking,',
          (DS,), "test_a_source_approver_declares_changes_and_clears_a_default_marking_audited"),
    Plant(9, "the source page's dataset gate", "services/api/app.py",
          "async def get_dataset_source(\n    dataset_id: StudioDatasetDep, source_id: str,",
          "async def get_dataset_source(\n    dataset_id: str, source_id: str,",
          (DS,), "test_the_default_is_read_with_the_source_and_only_where_the_source_is_read"),
    Plant(10, "the source page's Add ingest files right", "services/api/app.py",
          '    "/v1/datasets/{dataset_id}/sources/{source_id}",\n'
          "    dependencies=[Depends(require_right(Right.ADD_INGEST_FILES))],",
          '    "/v1/datasets/{dataset_id}/sources/{source_id}",\n    dependencies=[],',
          (DS,), "test_the_default_is_read_with_the_source_and_only_where_the_source_is_read"),
    Plant(11, "the load passes no declaration", "services/api/pipeline_run.py",
          "            declared=declared,\n        )  # fmt: skip", "        )  # fmt: skip",
          (STAGED,), "test_a_load_joins_an_unmarked_source_carrying_its_declared_default"),
    Plant(12, "the run hands the runner no source store", "services/api/recipe_run.py",
          "            source_store=deps.sources,", "            source_store=None,",
          (f"{T}/services/api/test_recipe_run_path.py",),
          "test_a_recipe_run_hands_the_pipeline_runner_its_source_store"),
    Plant(13, "the engine's never-a-marked-table guard", "services/ingest/staging_catalogue.py",
          "    if any(column in table.columns for column in marked):\n        return table", "",
          (MARKED,), "test_the_default_never_touches_a_table_that_has_a_marking_column"),
    Plant(14, "the refusal no longer names the setting", "services/ingest/staging_catalogue.py",
          'raise StagingError([f"{words}. {UNMARKED_WORDS}" if unmarked else words])',
          "raise StagingError([words])",
          (MARKED,), "test_no_default_declared_keeps_the_guard_fail_closed_and_names_the_setting"),
    Plant(15, "the setting named for marked rows too", "services/ingest/staging_catalogue.py",
          'raise StagingError([f"{words}. {UNMARKED_WORDS}" if unmarked else words])',
          'raise StagingError([f"{words}. {UNMARKED_WORDS}"])',
          (MARKED,), "test_a_refusal_of_two_marked_rows_does_not_point_at_the_default"),
    Plant(16, "the step preview passes no declaration", "services/api/app.py",
          "        declared=await declared_markings(sources, recipe.dataset_id, scheme),\n"
          "    )\n    await audit.record(",
          "    )\n    await audit.record(",
          (ROUTES,), "test_a_preview_joins_an_unmarked_source_carrying_its_declared_default"),
    Plant(17, "Test passes no declaration", "services/api/studio_verify.py",
          "                declared=staging.declared,\n", "",
          (ROUTES,), "test_test_reads_the_sources_declared_default_as_the_run_does[declared]"),
    Plant(18, "the raw rows not carried", "services/api/studio_staging.py",
          "            rows = [row | dict.fromkeys(sorted(classified), default) for row in rows]",
          "            pass",
          (ROUTES,), "test_a_preview_joins_an_unmarked_source_carrying_its_declared_default"),
    Plant(19, "no carry at all", "services/ingest/staging_catalogue.py",
          "    if declared is None or not marked or not classification:\n        return table",
          "    if True:\n        return table",
          (MARKED,), "test_a_default_marked_differently_from_the_other_table_is_still_refused"),
    Plant(20, "Load Preview passes no sources", "services/api/app.py",
          "    report, _ = await _studio_dry_run(\n"
          "        investigation=investigation, recipe=recipe, principal=principal, scheme=scheme, graph=graph,\n"
          "        ontology=ontology, recipe_runs=recipe_runs, typology_rules=typology_rules,\n"
          "        analytics=analytics, principal_resolver=principal_resolver, patterns_store=patterns_store,\n"
          "        hotlists_store=hotlists_store, screening_lists=screening_lists, compute=compute,\n"
          "        repo_root=repo_root, influencers_store=influencers_store, models=models,\n"
          "        staging_storage=staging_storage, list_store=list_store, sources=sources,",
          "    report, _ = await _studio_dry_run(\n"
          "        investigation=investigation, recipe=recipe, principal=principal, scheme=scheme, graph=graph,\n"
          "        ontology=ontology, recipe_runs=recipe_runs, typology_rules=typology_rules,\n"
          "        analytics=analytics, principal_resolver=principal_resolver, patterns_store=patterns_store,\n"
          "        hotlists_store=hotlists_store, screening_lists=screening_lists, compute=compute,\n"
          "        repo_root=repo_root, influencers_store=influencers_store, models=models,\n"
          "        staging_storage=staging_storage, list_store=list_store,",
          (ROUTES,), "test_load_preview_reads_the_sources_declared_default_as_the_run_does"),
    Plant(21, "the command's dispatch drops the version", "cli/ospreyflow/main.py",
          "            replace_own_draft=args.replace_own_draft,\n", "",
          (CLI,), "test_replace_own_draft_reaches_the_route_through_the_command[True]"),
    Plant(22, "a default below a raised source marking carried (judged at read)",
          "services/api/studio_staging.py",
          "        if isinstance(own, str) and own and (", "        if False and (",
          (STAGED,), "test_a_default_left_below_a_raised_source_marking_is_not_carried"),
    Plant(23, "the setting's read gates (Edit pipelines) taken out", "services/api/app.py",
          "        Depends(require_right(Right.ADD_INGEST_FILES)),\n"
          "        Depends(require_studio_role(StudioRole.SOURCE_AUTHOR)),\n",
          "",
          (DS,), "test_an_approver_who_may_not_read_the_source_cannot_set_its_default"),
    Plant(24, "drafts not following a default change", "services/api/app.py",
          "    followed = await studio_recipes.follow_source(\n"
          "        dataset_id, edited.location, edited.handling, edited.legal_basis\n    )\n"
          "    await audit.record(\n        principal=principal,\n"
          '        action="set_dataset_source_default_marking",',
          "    followed: list[str] = []\n"
          "    await audit.record(\n        principal=principal,\n"
          '        action="set_dataset_source_default_marking",',
          (DS,), "test_a_source_approver_declares_changes_and_clears_a_default_marking_audited"),
    Plant(25, "the unmarked words for a marked table's empty cell", "services/ingest/staging_catalogue.py",
          "    unmarked = not any(c in row.cells for c in marked) or not any(c in other.cells for c in marked)",
          "    unmarked = all(c is None for c in mine) or all(c is None for c in theirs)",
          (MARKED,), "test_a_bound_column_with_an_empty_cell_is_not_filled_by_the_default"),
    Plant(26, "the governance edit's Add ingest files right", "services/api/app.py",
          "        # reading it needs (rule 4; the orchestrator's review of the carries step, item 2).\n"
          "        Depends(require_right(Right.ADD_INGEST_FILES)),\n",
          "",
          (DS,), "test_a_governance_edit_is_refused_to_someone_the_source_read_refuses"),
    Plant(27, "a default above the approver changed or cleared by them", "services/api/sources.py",
          "    if current and (\n        current not in levels", "    if False and (\n        current not in levels",
          (DS,), "test_a_default_above_the_approver_is_neither_changed_nor_cleared_by_them[cleared]"),
    Plant(28, "no change still written", "services/api/app.py",
          "    if marking == before.default_marking:", "    if False:",
          (DS,), "test_a_default_set_to_what_it_already_is_writes_nothing[the-same-level]"),
    Plant(29, "the confirmation not tied to the draft's version", "services/api/studio_release.py",
          "    if replace_own_draft == draft.version:", "    if replace_own_draft is not None:",
          (RELEASE,), "test_a_confirmation_for_another_version_of_the_own_draft_is_refused[False]"),
    Plant(30, "another person's draft replaced on confirmation", "services/api/studio_release.py",
          "    if draft.created_by != principal.id:", "    if False:",
          (RELEASE,), "test_another_persons_draft_is_refused_in_words_naming_them[True-False]"),
    Plant(31, "the write's own re-read of the draft", "services/api/studio_release.py",
          "    if held is not None:\n        raise held", "    if False:\n        raise held",
          (RELEASE,), "test_a_draft_opened_by_another_between_plan_and_write_is_refused_before_any_write"),
    Plant(32, "the store's refusal of a second draft (the open_draft window)",
          "services/api/target_models.py",
          "def _refuse_a_second_draft(draft: TargetModel | None) -> None:\n    if draft is not None:",
          "def _refuse_a_second_draft(draft: TargetModel | None) -> None:\n    if False:",
          (RELEASE,),
          "test_a_draft_opened_in_the_open_draft_window_is_refused_by_the_store_before_any_write"),
]


def main() -> int:
    pytest = [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider",
              "-q", "-rf"]  # fmt: skip
    ok = True
    # `carries_reds.py 5 6` runs only those plants, into a log of their own.
    chosen = {int(a) for a in sys.argv[1:]}
    log_path = LOG if not chosen else LOG.with_suffix(f".{'-'.join(sys.argv[1:])}.log")
    with log_path.open("w") as log:
        for plant in [p for p in PLANTS if not chosen or p.n in chosen]:
            path = CORE / plant.path
            text = path.read_text()
            count = text.count(plant.old)
            head = f"== plant {plant.n}: {plant.what} ({plant.path})"
            log.write(f"{head}\n--- old\n{plant.old}\n--- new\n{plant.new}\n")
            if count != 1:
                log.write(f"PLANT SITE FOUND {count} TIMES: not run\n\n")
                print(f"{head}: site found {count} times", file=sys.stderr)
                ok = False
                continue
            path.write_text(text.replace(plant.old, plant.new, 1))
            try:
                run = subprocess.run([*pytest, *plant.tests], capture_output=True, text=True)
            finally:
                path.write_text(text)
            log.write(run.stdout + run.stderr + "\n")
            red = f"FAILED {plant.tests[0]}::{plant.red}" in run.stdout or any(
                line.startswith("FAILED") and plant.red in line for line in run.stdout.splitlines()
            )
            verdict = "RED as named" if red else "NOT RED for the named test"
            log.write(f"=> {verdict}\n\n")
            print(f"{head}: {verdict}")
            ok = ok and red
            assert path.read_text() == text, f"{plant.path} not put back"
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
