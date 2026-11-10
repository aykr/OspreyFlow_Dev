"""ADR-148 decision 10, the deployment's marking ceiling (L1.10): `deployment.highest_marking`,
defaulting to the scheme's highest. A load marked above it is refused before anything is written,
in words that say the deployment's limit, never the item's content (rule 12: each entry point has
its test, each red first, `process/lanes/studio-b/l1.10/`)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from services.ingest import ceiling as ceiling_module
from services.ingest.ceiling import AboveTheDeploymentCeiling, CeilingUnknown, DeploymentCeiling

from demo_fixtures import pid_files
from ontology.handling import load_uk_le_scheme
from schemas.deployment import OspreyConfig
from tests.ingest.pid_golden_support import CASE, load, loaded, rows_of
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_row_keys import Sink

SCHEME = load_uk_le_scheme()
FILE = "pid_conflicts.csv"
#: A value of the planted row that the refusal must never say (rule 7: no content).
PLANTED = "SYN-CEILING-ROW"


#: Every file the seed loads before this one, in its order, so its references resolve.
ORDER = [stage.file for stage in pid_files.SEED_ORDER]
BEFORE = tuple(ORDER[: ORDER.index(FILE)])
LOAD = "load-ceiling"


def _rows(classification: str) -> list[dict[str, str]]:
    """The file as the seed has it, with its first row's classification planted and its free text
    set to a value the refusal must never say."""
    rows = [dict(r) for r in rows_of(FILE)]
    rows[0] = {**rows[0], "classification": classification, "reason": PLANTED}
    return rows


def _staged_for(root: Path, load_id: str) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and load_id in str(p)]


def _config(**deployment: object) -> OspreyConfig:
    return OspreyConfig.model_validate({"profile": "local-lite", "deployment": deployment})


# --- the setting ----------------------------------------------------------------------------


def test_the_ceiling_is_rendered_for_the_conduit() -> None:
    from harness.render import _render_env

    env = _render_env(_config(highest_marking="OFFICIAL-SENSITIVE"))
    assert "OSPREY_HIGHEST_MARKING=OFFICIAL-SENSITIVE" in env.splitlines()


def test_no_ceiling_set_renders_the_scheme_s_highest() -> None:
    from harness.render import _render_env

    env = _render_env(_config())
    assert f"OSPREY_HIGHEST_MARKING={SCHEME.classification[-1]}" in env.splitlines()


def test_a_ceiling_the_scheme_does_not_know_is_refused_at_render() -> None:
    from harness.render import _render_env

    with pytest.raises(ValueError) as raised:
        _render_env(_config(highest_marking="SEKRIT"))
    assert "deployment.highest_marking" in str(raised.value)
    assert "OFFICIAL-SENSITIVE" in str(raised.value)  # the known ones are named


def test_the_conduit_reads_the_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", "OFFICIAL-SENSITIVE")
    found = DeploymentCeiling.from_env()
    assert found.marking == "OFFICIAL-SENSITIVE"
    assert (
        found.above("SECRET")
        and not found.above("OFFICIAL-SENSITIVE")
        and not found.above("OFFICIAL")
    )


def test_nothing_set_is_the_scheme_s_highest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OSPREY_HIGHEST_MARKING", raising=False)
    found = DeploymentCeiling.from_env()
    assert found.marking == SCHEME.classification[-1]
    assert not any(found.above(c) for c in SCHEME.classification)


def test_an_unknown_ceiling_stops_the_conduit_rather_than_guessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", "SEKRIT")
    with pytest.raises(CeilingUnknown):
        DeploymentCeiling.from_env()


# --- the funnel: every load, through run_recipe ---------------------------------------------


async def test_a_load_with_a_row_above_the_ceiling_is_refused_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, store, _ = await loaded(*BEFORE)
    nodes, edges = len(graph.committed_nodes), len(graph.committed_edges)
    sink = Sink(store, CASE)
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", "OFFICIAL-SENSITIVE")

    with pytest.raises(AboveTheDeploymentCeiling) as raised:
        await load(graph, FILE, sink, LOAD, rows=_rows("SECRET"))

    words = str(raised.value)
    assert "OFFICIAL-SENSITIVE" in words and "highest marking" in words
    assert PLANTED not in words, "the refusal said the row's content"
    assert (len(graph.committed_nodes), len(graph.committed_edges)) == (nodes, edges)
    assert sink.records == []
    assert _staged_for(tmp_path / "staging", LOAD) == [], "staged before the refusal"


async def test_a_load_at_the_ceiling_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    graph, store, _ = await loaded(*BEFORE)
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", "OFFICIAL-SENSITIVE")
    report, _ = await load(graph, FILE, Sink(store, CASE), LOAD, rows=_rows("OFFICIAL-SENSITIVE"))
    assert report.rows_read == len(rows_of(FILE))
    assert any(h.classification == "OFFICIAL-SENSITIVE" for h in report.markings)


async def test_with_no_ceiling_set_a_secret_row_loads_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph, store, _ = await loaded(*BEFORE)
    monkeypatch.delenv("OSPREY_HIGHEST_MARKING", raising=False)
    report, _ = await load(graph, FILE, Sink(store, CASE), LOAD, rows=_rows("SECRET"))
    assert any(h.classification == "SECRET" for h in report.markings)


def test_a_recipe_whose_fixed_marking_is_above_the_ceiling_is_refused_before_any_staging() -> None:
    """A staged pipeline writes its step tables before `run_recipe`, so what can be judged without
    rows (a marking no column sets) is refused first (`pipeline_run`)."""
    from tests.ingest.test_load_record_created_and_merged import _recipe

    recipe = _recipe()
    secret = recipe.model_copy(
        update={
            "defaults": recipe.defaults.model_copy(
                update={"handling": {**recipe.defaults.handling, "classification": "SECRET"}}
            )
        }
    )
    ceiling = DeploymentCeiling(marking="OFFICIAL-SENSITIVE", scheme=SCHEME)
    with pytest.raises(AboveTheDeploymentCeiling):
        ceiling_module.refuse_fixed_markings_above_the_ceiling(secret, ceiling)
    ceiling_module.refuse_fixed_markings_above_the_ceiling(recipe, ceiling)  # OFFICIAL passes


async def test_the_conduits_start_stops_on_an_unknown_ceiling_before_opening_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The start itself, not only the reader: `lifespan` reads the ceiling before any store is
    opened, and an unknown one ends it there."""
    from services.api import app as app_module
    from services.api.app import app

    def opened(*_: object, **__: object) -> None:
        raise AssertionError("the start went on to open the stores")

    monkeypatch.setattr(app_module, "build_run_resources", opened)
    monkeypatch.setattr(app_module.ApiConfig, "from_env", classmethod(lambda cls: object()))
    monkeypatch.delenv("OSPREY_GRADING_SCHEME", raising=False)
    monkeypatch.setenv("OSPREY_HIGHEST_MARKING", "SEKRIT")
    with pytest.raises(CeilingUnknown):
        async with app_module.lifespan(app):
            pass


