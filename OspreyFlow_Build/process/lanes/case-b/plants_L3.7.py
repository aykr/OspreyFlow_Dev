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
V = "../OspreyFlow_Build/tests/cli/test_grading_verb.py"
R = "../OspreyFlow_Build/tests/services/api/test_grading_registry.py"
B = "../OspreyFlow_Build/tests/services/api/test_grading_boards.py"
L = "../OspreyFlow_Build/tests/services/api/test_grading_change_live.py"
C = ("../OspreyFlow_Build/tests/conformance/graph_port/test_suite.py::"
     "test_regrade_drawn_changes_the_grade_and_original_alone")
G = "services/api/grading.py"
CMD = "scripts/grading_change.py"
APP = "services/api/app.py"
CFG = "services/api/config.py"
VERB = "cli/ospreyflow/main.py"
EDIT = "cli/ospreyflow/grading.py"
ADAPTER = "packages/adapters/graph_arcadedb/adapter.py"
LIVE_TEST = f"{L}::test_the_command_changes_every_drawn_grade_in_the_real_stores"

Plant = tuple[str, str, list[tuple[str, str]], list[str]]

OFFLINE: list[Plant] = [
    # --- the change (services/api/grading.py) ---
    ("the dry run writes as the change does", G,
     [("    if dry_run:\n        return plan\n    if pending:", "    if pending:")],
     [f"{T}::test_the_dry_run_writes_nothing_and_counts_each_mapping_line",
      f"{T}::test_the_command_says_each_mapping_lines_count_and_a_dry_run_writes_nothing"]),
    ("the change run without its dry run's token", G,
     [("    if not dry_run and confirm != plan.token:\n", "    if False:\n")],
     [f"{T}::test_the_change_is_refused_without_its_dry_runs_token_for_this_state"]),
    ("the token blind to the drawn items' state", G,
     [('        "items": sorted(item.state() for item in items),', '        "items": [],')],
     [f"{T}::test_the_change_is_refused_without_its_dry_runs_token_for_this_state"]),
    ("the token blind to an edit (no revision)", G,
     [('            getattr(audit, "revision", None),', "            None,")],
     [f"{T}::test_an_edit_since_the_dry_run_is_another_state"]),
    ("a second change overwrites the original with the middle grade", G,
     [("mapping.apply(item.grading), item.original or item.grading)",
       "mapping.apply(item.grading), item.grading)")],
     [f"{T}::test_every_item_keeps_its_original_grade_and_scheme_through_two_changes"]),
    ("a grade of the old scheme left unmapped is accepted", G,
     [('                raise MappingRefused(f"{part} {grade} of {old} is not mapped")',
       "                pass")],
     [f"{T}::test_a_mapping_that_does_not_cover_the_old_scheme_is_refused_in_words"]),
    ("a mapping from another scheme than the deployment's is run", G,
     [("    if mapping.from_scheme != current.scheme:\n", "    if False:\n")],
     [f"{T}::test_a_mapping_from_another_scheme_than_the_deployments_is_refused"]),
    ("an item in a third scheme is skipped, the rest changed", G,
     [("    if elsewhere:\n", "    if False:\n")],
     [f"{T}::test_an_item_in_a_third_scheme_refuses_the_whole_change_naming_it"]),
    ("an item drawn in the new scheme refused (no way out)", G,
     [("        elif scheme == mapping.to_scheme:\n            plan.already_in_new += 1\n", "")],
     [f"{T}::test_an_item_drawn_in_the_new_scheme_is_left_and_counted"]),
    ("an item off the deployment's scheme mapped as if on it", G,
     [("            except ValueError:\n                off_scheme.append(item.id)\n"
       "                continue\n", "            except ValueError:\n                pass\n")],
     [f"{T}::test_an_item_whose_grade_is_not_of_the_deployments_scheme_refuses_naming_it"]),
    ("an item that cannot be read back is skipped silently", G,
     [("    if inventory.unread:\n", "    if False:\n")],
     [f"{T}::test_a_registered_item_that_cannot_be_read_back_refuses_the_whole_change"]),
    ("the unread refusal counts but names no item", G,
     [("unknown: {named(inventory.unread)}. Nothing was changed.", "unknown. Nothing was changed.")],
     [f"{T}::test_a_registered_item_that_cannot_be_read_back_refuses_the_whole_change"]),
    ("every id named, none counted", G,
     [('    shown = ", ".join(ids[:SHOWN_IDS])', '    shown = ", ".join(ids)')],
     [f"{T}::test_a_refusal_names_ten_ids_and_counts_the_rest"]),
    # Not a regrade: the fake (as the store) does not give back a withdrawn (reverted) element, so
    # without the filter the withdrawn item counts as unread and the change is refused whole.
    ("the withdrawn filter removed (then unread: the change refused whole)", G,
     [('            if i.withdrawn_at is None and i.kind in ("node", "link")',
       '            if i.kind in ("node", "link")')],
     [f"{T}::test_a_withdrawn_item_keeps_the_grade_it_was_drawn_with"]),
    ("a run again after a stop counts its changed items as drawn in the new scheme", G,
     [("        elif scheme == mapping.to_scheme and item.original is not None:\n",
       "        elif False:\n")],
     [f"{T}::test_a_change_stopped_part_way_finishes_when_run_again"]),
    ("a regrade the store refused counted as changed", G,
     [("        if not await self.graph.regrade_drawn(item.id, grading, original):\n",
       "        if not (await self.graph.regrade_drawn(item.id, grading, original) or True):\n")],
     [f"{T}::test_an_element_gone_from_under_the_change_stops_it_saying_so"]),
    ("the plan not said before the writes", G,
     [("    if announce is not None:\n        announce(plan)\n", "")],
     [f"{T}::test_the_plan_is_said_and_audited_before_the_first_write"]),
    ("the audit written only after the writes", G,
     [('        plan.stage = "started"\n        await audit(plan)',
       '        plan.stage = "started"\n        pass')],
     [f"{T}::test_the_plan_is_said_and_audited_before_the_first_write"]),
    # --- the command (scripts/grading_change.py) ---
    ("the command runs a mapping to another scheme than --to", CMD,
     [("    if mapping.to_scheme != target.scheme:\n        say(", "    if False:\n        say(")],
     [f"{T}::test_the_command_refuses_with_exit_1_and_writes_nothing"]),
    ("the command opens the stores with no store settings", CMD,
     [("    if not any(os.environ.get(name) for name in STORE_SETTINGS):\n", "    if False:\n")],
     [f"{T}::test_the_command_without_store_settings_refuses_before_opening_any"]),
    ("the change run beside a running Conduit", CMD,
     [("    if not args.dry_run and await answers(args.conduit_url):\n", "    if False:\n")],
     [f"{T}::test_the_change_is_refused_while_the_conduit_answers_before_any_store_is_opened"]),
    ("a scheme file may take a built-in scheme's name", "packages/schemas/domain.py",
     [("        if self.scheme in GRADING_PARTS and self.parts() != GRADING_PARTS[self.scheme]:\n",
       "        if False:\n")],
     [f"{T}::test_a_target_that_is_no_scheme_is_refused_in_words"]),
    ("a scheme's grades never checked", "packages/schemas/domain.py",
     [("            if getattr(grading, part) not in grades:\n", "            if False:\n")],
     [f"{B}::test_a_scheme_files_grades_are_offered_and_checked",
      f"{T}::test_an_item_whose_grade_is_not_of_the_deployments_scheme_refuses_naming_it"]),
    # --- the setting ---
    ("an unknown OSPREY_GRADING_SCHEME read as the default", CFG,
     [("            raise GradingSchemeUnknown(\n"
       "                f\"OSPREY_GRADING_SCHEME is {raw!r}: neither a built-in scheme \"\n",
       "            return cls()\n            raise GradingSchemeUnknown(\n"
       "                f\"OSPREY_GRADING_SCHEME is {raw!r}: neither a built-in scheme \"\n")],
     [f"{S}::test_a_scheme_the_conduit_does_not_know_stops_it_rather_than_guessing",
      f"{S}::test_the_conduit_reads_a_scheme_files_grades_and_fails_closed_without_them"]),
    ("a scheme file's grades taken for another scheme's", CFG,
     [("        if grades.scheme != raw:\n", "        if False:\n")],
     [f"{S}::test_the_conduit_reads_a_scheme_files_grades_and_fails_closed_without_them"]),
    ("a list of the names of the Conduit's own", CFG,
     [("class GradingSchemeUnknown(ValueError):",
       'GRADING_SCHEMES = ("5x5x5", "3x5x2")\n\n\nclass GradingSchemeUnknown(ValueError):')],
     [f"{S}::test_the_built_in_schemes_names_are_listed_once"]),
    ("the Conduit's start reads the scheme only after opening the stores", APP,
     [("    grading_settings = GradingSettings.from_env()\n", ""),
      ("    app.state.grading = grading_settings\n",
       "    app.state.grading = GradingSettings.from_env()\n")],
     [f"{S}::test_the_conduits_start_stops_on_an_unknown_scheme_before_opening_anything"]),
    ("the route falls back to 5x5x5 with no setting held", APP,
     [("    return held if held is not None else GradingSettings.from_env()",
       "    return held if held is not None else GradingSettings()")],
     [f"{S}::test_the_route_never_answers_a_default_for_a_scheme_it_cannot_read"]),
    ("the scheme not rendered into deployment.env", "harness/render.py",
     [('    lines = [f"OSPREY_GRADING_SCHEME={scheme.scheme}"]', "    lines: list[str] = []")],
     [f"{S}::test_the_scheme_is_rendered_for_the_conduit"]),
    ("a scheme file's grades not rendered", "harness/render.py",
     [('        lines.append(f"OSPREY_GRADING_GRADES={scheme.model_dump_json()}")', "        pass")],
     [f"{S}::test_a_scheme_file_is_read_beside_osprey_yaml_and_rendered_with_its_grades"]),
    ("the scheme file never read", "harness/render.py",
     [("    config.grading.read_file(path.parent)\n", "")],
     [f"{S}::test_a_scheme_file_is_read_beside_osprey_yaml_and_rendered_with_its_grades",
      f"{S}::test_a_scheme_file_that_cannot_be_read_or_is_no_scheme_is_refused_naming_it"]),
    ("any value taken as a scheme", "packages/schemas/deployment.py",
     [('        if value in BUILT_IN_GRADING_SCHEMES or value.endswith((".yaml", ".yml")):',
       "        if True:")],
     [f"{A}::test_a_scheme_that_is_not_one_is_refused_by_the_deployment_schema_naming_it"]),
    ("the route answers without a signed-in principal", APP,
     [("    principal: PrincipalDep, grading: GradingSettingsDep\n) -> GradingSchemeAnswer:",
       "    grading: GradingSettingsDep\n) -> GradingSchemeAnswer:")],
     [f"{S}::test_the_route_answers_nobody_signed_out"]),
    ("the route answers the default, not the setting", APP,
     [("    return grading.grades\n", '    return GradingSchemeAnswer.of("5x5x5")\n')],
     [f"{S}::test_the_route_answers_the_scheme_and_its_grades_to_anyone_signed_in"]),
    # --- the boards ---
    ("an opened board offers 5x5x5 whatever the setting", APP,
     [('            "grading_scheme": grading.scheme,\n', "")],
     [f"{B}::test_an_opened_board_offers_the_deployments_scheme"]),
    ("an opened board offers no grades", APP,
     [('            "grading_grades": grading.grades,\n', "")],
     [f"{B}::test_a_scheme_files_grades_are_offered_and_checked"]),
    ("a grade in another scheme drawn as given", APP,
     [("    if given is None:\n        return\n", "    if True:\n        return\n")],
     [f"{B}::test_a_drawn_item_in_another_scheme_is_refused_before_anything_is_written",
      f"{B}::test_a_drawn_link_in_another_scheme_is_refused_before_anything_is_written",
      f"{B}::test_an_edit_to_a_grade_in_another_scheme_is_refused_before_anything_is_written"]),
    ("the edit route alone not checked", APP,
     [('    """The author edits their own item; a marking is never lowered (decision 5)."""\n'
       "    _graded_in_the_deployments_scheme(body.grading, grading)\n",
       '    """The author edits their own item; a marking is never lowered (decision 5)."""\n')],
     [f"{B}::test_an_edit_to_a_grade_in_another_scheme_is_refused_before_anything_is_written"]),
    # --- the install answers ---
    ("the install's chosen scheme never reaches osprey.yaml", "cli/ospreyflow/answers.py",
     [('        config["grading"] = {**(config.get("grading") or {}), '
       '"scheme": answers.grading_scheme}\n', "        pass\n")],
     [f"{A}::test_the_grading_scheme_is_5x5x5_unless_the_answers_choose_another"]),
    ("a named config never gains the chosen scheme", "cli/ospreyflow/answers.py",
     [('            loaded["grading"] = {**(loaded.get("grading") or {}), '
       '"scheme": answers.grading_scheme}\n', "            pass\n")],
     [f"{A}::test_a_named_config_gains_the_chosen_scheme_and_keeps_the_rest"]),
    ("a scheme that is not a name passed on", "cli/ospreyflow/answers.py",
     [("    if not isinstance(scheme, str):\n", "    if False:\n")],
     [f"{A}::test_a_scheme_that_is_not_a_name_or_a_key_that_is_not_one_is_refused"]),
    # --- the verb ---
    ("the change run beside a running Conduit, unasked", VERB,
     [("    if not args.dry_run and running and not args.stop_api:\n", "    if False:\n")],
     [f"{V}::test_the_change_is_refused_while_the_conduit_runs_unless_told_to_stop_it"]),
    ("the dry run run as a change", VERB,
     [("    if args.dry_run:\n        return ctx.run(argv, cwd=ctx.product)\n", "")],
     [f"{V}::test_the_dry_run_runs_in_a_one_shot_beside_a_running_conduit_and_changes_nothing"]),
    ("the setting changed after a refused change", VERB,
     [("    if code != 0:\n        if running:\n", "    if code not in (0, 1):\n        if running:\n")],
     [f"{V}::test_a_refused_change_leaves_the_setting_and_starts_the_conduit_again"]),
    ("a change stopped part way started again in the old scheme", VERB,
     [("    if code == 2:\n", "    if False:\n")],
     [f"{V}::test_a_change_stopped_part_way_leaves_the_conduit_stopped_and_the_setting_as_it_was"]),
    ("the Conduit not started in the new scheme", VERB,
     [('    ctx.step("start the Conduit", [*compose(directory), "up", "-d", "--wait", "api"])\n'
       '    print("The Conduit is started', '    print("The Conduit is started')],
     [f"{V}::test_a_change_stops_the_conduit_then_sets_the_scheme_renders_and_starts_it",
      f"{V}::test_a_change_with_the_conduit_already_stopped_starts_it_in_the_new_scheme"]),
    ("the scheme file not kept beside osprey.yaml", EDIT,
     [("        shutil.copyfile(scheme_file, kept)\n", "        pass\n")],
     [f"{V}::test_a_scheme_file_is_mounted_and_kept_beside_osprey_yaml"]),
    ("the scheme line replaced whole, its comment lost", EDIT,
     [("        body = body[: line.start(2)] + scheme + body[line.end(2) :]",
       '        body = body[: line.start(2)] + scheme + "\\n" + body[line.end() :]')],
     [f"{V}::test_the_setting_is_edited_in_place"]),
]

