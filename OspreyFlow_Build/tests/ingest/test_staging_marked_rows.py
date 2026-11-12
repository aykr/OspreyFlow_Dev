"""The typed steps over a column a marking is bound to (CARRIES row 48; rule 3; ADR-140 Amendment
14 decision 11, the SQL step's rule, carried to the typed steps; the strict option, logged in
REPORT.md):

- **at the gate**, a step that computes a new value from a marking column is refused: a Derive
  reading one, a Lookup or a Join keyed on one, and a Join or Lookup that adds a column named as
  one. A value computed from a marking, bound by Map as another element's marking, could lower it;
- **at the run**, a Join or a fuzzy match whose output row would carry a row's values under another
  row's marking cells, where the two rows' marking cells differ, is refused in words, never cut;
- a Dedupe never folds rows whose marking cells differ: each stays, under its own marking.

Each guard is taken out at its own call site in `L1.7_RED_RECORD.md` (rule 15). The planted rows
take the shape a real source's rows do: a `classification` column the source declares a handling
column, read into `marked` by `recipe_rules.marked_columns`.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from services.ingest.fuzzy_match import run_fuzzy_step
from services.ingest.staging_catalogue import (
    StagingError,
    run_staging,
    source_table,
    staging_rule_violations,
)

from schemas.staging import FuzzyMatchStep, StagingStep

STEPS: TypeAdapter[list[StagingStep]] = TypeAdapter(list[StagingStep])
MARKED = frozenset({"classification"})


def _gate(steps: list[dict[str, object]], *, marked: frozenset[str] = MARKED) -> list[str]:
    return staging_rule_violations(
        STEPS.validate_python(steps), sources=["visits", "people"], lists=[], dataset_id="pid",
        marked=marked, subscribed=(),
    )  # fmt: skip


def _derive(columns: list[str]) -> dict[str, object]:
    return {
        "id": "d", "kind": "derive", "input": "visits", "column": "label",
        "operation": "concat", "columns": columns, "settings": {"separator": " "},
    }  # fmt: skip


def _join(**changes: object) -> dict[str, object]:
    step: dict[str, object] = {
        "id": "j", "kind": "join", "left": "visits", "right": "people",
        "left_key": "pin", "right_key": "pin", "add": [{"column": "name"}],
    }  # fmt: skip
    step.update(changes)
    return step


def test_a_derive_reading_a_marking_column_is_refused() -> None:
    problems = _gate([_derive(["name", "classification"])])
    assert any(
        "derives from 'classification', a column a marking is bound to" in p for p in problems
    )
    assert _gate([_derive(["name", "note"])]) == []
    assert _gate([_derive(["name", "classification"])], marked=frozenset()) == []


@pytest.mark.parametrize(
    ("changes", "words"),
    [
        (
            {"left_key": "classification"},
            "joins on 'classification', a column a marking is bound to",
        ),
        (
            {"right_key": "classification"},
            "joins on 'classification', a column a marking is bound to",
        ),
        ({"add": [{"column": "grade", "as": "classification"}]}, "adds 'classification'"),
        ({"add": [{"column": "classification"}]}, "adds 'classification'"),
    ],
)
def test_a_join_keyed_on_or_adding_a_marking_column_is_refused(
    changes: dict[str, object], words: str
) -> None:
    assert any(words in p for p in _gate([_join(**changes)]))


def test_a_lookup_keyed_on_a_marking_column_is_refused() -> None:
    lookup = {"id": "l", "kind": "lookup", "input": "visits", "list": "wings",
              "on": "classification",
              "add": [{"column": "name"}]}  # fmt: skip
    assert any(
        "looks up on 'classification', a column a marking is bound to" in p for p in _gate([lookup])
    )


def _tables(right_class: str | None) -> dict[str, object]:
    visits = source_table(
        "visits", [{"pin": "A1", "classification": "OFFICIAL", "note": "x"}], load_id="l1"
    )
    person: dict[str, object] = {"pin": "A1", "name": "Ann Example"}
    if right_class is not None:
        person["classification"] = right_class
    people = source_table("people", [person], load_id="l2")
    return {"visits": visits, "people": people}


def _run_join(right_class: str | None, marked: frozenset[str] = MARKED) -> object:
    return run_staging(
        STEPS.validate_python([_join()]), sources=_tables(right_class), lists={}, dataset_id="pid",  # type: ignore[arg-type]
        marked=marked, subscribed=(),
    )  # fmt: skip


def test_a_join_of_rows_marked_alike_runs() -> None:
    result = _run_join("OFFICIAL")
    assert result.output.rows[0].cells["name"] == "Ann Example"  # type: ignore[attr-defined]


@pytest.mark.parametrize("right_class", ["SECRET", None], ids=["marked-higher", "not-marked"])
def test_a_join_of_rows_marked_differently_is_refused_whole(right_class: str | None) -> None:
    with pytest.raises(StagingError) as refused:
        _run_join(right_class)
    words = str(refused.value)
    assert "joins a row to one whose marking differs" in words
    assert "Ann Example" not in words and "SECRET" not in words


def test_a_pipeline_with_no_marking_column_joins_as_before() -> None:
    result = _run_join("SECRET", marked=frozenset())
    assert result.output.rows[0].cells["name"] == "Ann Example"  # type: ignore[attr-defined]


def test_a_dedupe_never_folds_rows_marked_differently() -> None:
    rows = [
        {"pin": "A1", "classification": "OFFICIAL", "note": "seen"},
        {"pin": "A1", "classification": "SECRET", "note": "seen"},
        {"pin": "A1", "classification": "OFFICIAL", "note": "seen"},
    ]
    sources = {"visits": source_table("visits", rows, load_id="l1")}
    step = STEPS.validate_python([{"id": "dd", "kind": "dedupe", "input": "visits", "on": ["pin"]}])
    result = run_staging(
        step, sources=sources, lists={}, dataset_id="pid", marked=MARKED, subscribed=()
    )
    assert [r.cells["classification"] for r in result.output.rows] == ["OFFICIAL", "SECRET"]
    assert [len(r.refs) for r in result.output.rows] == [2, 1]
    folded = run_staging(
        step, sources=sources, lists={}, dataset_id="pid", marked=frozenset(), subscribed=()
    )
    assert len(folded.output.rows) == 1


def test_a_fuzzy_match_onto_a_row_marked_differently_is_refused() -> None:
    step = FuzzyMatchStep.model_validate(
        {"id": "f", "kind": "fuzzy_match", "left": "visits", "right": "people",
         "compare": [{"left": "pin", "right": "pin", "method": "exact"}], "threshold": 0.5,
         "add": [{"column": "name"}], "same_as": {"left": "visitor", "right": "person"}}
    )  # fmt: skip
    tables = _tables("SECRET")
    with pytest.raises(StagingError, match="whose marking differs"):
        run_fuzzy_step(step, tables["visits"], tables["people"], marked=MARKED)  # type: ignore[arg-type]
    alike = _tables("OFFICIAL")
    table, _ = run_fuzzy_step(step, alike["visits"], alike["people"], marked=MARKED)  # type: ignore[arg-type]
    assert table.rows[0].cells["name"] == "Ann Example"


def test_a_derive_making_a_marking_column_is_refused() -> None:
    """The lane review of L1.7, item 16: a marking Map binds after staging, made by a Derive from
    unmarked values, would be a marking no source declared."""
    step = {**_derive(["name", "note"]), "column": "classification"}
    assert any("makes 'classification', a column a marking is bound to" in p for p in _gate([step]))


def test_a_fuzzy_match_comparing_a_marking_column_is_refused() -> None:
    fuzzy = {"id": "f", "kind": "fuzzy_match", "left": "visits", "right": "people",
             "compare": [{"left": "classification", "right": "name", "method": "exact"}],
             "threshold": 0.5, "add": [{"column": "name"}],
             "same_as": {"left": "visitor", "right": "person"}}  # fmt: skip
    assert any(
        "compares 'classification', a column a marking is bound to" in p for p in _gate([fuzzy])
    )


# --- ADR-140 Amendment 19 (CARRIES row 123): a source's declared default marking ---------------
#
# The guard stays fail closed: a table with no marking column of its own is unmarked, and its rows
# never join a marked table's. A source may declare a default marking (Studio › Sources, by a
# source approver, audited); an unmarked table's rows then carry it, in the column Map binds the
# classification from, before any step runs. It never touches a table that has a marking column,
# so it never lowers a bound marking.

CLASSIFICATION = frozenset({"classification"})


def _carried(right_class: str | None, declared: str | None) -> dict[str, object]:
    from services.ingest.staging_catalogue import carry_declared_marking

    tables = _tables(right_class)
    tables["people"] = carry_declared_marking(
        tables["people"], declared, marked=MARKED, classification=CLASSIFICATION  # type: ignore[arg-type]
    )
    return tables


def _run(tables: dict[str, object]) -> object:
    return run_staging(
        STEPS.validate_python([_join()]), sources=tables, lists={}, dataset_id="pid",  # type: ignore[arg-type]
        marked=MARKED, subscribed=(),
    )  # fmt: skip


def test_an_unmarked_table_carrying_its_sources_default_joins_rows_marked_alike() -> None:
    result = _run(_carried(None, "OFFICIAL"))
    (row,) = result.output.rows  # type: ignore[attr-defined]
    assert row.cells["name"] == "Ann Example" and row.cells["classification"] == "OFFICIAL"


def test_an_unmarked_tables_rows_carry_the_default_in_the_classification_column() -> None:
    people = _carried(None, "OFFICIAL")["people"]
    assert "classification" in people.columns  # type: ignore[attr-defined]
    assert [r.cells["classification"] for r in people.rows] == ["OFFICIAL"]  # type: ignore[attr-defined]


def test_a_default_marked_differently_from_the_other_table_is_still_refused() -> None:
    tables = _carried(None, "SECRET")
    # The default was carried (the row is marked SECRET now), so the refusal is a difference of
    # markings, never the unmarked words: an uncarried table would fail both assertions.
    assert [r.cells["classification"] for r in tables["people"].rows] == ["SECRET"]  # type: ignore[attr-defined]
    with pytest.raises(StagingError) as refused:
        _run(tables)
    assert "whose marking differs" in str(refused.value)
    assert "default marking" not in str(refused.value)


def test_the_default_never_touches_a_table_that_has_a_marking_column() -> None:
    """Never lowers a bound marking: a SECRET row stays SECRET, so the join is still refused."""
    tables = _carried("SECRET", "OFFICIAL")
    assert [r.cells["classification"] for r in tables["people"].rows] == ["SECRET"]  # type: ignore[attr-defined]
    with pytest.raises(StagingError, match="whose marking differs"):
        _run(tables)


def test_a_bound_column_with_an_empty_cell_is_not_filled_by_the_default() -> None:
    """The table has the marking column, so it is marked: an empty cell is not an unmarked table
    (the strict option); the join is refused as before."""
    tables = _carried("", "OFFICIAL")
    people = tables["people"]
    assert "classification" in people.columns  # type: ignore[attr-defined]
    assert [r.cells["classification"] for r in people.rows] == [None]  # type: ignore[attr-defined]
    with pytest.raises(StagingError) as refused:
        _run(tables)
    # The table is marked, so the words never point at a default that could not help it (the lane
    # review, item 4).
    assert "whose marking differs" in str(refused.value)
    assert "default marking" not in str(refused.value)


def test_no_default_declared_keeps_the_guard_fail_closed_and_names_the_setting() -> None:
    with pytest.raises(StagingError) as refused:
        _run(_carried(None, None))
    words = str(refused.value)
    assert "whose marking differs" in words
    assert "unmarked" in words and "default marking" in words and "Studio › Sources" in words
    assert "Ann Example" not in words and "OFFICIAL" not in words


def test_a_refusal_of_two_marked_rows_does_not_point_at_the_default() -> None:
    """The setting is named only where it could help: a row with no marking at all."""
    with pytest.raises(StagingError) as refused:
        _run(_carried("SECRET", None))
    assert "default marking" not in str(refused.value)


def test_a_pipeline_with_no_marking_column_is_left_as_it_is() -> None:
    from services.ingest.staging_catalogue import carry_declared_marking

    people = _tables(None)["people"]
    kept = carry_declared_marking(
        people, "OFFICIAL", marked=frozenset(), classification=frozenset()  # type: ignore[arg-type]
    )
    assert kept is people