def test_a_staged_pipeline_judges_its_fixed_markings_before_its_step_tables() -> None:
    """Structural, since a staged branch needs its stores to run end to end: in
    `pipeline_run._run_staged_branch`, the ceiling's check of fixed markings comes before the
    source tables are read and the step tables written (`source_tables`, `prepare_staged_load`).
    Red with the check removed or moved after them."""
    import inspect

    from services.api import pipeline_run

    source = inspect.getsource(pipeline_run._run_staged_branch)
    check = source.find("refuse_fixed_markings_above_the_ceiling(")
    assert check != -1, "the staged branch does not judge its fixed markings"
    for write in ("source_tables,", "prepare_staged_load("):
        assert source.find(write) != -1, write
        assert check < source.find(write), f"the check comes after {write}"


# --- the lane review of L1.10 ----------------------------------------------------------------


def _two_unit_recipe() -> Any:
    """Two people, each restricted (code R) to a different unit, the first's classification read
    from a column: a row of it is a conflict between units, which `row_marking` refuses outright."""
    from tests.ingest.test_load_record_created_and_merged import _recipe

    recipe = _recipe()
    entities = [
        e.model_copy(update={"handling": handling})
        for e, handling in zip(
            recipe.row_template.entities,
            [
                {"classification": {"field": "cls"}, "handling_code": "R",
                 "originator": "unit-1", "owning_unit": "unit-1"},
                {"handling_code": "R", "originator": "unit-2", "owning_unit": "unit-2"},
            ],
            strict=True,
        )
    ]  # fmt: skip
    template = recipe.row_template.model_copy(update={"entities": entities})
    defaults = recipe.defaults.model_copy(update={"units": ["unit-1", "unit-2"]})
    return recipe.model_copy(update={"row_template": template, "defaults": defaults})


