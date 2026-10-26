"""The seed's load order, one constant (ADR-127 Amendment 23): `pid_files.SEED_ORDER` names every
PID source file once, with its recipe and the moment it loads at, and every PID recipe test loads
its steps in an order that is a subsequence of it. What a mistake would do, and the case that
catches it:

- a source file or a recipe missing from the order, or named twice, or the batches not separate
  (`test_the_order_names_every_source_file_once_and_every_recipe`);
- the order not the amendment's (`test_the_order_is_the_amendments`);
- a stage at a moment other than the plan's for that file
  (`test_each_stage_is_at_the_moment_the_plan_loads_its_file`);
- a recipe test that loads out of the seed's order, so what it proves is not what the seed does
  (`test_every_recipe_tests_load_steps_are_a_subsequence_of_the_seed_order`), and that check itself
  failing for one such test (`test_the_subsequence_check_fails_for_a_step_out_of_order`);
- a recipe test that leaves out an earlier file of the seed which writes an element the tested file
  also writes, so the marking the test sees for it is not the seed's: a node the omitted file would
  create first, or a link any omitted row writes
  (`test_no_recipe_test_omits_an_earlier_file_that_writes_an_element_its_file_also_writes`), and
  that check itself failing for one such omission
  (`test_the_omission_check_fails_for_a_file_that_marks_an_element_first`)."""

from __future__ import annotations

import importlib
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from demo_fixtures import pid_files, pid_plan
from tests.ingest.pid_golden_support import FIXTURES, PLAN, RECIPE_OF, Step

TESTS = Path(__file__).resolve().parent
ORDER = pid_files.SEED_ORDER
FILES = [s.file for s in ORDER]
#: Amendment 23's first bullet, one recipe file per stage, as the amendment lists them.
AMENDMENT = [
    "pid_establishment_plan_recipe.yaml",  # R11
    "pid_nomis_prisoners_recipe.yaml",  # R1
    "pid_nomis_cell_stays_recipe.yaml",  # R14
    "pid_nomis_cell_shares_recipe.yaml",  # R2
    "pid_nomis_visits_recipe.yaml",  # R3
    "pid_nomis_incidents_recipe.yaml",  # R4
    "pid_number_owners_recipe.yaml",  # R16
    "pid_soc_nominals_recipe.yaml",  # R12
    "pid_family_and_associates_recipe.yaml",  # R13
    "pid_codefendants_recipe.yaml",  # R8
    "pid_conflicts_recipe.yaml",  # R15
    "pid_pin_calls_recipe.yaml",  # R5
    "pid_prisoner_money_recipe.yaml",  # R7
    "pid_seized_comms_recipe.yaml",  # R6 batch 1
    "pid_throwover_log_recipe.yaml",  # R10
    "pid_intel_reports_recipe.yaml",  # R9
    "pid_report_incidents_recipe.yaml",  # R17
    "pid_seized_comms_recipe.yaml",  # R6 batch 2
]


def is_subsequence(steps: Sequence[str], order: Sequence[str]) -> bool:
    """Whether `steps` appear in `order`, each once, in the same relative order."""
    remaining = iter(order)
    return all(step in remaining for step in steps)


def _tested_of(module: Any) -> list[str]:
    """The file or files a recipe test is about."""
    return [module.FILE] if hasattr(module, "FILE") else [module.BATCH_1, module.BATCH_2]


def _stages_of(module: Any) -> list[Step]:
    """What a recipe test loads, in the order it loads it, as steps: its `_steps()`, `_before()` or
    `BEFORE` (a partial step keeps the predicate that picks the plan's rows it loads), then the file
    or files it tests, whole."""
    if callable(getattr(module, "_steps", None)):
        held: Iterable[object] = module._steps()
    elif callable(getattr(module, "_before", None)):
        held = module._before()
    else:
        held = getattr(module, "BEFORE", ())
    steps = [s if isinstance(s, Step) else Step(str(s)) for s in held]
    tested = _tested_of(module)
    return [*steps, *(Step(f) for f in tested if f not in {s.file for s in steps})]


def _steps_of(module: Any) -> list[str]:
    return [s.file for s in _stages_of(module)]


def _recipe_test_modules() -> dict[str, object]:
    return {
        path.stem: importlib.import_module(f"tests.ingest.{path.stem}")
        for path in sorted(TESTS.glob("test_pid_recipe_r*.py"))
    }


def test_the_order_names_every_source_file_once_and_every_recipe() -> None:
    shaped = {
        sh.file for sh in [*pid_plan.LOAD_SHAPES, *pid_plan.ENTITY_SHAPES]
    } - {"graph port", "picture route"}
    assert len(FILES) == len(set(FILES)) == len(shaped) == 18
    assert set(FILES) == shaped, "a file the plan loads is missing, or one it does not is named"
    assert {"pid_seized_comms_batch1.csv", "pid_seized_comms_batch2.csv"} <= set(FILES)
    on_disk = {p.name for p in FIXTURES.glob("pid_*_recipe.yaml")}
    assert len(on_disk) == 17
    assert {s.recipe for s in ORDER} == on_disk, "a recipe is not in the order, or is not there"
    for step in ORDER:
        assert RECIPE_OF[step.file] == step.recipe, step.file


def test_the_order_is_the_amendments() -> None:
    assert [s.recipe for s in ORDER] == AMENDMENT
    assert [s.file for s in ORDER][-1] == "pid_seized_comms_batch2.csv"
    assert [s.file for s in ORDER][15:17] == ["pid_intel_reports.csv", "pid_report_incidents.csv"]


