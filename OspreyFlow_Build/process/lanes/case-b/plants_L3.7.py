"""L3.7's red record, reproducible (rule 15): each plant breaks one rule at the call site its test
reaches, runs that test, and puts the file back. Run from `OspreyFlow_Core` with offline ports
pinned (for example `ARCADEDB_HTTP_PORT=1 ARCADEDB_HOST=127.0.0.1 POSTGRES_PORT=1 VALKEY_PORT=1
CLICKHOUSE_HTTP_PORT=1`):

    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/plants_L3.7.py

Each row prints the plant, the tests run and pytest's tally; every plant must fail at least one.
The registry plant (`--live`, under a lease) runs against the leased Postgres.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

T = "../OspreyFlow_Build/tests/services/api/test_grading_change.py"
S = "../OspreyFlow_Build/tests/services/api/test_grading_setting.py"
A = "../OspreyFlow_Build/tests/cli/test_grading_answers.py"
R = "../OspreyFlow_Build/tests/services/api/test_grading_registry.py"
B = "../OspreyFlow_Build/tests/services/api/test_grading_boards.py"
L = "../OspreyFlow_Build/tests/services/api/test_grading_change_live.py"
G = "services/api/grading.py"
CMD = "scripts/grading_change.py"

Plant = tuple[str, str, list[tuple[str, str]], list[str]]

OFFLINE: list[Plant] = [
    ("the dry run writes as the change does", G,
     [("    if dry_run:\n        return plan\n    if pending:", "    if pending:")],
     [f"{T}::test_the_dry_run_writes_nothing_and_counts_each_mapping_line",
      f"{T}::test_the_command_says_each_mapping_lines_count_and_a_dry_run_writes_nothing"]),
    ("a second change overwrites the original with the middle grade", G,
     [("mapping.apply(item.grading), item.original or item.grading)",
       "mapping.apply(item.grading), item.grading)")],
     [f"{T}::test_every_item_keeps_its_original_grade_and_scheme_through_two_changes"]),
    ("a grade of the old scheme left unmapped is accepted", G,
     [('                raise MappingRefused(f"{part} {grade} of {old} is not mapped")',
       "                pass")],
     [f"{T}::test_a_mapping_that_does_not_cover_the_old_scheme_is_refused_in_words"]),
    ("a mapping from another scheme than the deployment's is run", G,
     [("    if mapping.from_scheme != current:\n", "    if False:\n")],
     [f"{T}::test_a_mapping_from_another_scheme_than_the_deployments_is_refused"]),
    ("an item in another scheme is skipped, the rest changed", G,
     [("    if elsewhere:\n        said", "    if False:\n        said")],
     [f"{T}::test_an_item_in_another_scheme_refuses_the_whole_change_before_any_write"]),
    ("an item that cannot be read back is skipped silently", G,
     [("    if inventory.unread:\n", "    if False:\n")],
     [f"{T}::test_a_registered_item_that_cannot_be_read_back_refuses_the_whole_change"]),
    ("no pre-flight: a rewrite's refusal met mid-run, after earlier writes", G,
     [("    problems = await items.check(pending)\n", "    problems: list[str] = []\n")],
     [f"{T}::test_an_item_whose_rewrite_would_be_refused_refuses_the_whole_change_first"]),
    ("the plan not said before the writes", G,
     [("    if announce is not None:\n        announce(plan)\n", "")],
     [f"{T}::test_the_plan_is_said_and_audited_before_the_first_write"]),
    ("the audit written only after the writes", G,
     [('        plan.stage = "started"\n        await audit(plan)',
       '        plan.stage = "started"\n        pass')],
     [f"{T}::test_the_plan_is_said_and_audited_before_the_first_write"]),
    ("the reader's view read and written back (sources and board withheld), guards removed", G,
     [("        # A read that is written back (ADR-130 Amendment 2): the body whole, its sources and its\n"
       "        # board kept, or the rewrite would store what a reader is shown in their place.\n"
       "        with sources_in_full():\n",
       "        # A read that is written back (ADR-130 Amendment 2): the body whole, its sources and its\n"
       "        # board kept, or the rewrite would store what a reader is shown in their place.\n"
       "        if True:\n"),
      ("            if drawn is None or element.provenance.sources_withheld or not drawn.board_id:\n",
       "            if drawn is None:\n"),
      ("        if element.provenance.sources_withheld or not drawn.board_id:\n            raise",
       "        if False:\n            raise")],
     [f"{T}::test_the_change_keeps_the_items_other_drawn_fields_and_its_marking"]),
    ("the write-back guard removed", G,
     [("        if element.provenance.sources_withheld or not drawn.board_id:\n            raise",
       "        if False:\n            raise")],
     [f"{T}::test_a_body_read_with_its_board_withheld_is_never_written_back"]),
    # Not a regrade: the fake (as the store) does not give back a withdrawn (reverted) element, so
    # without the filter the withdrawn item counts as unread and the change is refused whole.
    ("the withdrawn filter removed (then unread: the change refused whole)", G,
     [('            if i.withdrawn_at is None and i.kind in ("node", "link")',
       '            if i.kind in ("node", "link")')],
     [f"{T}::test_a_withdrawn_item_keeps_the_grade_it_was_drawn_with"]),
    ("a run again after a stop refuses the items it already changed", G,
     [("        elif scheme == mapping.to_scheme and item.original is not None:\n",
       "        elif False:\n")],
     [f"{T}::test_a_change_stopped_part_way_finishes_when_run_again"]),
    ("the command runs a mapping to another scheme than --to", CMD,
     [("    if mapping.to_scheme != to:\n", "    if False:\n")],
     [f"{T}::test_the_command_refuses_with_exit_1_and_writes_nothing"]),
    ("the command opens the stores with no store settings", CMD,
     [("    if not any(os.environ.get(name) for name in STORE_SETTINGS):\n", "    if False:\n")],
     [f"{T}::test_the_command_without_store_settings_refuses_before_opening_any"]),
    ("an unknown OSPREY_GRADING_SCHEME read as the default", "services/api/config.py",
     [("            raise GradingSchemeUnknown(\n"
       "                f\"OSPREY_GRADING_SCHEME is {raw!r}, not one of {', '.join(GRADING_SCHEMES)}\"\n"
       "            )\n", "            return cls()\n")],
     [f"{S}::test_a_scheme_the_conduit_does_not_know_stops_it_rather_than_guessing",
      f"{T}::test_the_command_without_store_settings_refuses_before_opening_any"]),
    ("the Conduit's start reads the scheme only after opening the stores", "services/api/app.py",
     [("    grading_settings = GradingSettings.from_env()\n", ""),
      ("    app.state.grading = grading_settings\n",
       "    app.state.grading = GradingSettings.from_env()\n")],
     [f"{S}::test_the_conduits_start_stops_on_an_unknown_scheme_before_opening_anything"]),
    ("the route falls back to 5x5x5 with no setting held", "services/api/app.py",
     [("    return held if held is not None else GradingSettings.from_env()",
       "    return held if held is not None else GradingSettings()")],
     [f"{S}::test_the_route_never_answers_a_default_for_a_scheme_it_cannot_read"]),
    ("a scheme name list that has drifted", "services/api/config.py",
     [('GRADING_SCHEMES = ("5x5x5", "3x5x2")', 'GRADING_SCHEMES = ("5x5x5", "3x5x2", "4x4")')],
     [f"{S}::test_every_list_of_the_scheme_names_is_the_schemes_of_grading_parts"]),
    ("the scheme not rendered into deployment.env", "harness/render.py",
     [('        f"OSPREY_GRADING_SCHEME={config.grading.scheme}",\n', "")],
     [f"{S}::test_the_scheme_is_rendered_for_the_conduit"]),
    ("the route answers without a signed-in principal", "services/api/app.py",
     [("    principal: PrincipalDep, grading: GradingSettingsDep\n) -> GradingSchemeAnswer:",
       "    grading: GradingSettingsDep\n) -> GradingSchemeAnswer:")],
     [f"{S}::test_the_route_answers_nobody_signed_out"]),
    ("the route answers the default, not the setting", "services/api/app.py",
     [("    return GradingSchemeAnswer.of(grading.scheme)",
       '    return GradingSchemeAnswer.of("5x5x5")')],
     [f"{S}::test_the_route_answers_the_scheme_and_its_grades_to_anyone_signed_in"]),
    ("an opened board offers 5x5x5 whatever the setting", "services/api/app.py",
     [('            "grading_scheme": grading.scheme,\n', "")],
     [f"{B}::test_an_opened_board_offers_the_deployments_scheme"]),
    ("a grade in another scheme drawn as given", "services/api/app.py",
     [("    if given is not None and given.scheme != grading.scheme:\n",
       "    if False:\n")],
     [f"{B}::test_a_drawn_item_in_another_scheme_is_refused_before_anything_is_written",
      f"{B}::test_a_drawn_link_in_another_scheme_is_refused_before_anything_is_written",
      f"{B}::test_an_edit_to_a_grade_in_another_scheme_is_refused_before_anything_is_written"]),
    ("the edit route alone not checked", "services/api/app.py",
     [('    """The author edits their own item; a marking is never lowered (decision 5)."""\n'
       "    _graded_in_the_deployments_scheme(body.grading, grading)\n",
       '    """The author edits their own item; a marking is never lowered (decision 5)."""\n')],
     [f"{B}::test_an_edit_to_a_grade_in_another_scheme_is_refused_before_anything_is_written"]),
    ("the install's chosen scheme never reaches osprey.yaml", "cli/ospreyflow/answers.py",
     [('        config["grading"] = {**(config.get("grading") or {}), '
       '"scheme": answers.grading_scheme}\n', "        pass\n")],
     [f"{A}::test_the_grading_scheme_is_5x5x5_unless_the_answers_choose_another"]),
    ("a named config never gains the chosen scheme", "cli/ospreyflow/answers.py",
     [('            loaded["grading"] = {**(loaded.get("grading") or {}), '
       '"scheme": answers.grading_scheme}\n', "            pass\n")],
     [f"{A}::test_a_named_config_gains_the_chosen_scheme_and_keeps_the_rest"]),
    ("an unknown install scheme accepted", "cli/ospreyflow/answers.py",
     [("    if str(scheme) not in GRADING_SCHEMES:\n", "    if False:\n")],
     [f"{A}::test_a_scheme_that_is_not_one_is_refused_naming_it"]),
]

LIVE: list[Plant] = [
    ("the command's adapter given no ontology", CMD,
     [("    adapter.use_schema(ontology)\n", "")],
     [f"{L}::test_the_change_rewrites_each_grade_in_the_store_keeping_its_original_and_the_rest"]),
    ("the dry run writes as the change does, against ArcadeDB", G,
     [("    if dry_run:\n        return plan\n    if pending:", "    if pending:")],
     [f"{L}::test_the_change_rewrites_each_grade_in_the_store_keeping_its_original_and_the_rest"]),
    ("a second change overwrites the original, against ArcadeDB", G,
     [("mapping.apply(item.grading), item.original or item.grading)",
       "mapping.apply(item.grading), item.grading)")],
     [f"{L}::test_the_change_rewrites_each_grade_in_the_store_keeping_its_original_and_the_rest"]),
    ("the node's rewrite written into the source dataset, against ArcadeDB", G,
     [("datasets=element.datasets,\n                        resolution=element.resolution,",
       "datasets=[\"src\"],\n                        resolution=element.resolution,")],
     [f"{L}::test_the_change_rewrites_each_grade_in_the_store_keeping_its_original_and_the_rest"]),
    ("the node's resolution state not carried (a fresh one written)", G,
     [("                        resolution=element.resolution, load_id=audit.load_id,\n",
       "                        load_id=audit.load_id,\n")],
     [f"{L}::test_the_change_rewrites_each_grade_in_the_store_keeping_its_original_and_the_rest"]),
    ("the link's occurrences counted again", G,
     [("occurrences=0, load_id=audit.load_id", "load_id=audit.load_id")],
     [f"{L}::test_the_change_rewrites_each_grade_in_the_store_keeping_its_original_and_the_rest"]),
    ("the registry read includes withdrawn items", CMD,
     [('    "WHERE withdrawn_at IS NULL AND kind IN', '    "WHERE kind IN')],
     [f"{R}::test_the_registry_read_is_every_cases_live_drawn_nodes_and_links"]),
    ("the registry read includes pictures and match links", CMD,
     [("AND kind IN ('node', 'link') ORDER BY", "ORDER BY")],
     [f"{R}::test_the_registry_read_is_every_cases_live_drawn_nodes_and_links"]),
]


def run(plants: list[Plant]) -> int:
    held = 0
    for title, file, swaps, tests in plants:
        path = pathlib.Path(file)
        before = path.read_text()
        after = before
        for old, new in swaps:
            assert after.count(old) == 1, f"{title}: the plant's text is not found once in {file}"
            after = after.replace(old, new)
        path.write_text(after)
        try:
            done = subprocess.run(
                [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p",
                 "no:warnings", "-p", "no:randomly", *tests],
                capture_output=True, text=True, check=False,
            )  # fmt: skip
        finally:
            path.write_text(before)
        tally = [line for line in done.stdout.splitlines() if " passed" in line or " failed" in line]
        red = done.returncode != 0
        held += 0 if red else 1
        names = ", ".join(t.split("::")[1] for t in tests)
        print(f"| {title} | `{file}` | {names} | {tally[-1].strip('= ') if tally else done.returncode} |")
    return held


if __name__ == "__main__":
    still_green = run(LIVE if "--live" in sys.argv else OFFLINE)
    sys.exit(1 if still_green else 0)