def test_a_row_whose_units_conflict_is_still_judged() -> None:
    """A unit conflict once skipped the row; it is staged all the same, so it is judged."""
    from tests.ingest.test_load_record_created_and_merged import _row

    ceiling = DeploymentCeiling(marking="OFFICIAL-SENSITIVE", scheme=SCHEME)
    recipe = _two_unit_recipe()
    with pytest.raises(AboveTheDeploymentCeiling):
        ceiling_module.refuse_rows_above_the_ceiling(
            recipe, [{**_row("SYN-1", "SYN-2", 1), "cls": "SECRET"}], ceiling
        )
    ceiling_module.refuse_rows_above_the_ceiling(
        recipe, [{**_row("SYN-1", "SYN-2", 1), "cls": "OFFICIAL"}], ceiling
    )


def test_a_row_whose_classification_reads_is_judged_by_it_alone() -> None:
    """A bad originator cell beside a readable OFFICIAL classification is the engine's to reject
    (it names the cause); the ceiling judges the classification, not the whole marking widened."""
    from tests.ingest.pid_golden_support import recipe_for

    ceiling = DeploymentCeiling(marking="OFFICIAL-SENSITIVE", scheme=SCHEME)
    row = {**_rows("OFFICIAL")[0], "originator": "no-such-unit"}
    ceiling_module.refuse_rows_above_the_ceiling(recipe_for(FILE), [row], ceiling)


def test_a_row_whose_classification_cannot_be_read_is_refused_in_words_that_say_so() -> None:
    """Fails closed, honestly: a classification the scheme does not define could be anything, and
    the engine holds such a row's sample at the scheme's highest; the words say it cannot be read,
    not that it is above."""
    from tests.ingest.pid_golden_support import recipe_for

    ceiling = DeploymentCeiling(marking="OFFICIAL-SENSITIVE", scheme=SCHEME)
    with pytest.raises(AboveTheDeploymentCeiling) as raised:
        ceiling_module.refuse_rows_above_the_ceiling(
            recipe_for(FILE), [_rows("SEKRIT")[0]], ceiling
        )
    words = str(raised.value)
    assert "cannot be read" in words and "OFFICIAL-SENSITIVE" in words
    assert PLANTED not in words and "SEKRIT" not in words


def test_an_element_whose_own_fixed_marking_is_above_the_ceiling_is_refused() -> None:
    from tests.ingest.test_load_record_created_and_merged import _recipe

    recipe = _recipe()
    first, *rest = recipe.row_template.entities
    secret = first.model_copy(update={"handling": {"classification": "SECRET"}})
    template = recipe.row_template.model_copy(update={"entities": [secret, *rest]})
    ceiling = DeploymentCeiling(marking="OFFICIAL-SENSITIVE", scheme=SCHEME)
    with pytest.raises(AboveTheDeploymentCeiling):
        ceiling_module.refuse_fixed_markings_above_the_ceiling(
            recipe.model_copy(update={"row_template": template}), ceiling
        )