def test_each_stage_is_at_the_moment_the_plan_loads_its_file() -> None:
    for step in ORDER:
        moments = {
            sh.moment
            for sh in [*pid_plan.LOAD_SHAPES, *pid_plan.ENTITY_SHAPES]
            if sh.file == step.file
        }
        assert moments == {step.moment}, (step.file, moments)
    assert [s.moment for s in ORDER] == ["seed"] * 15 + ["chapter4"] * 2 + ["chapter9"]
    seed_part = pid_files.seed_stages("seed")
    assert [s.file for s in seed_part] == FILES[:15]
    assert [s.file for s in pid_files.seed_stages("chapter4", "chapter9")] == FILES[15:]


def test_every_recipe_tests_load_steps_are_a_subsequence_of_the_seed_order() -> None:
    modules = _recipe_test_modules()
    assert len(modules) >= 17, sorted(modules)  # R1 to R17, none skipped by the glob
    for name, module in modules.items():
        steps = _steps_of(module)
        assert steps, name
        assert is_subsequence(steps, FILES), (name, steps)


def test_the_subsequence_check_fails_for_a_step_out_of_order() -> None:
    # The shape a recipe test's steps take: R9's own, then the same with R3 moved after R16, then a
    # step the order does not hold, then a step named twice.
    r9 = ["pid_establishment_plan.csv", "pid_nomis_prisoners.csv", "pid_nomis_visits.csv",
          "pid_number_owners.csv", "pid_intel_reports.csv"]  # fmt: skip
    assert is_subsequence(r9, FILES)
    swapped = [r9[0], r9[1], r9[3], r9[2], r9[4]]
    assert not is_subsequence(swapped, FILES)
    assert not is_subsequence([*r9, "pid_nowhere.csv"], FILES)
    assert not is_subsequence([r9[0], r9[0]], FILES)
    # R17 before R9 is out of order.
    assert not is_subsequence([FILES[16], FILES[15]], FILES)
    assert is_subsequence(["pid_intel_reports.csv", "pid_report_incidents.csv"], FILES)


# --- No omitted earlier file writes an element the tested file also writes ----------------------


def _written(row: pid_plan.PlanRow) -> tuple[set[str], set[str]]:
    """The nodes (plan entity keys) and links (plan link keys) a row's recipe writes: its own
    entities and the ends of its links, which the recipe makes when none holds them yet, exactly as
    `pid_golden_support.replay` takes them."""
    nodes = set(row.entities)
    for link_key in row.links:
        link = _LINKS[link_key]
        nodes |= {link.source, link.target}
    return nodes, set(row.links)


_LINKS = {lk.key: lk for lk in PLAN.links}


def omission_problems(steps: Sequence[Step], tested: Sequence[str]) -> list[str]:
    """Where the steps leave out an earlier file (or an earlier row of a partial one) of the seed
    that writes an element a tested file also writes. A node is a problem when the first row of the
    seed's order to write it is not loaded (it would take the marking of whichever row does); a
    link, when any row of the seed's order that writes it is not loaded (the store merges
    every write of a pair by audience). Taken over the seed's order up to the last tested file."""
    loaded_rows = {s.file: s for s in steps}
    prefix = FILES[: max(FILES.index(f) for f in tested) + 1]
    first_node: dict[str, tuple[str, bool]] = {}
    link_writers: dict[str, list[tuple[str, bool]]] = {}
    touched_nodes: set[str] = set()
    touched_links: set[str] = set()
    for file in prefix:
        step = loaded_rows.get(file)
        for row in pid_files.ordered_rows(PLAN, file):
            took = step is not None and (step.plan_rows is None or step.plan_rows(row))
            nodes, links = _written(row)
            for key in nodes:
                first_node.setdefault(key, (file, took))
            for key in links:
                link_writers.setdefault(key, []).append((file, took))
            if file in tested:
                touched_nodes |= nodes
                touched_links |= links
    problems = []
    for key in sorted(touched_nodes):
        file, took = first_node[key]
        if not took:
            problems.append(f"node {key} is first written by {file}, which the test does not load")
    for key in sorted(touched_links):
        for file, took in link_writers[key]:
            if not took:
                problems.append(f"link {key} is also written by {file}, which the test omits")
                break
    return problems


def test_no_recipe_test_omits_an_earlier_file_that_writes_an_element_its_file_also_writes() -> None:
    modules = _recipe_test_modules()
    failing = {}
    for name, module in modules.items():
        problems = omission_problems(_stages_of(module), _tested_of(module))
        if problems:
            failing[name] = (len(problems), problems[:3])
    assert failing == {}, failing


def test_the_omission_check_fails_for_a_file_that_marks_an_element_first() -> None:
    r9 = _stages_of(_recipe_test_modules()["test_pid_recipe_r9"])
    assert omission_problems(r9, ["pid_intel_reports.csv"]) == []
    # R9 without R16: the number the report gives is first written by R16 (the owner file), so R9's
    # test would see it made by R9, at R9's marking.
    without = [s for s in r9 if s.file != "pid_number_owners.csv"]
    problems = omission_problems(without, ["pid_intel_reports.csv"])
    assert problems and all("pid_number_owners.csv" in p for p in problems), problems
    # R9 without R11: every area is first written by the estate.
    without = [s for s in r9 if s.file != "pid_establishment_plan.csv"]
    assert any("pid_establishment_plan.csv" in p for p in omission_problems(
        without, ["pid_intel_reports.csv"]))  # fmt: skip
    # A partial step that drops the rows of a link: R5 loaded without the calls to R6's numbers.
    r6 = _recipe_test_modules()["test_pid_recipe_r6"]
    stages = _stages_of(r6)
    calls = next(s for s in stages if s.file == "pid_pin_calls.csv")
    assert calls.plan_rows is not None, "R6's test loads a slice of the call file"
    dropped = [Step(s.file, s.rows, lambda row: False) if s is calls else s for s in stages]
    assert omission_problems(dropped, _tested_of(r6)) != []
