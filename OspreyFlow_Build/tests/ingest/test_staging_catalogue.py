"""The staging catalogue's gate, its reference lists and its Parquet (ADR-140 decision 11;
Amendment 9 decision 3, screening lists as reference lists; rule 8;
`services/ingest/staging_catalogue.py`).

What a mistake would do, and the case that catches it:

- a step reading a table nothing gives, or one that comes after it, or a step feeding nothing
  (`test_the_gate_refuses_an_unfed_or_dangling_step`): the phase's "a step must be fed";
- a Lookup reading another dataset's list, or a screening list the dataset has not subscribed to,
  or saying in its refusal that another dataset's list exists
  (`test_a_lookup_reads_only_its_dataset_s_lists_and_subscribed_screening_lists`);
- a key "normalised" by something that is not a one-column Knowledge Adapter
  (`test_a_key_is_normalised_only_by_a_one_column_adapter`);
- a guided-mode transform that is not a Knowledge Adapter with its golden file
  (`test_every_adapter_a_step_may_name_has_its_golden_tests`): rule 8;
- a screening list that comes back from the catalogue as something else, or loses an alias or a
  date of birth (`test_a_screening_list_round_trips_through_the_catalogue`), or cannot be looked
  up once it is back (`test_a_subscribed_screening_list_serves_a_lookup_after_its_round_trip`);
- a staged table whose empty cells or refs do not survive Parquet
  (`test_a_step_s_table_round_trips_its_parquet`);
- a column added over one that is there (`test_a_step_never_writes_over_a_column`).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import TypeAdapter
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import (
    StagingError,
    read_staged_table,
    reference_table,
    run_staging,
    screening_parties,
    screening_table,
    source_table,
    stage_table,
    staging_rule_violations,
)

from knowledge_adapters import ARITY, REGISTRY
from knowledge_adapters.screening_lists import ofac_sdn
from schemas.dataset_model import ReferenceList
from schemas.staging import StagingStep
from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)

STEPS = TypeAdapter(list[StagingStep])
TESTS = Path(__file__).resolve().parents[1]
STORE = ObjectStorageConfig(bucket="staging")

OWN = ReferenceList(
    id="rl-1",
    dataset_id="pid",
    name="establishments",
    kind="reference",
    key_column="estab_id",
    version=3,
)
OTHERS = ReferenceList(
    id="rl-2", dataset_id="ledger", name="branches", kind="reference", key_column="code", version=1
)
OFAC = ReferenceList(
    id="rl-3",
    dataset_id="deployment",
    name="ofac_sdn",
    kind="screening",
    key_column="ref",
    version=1,
)


def _lookup(list_name: str, **extra: object) -> dict[str, object]:
    return {
        "id": "looked_up",
        "kind": "lookup",
        "input": "bookings",
        "list": list_name,
        "on": "estab_id",
        "add": [{"column": "name"}],
        **extra,
    }


def _violations(steps: list[dict[str, object]], subscribed: tuple[str, ...] = ()) -> list[str]:
    return staging_rule_violations(
        STEPS.validate_python(steps),
        sources=["bookings", "owners"],
        lists=[OWN, OTHERS, OFAC],
        dataset_id="pid",
        subscribed=subscribed,
    )


def test_the_gate_accepts_a_fed_chain() -> None:
    steps = [
        _lookup("establishments"),
        {
            "id": "kept",
            "kind": "filter",
            "input": "looked_up",
            "keep": [{"field": "name", "is": "not_null"}],
        },
    ]
    assert _violations(steps) == []


def test_the_gate_refuses_an_unfed_or_dangling_step() -> None:
    filter_ = {"kind": "filter", "keep": [{"field": "a", "is": "null"}]}
    later = _violations(
        [{**filter_, "id": "a", "input": "b"}, {**filter_, "id": "b", "input": "bookings"}]
    )
    assert any("reads 'b', which is a later step" in p for p in later), later
    unknown = _violations([{**filter_, "id": "a", "input": "calls"}])
    assert unknown == [
        "step 'a' reads 'calls', which is neither a source table of this pipeline nor an "
        "earlier step"
    ]
    dangling = _violations(
        [{**filter_, "id": "a", "input": "bookings"}, {**filter_, "id": "b", "input": "bookings"}]
    )
    assert dangling == [
        "step 'a' feeds nothing: every step but the last must feed a later one (the last is what "
        "Map reads)"
    ]
    clash = _violations([{**filter_, "id": "bookings", "input": "bookings"}])
    assert any("has the name of a source table" in p for p in clash), clash
    with pytest.raises(StagingError, match="feeds nothing"):
        run_staging(
            STEPS.validate_python(
                [
                    {**filter_, "id": "a", "input": "bookings"},
                    {**filter_, "id": "b", "input": "bookings"},
                ]
            ),
            sources={"bookings": source_table("bookings", [{"a": "1"}], load_id="l")},
            lists={},
            dataset_id="pid",
        )


def test_a_lookup_reads_only_its_dataset_s_lists_and_subscribed_screening_lists() -> None:
    assert _violations([_lookup("establishments")]) == []
    other_dataset = _violations([_lookup("branches")])
    no_such_list = _violations([_lookup("nothing_by_this_name")])
    # The same words whether the list belongs to another dataset or does not exist (rule 3).
    assert [p.replace("branches", "X") for p in other_dataset] == [
        p.replace("nothing_by_this_name", "X") for p in no_such_list
    ]
    assert other_dataset == [
        "step 'looked_up' looks up 'branches', which names no list this dataset holds or "
        "subscribes to"
    ]
    assert _violations([_lookup("ofac_sdn", on="name")]) != []
    assert _violations([_lookup("ofac_sdn", on="name")], subscribed=("ofac_sdn",)) == []
    # A subscription names a screening list; it does not open another dataset's reference list.
    assert _violations([_lookup("branches")], subscribed=("branches",)) == other_dataset


@pytest.mark.parametrize("name", ["split", "grid_ref", "coordinate_lon", "eval", "msisdn "])
def test_a_key_is_normalised_only_by_a_one_column_adapter(name: str) -> None:
    problems = _violations([_lookup("establishments", normalise=name)])
    assert problems == [
        f"step 'looked_up' normalises its key with {name!r}, which is not a Knowledge Adapter that "
        "reads one column into one value"
    ]


def test_every_adapter_a_step_may_name_has_its_golden_tests() -> None:
    """Rule 8: what a guided step may name to change a value is a Knowledge Adapter with golden
    tests in `tests/knowledge_adapters/`, found by the module the adapter is defined in."""
    tests = {
        p.read_text(encoding="utf-8") for p in (TESTS / "knowledge_adapters").glob("test_*.py")
    }
    allowed = [n for n in REGISTRY if not _violations([_lookup("establishments", normalise=n)])]
    assert "msisdn" in allowed and "split" not in allowed
    for name in allowed:
        module = inspect.getmodule(REGISTRY[name])
        assert module is not None and name not in ARITY
        assert any(f"from {module.__name__} import" in t for t in tests), name
    assert any("from knowledge_adapters.derive import" in t for t in tests)


def test_a_screening_list_round_trips_through_the_catalogue() -> None:
    golden = TESTS / "knowledge_adapters" / "golden" / "screening_lists"
    parsed = ofac_sdn(
        (golden / "ofac_sdn.SDN.CSV").read_text(encoding="utf-8"),
        alt_csv=(golden / "ofac_sdn.ALT.CSV").read_text(encoding="utf-8"),
        add_csv=(golden / "ofac_sdn.ADD.CSV").read_text(encoding="utf-8"),
    )
    assert any(p.aliases for p in parsed.entries) and any(p.date_of_birth for p in parsed.entries)
    table = screening_table(OFAC, parsed.entries)
    back = read_staged_table(stage_table(table, storage=STORE, load_id="ld-list-1"), storage=STORE)
    assert back.kind == "screening"
    assert back.reference == OFAC
    assert back.columns == table.columns
    assert screening_parties(back) == parsed.entries
    assert [r.refs for r in back.rows] == [r.refs for r in table.rows]


def test_a_subscribed_screening_list_serves_a_lookup_after_its_round_trip() -> None:
    golden = TESTS / "knowledge_adapters" / "golden" / "screening_lists"
    parsed = ofac_sdn((golden / "ofac_sdn.SDN.CSV").read_text(encoding="utf-8"))
    table = screening_table(OFAC, parsed.entries)
    back = read_staged_table(stage_table(table, storage=STORE, load_id="ld-list-2"), storage=STORE)
    first = parsed.entries[0]
    customers = source_table(
        "customers", [{"sdn_ref": first.ref}, {"sdn_ref": "0"}], load_id="ld-c"
    )
    step = {
        "id": "screened",
        "kind": "lookup",
        "input": "customers",
        "list": "ofac_sdn",
        "on": "sdn_ref",
        "add": [{"column": "primary_name", "as": "listed_name"}],
    }
    result = run_staging(
        STEPS.validate_python([step]),
        sources={"customers": customers},
        lists={"ofac_sdn": back},
        dataset_id="pid",
        subscribed=["ofac_sdn"],
    )
    assert [r.cells["listed_name"] for r in result.output.rows] == [first.name, None]
    assert result.output.rows[0].refs[1].source == "reference_list:ofac_sdn@v1"
    assert result.reports[0].unmatched == 1
    with pytest.raises(StagingError, match="names no list this dataset holds or subscribes to"):
        run_staging(
            STEPS.validate_python([step]),
            sources={"customers": customers},
            lists={"ofac_sdn": back},
            dataset_id="pid",
        )


def test_a_step_s_table_round_trips_its_parquet() -> None:
    bookings = source_table(
        "bookings", [{"a": "1", "b": ""}, {"a": "2", "b": "x"}], load_id="ld-1", key=["a"]
    )
    est = reference_table(OWN, [{"estab_id": "1", "name": "HMP Fenwick Moor"}])
    result = run_staging(
        STEPS.validate_python([{**_lookup("establishments"), "on": "a"}]),
        sources={"bookings": bookings},
        lists={"establishments": est},
        dataset_id="pid",
    )
    back = read_staged_table(
        stage_table(result.output, storage=STORE, load_id="ld-1"), storage=STORE
    )
    assert back.columns == result.output.columns == ["a", "b", "name"]
    assert back.rows == result.output.rows
    assert back.rows[0].cells["b"] is None and back.rows[1].cells["name"] is None
    assert back.kind == "step"


def test_a_step_never_writes_over_a_column() -> None:
    bookings = source_table("bookings", [{"estab_id": "1", "name": "mine"}], load_id="ld-1")
    est = reference_table(OWN, [{"estab_id": "1", "name": "HMP Fenwick Moor"}])
    with pytest.raises(StagingError, match="adds 'name', a column its table already has"):
        run_staging(
            STEPS.validate_python([_lookup("establishments")]),
            sources={"bookings": bookings},
            lists={"establishments": est},
            dataset_id="pid",
        )
    derive = {
        "id": "d",
        "kind": "derive",
        "input": "bookings",
        "column": "name",
        "operation": "concat",
        "columns": ["estab_id", "name"],
    }
    with pytest.raises(StagingError, match="makes 'name', a column its table already has"):
        run_staging(
            STEPS.validate_python([derive]),
            sources={"bookings": bookings},
            lists={},
            dataset_id="pid",
        )


def test_a_list_s_key_identifies_one_row() -> None:
    with pytest.raises(StagingError, match="holds one key on two rows"):
        reference_table(OWN, [{"estab_id": "FMR"}, {"estab_id": "FMR"}])
    with pytest.raises(StagingError, match="has no key"):
        reference_table(OWN, [{"estab_id": "FMR"}, {"estab_id": " "}])
