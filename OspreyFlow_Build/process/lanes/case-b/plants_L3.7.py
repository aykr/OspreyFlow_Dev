"""L3.7's red record, reproducible (rule 15): each plant breaks one rule at the call site its test
reaches, runs that test, and puts the file back. Run from `OspreyFlow_Core` with offline ports
pinned (for example `ARCADEDB_HTTP_PORT=1 ARCADEDB_HOST=127.0.0.1 POSTGRES_PORT=1 VALKEY_PORT=1
CLICKHOUSE_HTTP_PORT=1`):

    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/plants_L3.7.py

Each row prints the plant, the tests run and pytest's tally; every plant must fail at least one.
The registry plant (`--live`, under a lease) runs against the leased Postgres.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

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
     [("            else:\n                plan.already_in_new += 1\n",
       "            else:\n                elsewhere.setdefault(scheme, []).append(item.id)\n")],
     [f"{T}::test_an_item_drawn_in_the_new_scheme_is_left_and_counted"]),
    ("an item off the deployment's scheme mapped as if on it", G,
     [("                current.check(item.grading)\n            except ValueError:\n"
       "                off_scheme.append(item.id)\n                continue\n",
       "                current.check(item.grading)\n            except ValueError:\n"
       "                pass\n")],
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
     [("            if item.original is not None:\n                plan.already_changed += 1\n",
       "            if False:\n                plan.already_changed += 1\n")],
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
    ("a second scheme line rendered (a file's path beside its name)", "harness/render.py",
     [("        *_grading_env(config),\n",
       '        f"OSPREY_GRADING_SCHEME={config.grading.scheme}",\n        *_grading_env(config),\n')],
     [f"{S}::test_a_scheme_file_is_read_beside_osprey_yaml_and_rendered_with_its_grades"]),
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
     [("    if code in grading_verb.NOTHING_CHANGED:\n", "    if code == 64:\n")],
     [f"{V}::test_a_refused_change_leaves_the_setting_and_starts_the_conduit_again"]),
    ("the Conduit not started in the new scheme", VERB,
     [('        ctx.step("start the Conduit", [*compose(directory), "up", "-d", "--wait", "api"])\n'
       "    except StepFailed:", "    except StepFailed:")],
     [f"{V}::test_a_change_stops_the_conduit_then_sets_the_scheme_renders_and_starts_it",
      f"{V}::test_a_change_with_the_conduit_already_stopped_starts_it_in_the_new_scheme"]),
    ("the scheme file not kept beside osprey.yaml", EDIT,
     [("        shutil.copyfile(scheme_file, kept)\n", "        pass\n")],
     [f"{V}::test_a_scheme_file_is_mounted_and_kept_beside_osprey_yaml"]),
    ("the scheme line replaced whole, its comment lost", EDIT,
     [("        body = body[: line.start(2)] + scheme + body[line.end(2) :]",
       '        body = body[: line.start(2)] + scheme + "\\n" + body[line.end() :]')],
     [f"{V}::test_the_setting_is_edited_in_place"]),
    ("the token blind to the mapping (its schemes alone)", G,
     [('        "mapping": mapping.canonical(),\n', "")],
     [f"{T}::test_another_mapping_between_the_same_schemes_gives_another_token"]),
    ("an item already in the new scheme not checked against it", G,
     [("            try:\n                target.check(item.grading)\n            except ValueError:\n"
       "                off_scheme.append(item.id)\n                continue\n", "")],
     [f"{T}::test_an_item_already_in_the_new_scheme_off_its_grades_refuses_naming_it"]),
    ("the Conduit check failing open on a timeout", CMD,
     [("    except httpx.HTTPError:\n        return True\n", "    except httpx.HTTPError:\n        return False\n")],
     [f"{T}::test_the_conduit_is_taken_as_stopped_only_when_nothing_answers"]),
    ("the Conduit check taking a 503 as stopped", CMD,
     [('            await client.get(f"{url.rstrip(\'/\')}/healthz")\n',
       '            if (await client.get(f"{url.rstrip(\'/\')}/healthz")).status_code != 200:\n'
       "                return False\n")],
     [f"{T}::test_the_conduit_is_taken_as_stopped_only_when_nothing_answers"]),
    ("an unforeseen failure exiting 1, as a refusal", CMD,
     [("        return STOPPED\n", "        return 1\n")],
     [f"{T}::test_an_unforeseen_failure_exits_as_stopped_never_as_refused"]),
    ("a killed or unforeseen exit taken as nothing changed", VERB,
     [("    if code in grading_verb.NOTHING_CHANGED:\n", "    if code not in (0, 2):\n")],
     [f"{V}::test_any_failure_but_a_refusal_leaves_the_conduit_stopped"]),
    ("a restarting Conduit taken as stopped", VERB,
     [('    stopped = {"exited", "created", "dead", ""}\n'
       '    return any(str(row.get("State", "")) not in stopped for row in _services(output))',
       '    return any(str(row.get("State", "")) == "running" for row in _services(output))')],
     [f"{V}::test_a_conduit_not_stopped_is_taken_as_running"]),
    ("the setting not read back after the edit", VERB,
     [('    if grading_verb.scheme_set(config.read_text(encoding="utf-8")) != value:\n',
       "    if False:\n")],
     [f"{V}::test_a_setting_the_edit_did_not_take_is_said_and_nothing_started"]),
    ("a failed render after the change said as nothing", VERB,
     [("    except StepFailed:\n        print(\n", "    except StepFailed:\n        raise\n        print(\n")],
     [f"{V}::test_a_render_that_fails_after_the_change_says_the_conduit_is_stopped"]),
    ("a column-0 comment ends the grading section", EDIT,
     [('_TOP_LEVEL = re.compile(r"^[^\\s#]", re.MULTILINE)', '_TOP_LEVEL = re.compile(r"^\\S", re.MULTILINE)')],
     [f"{V}::test_the_setting_is_edited_in_place"]),
    ("the scheme file left behind by the copy of osprey.yaml", "harness/render.py",
     [("            write_shared(kept, source.read_text(encoding=\"utf-8\"))\n", "            pass\n")],
     [f"{S}::test_a_scheme_files_grade_is_safe_in_deployment_env".replace(
         "test_a_scheme_files_grade_is_safe_in_deployment_env",
         "test_a_scheme_file_goes_with_the_copy_of_osprey_yaml")]),
    ("a grade unsafe in deployment.env accepted", "packages/schemas/domain.py",
     [("            if any(not _GRADE.fullmatch(g) for g in grades):\n", "            if False:\n")],
     [f"{S}::test_a_scheme_files_grade_is_safe_in_deployment_env"]),
    ("the Conduit's graph passes regrade_drawn on", "services/api/dataset_scope.py",
     [('        if name == "regrade_drawn":', '        if name == "regrade_drawn-never":')],
     [f"{S}::test_the_conduits_graph_never_offers_regrade_drawn"]),
]

LIVE: list[Plant] = [
    ("the store's regrade writes no original", ADAPTER,
     [('                "original_grading": original.model_dump(mode="json"),\n', "")],
     [C]),
    ("the store's regrade takes a superseded element (both guards)", ADAPTER,
     [('        if row.get("reverted") is True or row.get("superseded_by") or not isinstance(drawn, dict):',
       '        if row.get("reverted") is True or not isinstance(drawn, dict):'),
      ('            "AND (reverted IS NULL OR reverted = false) AND superseded_by IS NULL",',
       '            "AND (reverted IS NULL OR reverted = false)",')],
     [C]),
    ("the store's regrade takes a reverted element (both guards)", ADAPTER,
     [('        if row.get("reverted") is True or row.get("superseded_by") or not isinstance(drawn, dict):',
       '        if row.get("superseded_by") or not isinstance(drawn, dict):'),
      ('            "AND (reverted IS NULL OR reverted = false) AND superseded_by IS NULL",',
       '            "AND superseded_by IS NULL",')],
     [C]),
    ("the dry run makes the audit's table", CMD,
     [("    audit_writer: AuditWriter | None = None\n",
       "    audit_writer: AuditWriter | None = await AuditWriter.connect(dsn)\n")],
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


def _pytest(tests: list[str]) -> subprocess.CompletedProcess[str]:
    """Each run with a bytecode cache of its own: two plants of one file can leave it the same
    size within the same second, and Python would then run the first plant's cached bytecode for
    the second (found 9 November 2026: a plant reported green that fails by hand)."""
    with tempfile.TemporaryDirectory() as cache:
        return subprocess.run(
            [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p", "no:warnings",
             "-p", "no:randomly", "-p", "no:cacheprovider", *tests],
            capture_output=True, text=True, check=False,
            env={**os.environ, "PYTHONPYCACHEPREFIX": cache},
        )  # fmt: skip


def _tally(done: subprocess.CompletedProcess[str]) -> str:
    lines = [ln for ln in done.stdout.splitlines() if " passed" in ln or " failed" in ln
             or " error" in ln]  # fmt: skip
    return lines[-1].strip("= ") if lines else f"exit {done.returncode}"


def run(plants: list[Plant]) -> int:
    """Each plant red, for the right reason: the named tests pass unplanted first (the suite is
    green before), and a plant counts as red only when pytest reports failed tests and no error
    (exit 1): a collection, import or fixture error the plant causes proves nothing."""
    every = sorted({t for _, _, _, tests in plants for t in tests})
    baseline = _pytest(every)
    if baseline.returncode != 0:
        print(f"Not green unplanted: {_tally(baseline)}")
        print(baseline.stdout[-3000:])
        return len(plants)
    print(f"Unplanted: {_tally(baseline)}")
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
            done = _pytest(tests)
        finally:
            path.write_text(before)
        tally = _tally(done)
        red = done.returncode == 1 and " failed" in tally and " error" not in tally
        held += 0 if red else 1
        names = ", ".join(t.split("::")[1] for t in tests)
        print(f"| {title} | `{file}` | {names} | {tally}{'' if red else ' (NOT RED)'} |")
    return held


if __name__ == "__main__":
    still_green = run(LIVE if "--live" in sys.argv else OFFLINE)
    sys.exit(1 if still_green else 0)