LIVE: list[Plant] = [
    ("the store's regrade writes no original", ADAPTER,
     [('                "original_grading": original.model_dump(mode="json"),\n', "")],
     [C]),
    ("the store's regrade takes a reverted element", ADAPTER,
     [('        if row.get("reverted") is True or row.get("superseded_by") or not isinstance(drawn, dict):',
       "        if not isinstance(drawn, dict):")],
     [C]),
    ("the command's adapter given no ontology", CMD,
     [("    adapter.use_schema(ontology)\n", "")],
     [LIVE_TEST]),
    ("the command's ontology not composed with the proposals", CMD,
     [("    return compose_ontology(load_deployment_ontology(), proposals, revision=revision)",
       "    return load_deployment_ontology()")],
     [LIVE_TEST]),
    ("the dry run makes the audit's table", CMD,
     [("    audit_writer = None if args.dry_run else await AuditWriter.connect(dsn)",
       "    audit_writer = await AuditWriter.connect(dsn)")],
     [LIVE_TEST]),
    ("the audit not saying who changed it is as typed", CMD,
     [('resolved_query={**plan.record(), "changed_by_as_typed": True},',
       "resolved_query=plan.record(),")],
     [LIVE_TEST]),
    ("the dry run writes as the change does, against the stores", G,
     [("    if dry_run:\n        return plan\n    if pending:", "    if pending:")],
     [LIVE_TEST]),
    ("a second change overwrites the original, against the stores", G,
     [("mapping.apply(item.grading), item.original or item.grading)",
       "mapping.apply(item.grading), item.grading)")],
     [LIVE_TEST]),
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
