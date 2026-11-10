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
    DEPLOYMENT_WIDE,
    StagingError,
    read_staged_table,
    readable_lists,
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
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    LocalStore,
    local_staging,
)

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
#: Another dataset's own list, kind screening and named as the deployment's list is.
LEDGERS_OFAC = ReferenceList(
    id="rl-9",
    dataset_id="ledger",
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


def _violations(
    steps: list[dict[str, object]],
    subscribed: tuple[str, ...] = (),
    lists: tuple[ReferenceList, ...] = (OWN, OTHERS, OFAC),
) -> list[str]:
    return staging_rule_violations(
        STEPS.validate_python(steps),
        sources=["bookings", "owners"],
        lists=list(lists),
        dataset_id="pid",
        subscribed=subscribed, marked=()
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
            dataset_id="pid", marked=(), subscribed=()
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
    # A subscription is by the list's id, never its name (review round 1, blocker 1).
    assert _violations([_lookup("ofac_sdn", on="name")], subscribed=("ofac_sdn",)) != []
    assert _violations([_lookup("ofac_sdn", on="name")], subscribed=("rl-3",)) == []
    # A subscription opens only a deployment-wide screening list, never another dataset's list.
    assert _violations([_lookup("branches")], subscribed=("rl-2",)) == other_dataset


def test_another_dataset_s_screening_list_of_the_same_name_is_never_read() -> None:
    """Review round 1, blocker 1: a screening list another dataset owns, named as the deployment's
    is, is not readable by a subscription to that name or to its own id, and does not stand in for
    the deployment's list."""
    only_ledgers = (OWN, LEDGERS_OFAC)
    for subscribed in [("ofac_sdn",), ("rl-9",), ("rl-3",), ("rl-3", "rl-9")]:
        assert _violations(
            [_lookup("ofac_sdn", on="name")], subscribed=subscribed, lists=only_ledgers
        ) == [
            "step 'looked_up' looks up 'ofac_sdn', which names no list this dataset holds or "
            "subscribes to"
        ], subscribed
    # Beside the deployment's own, the subscribed deployment list is the one read.
    assert (
        _violations(
            [_lookup("ofac_sdn", on="name")],
            subscribed=("rl-3", "rl-9"),
            lists=(OFAC, LEDGERS_OFAC),
        )
        == []
    )
    golden = TESTS / "knowledge_adapters" / "golden" / "screening_lists"
    parsed = ofac_sdn((golden / "ofac_sdn.SDN.CSV").read_text(encoding="utf-8"))
    ledgers = screening_table(LEDGERS_OFAC, parsed.entries[:1])
    deployments = screening_table(OFAC, parsed.entries)
    customers = source_table("bookings", [{"name": parsed.entries[1].ref}], load_id="ld-c")
    step = STEPS.validate_python([_lookup("ofac_sdn", on="name", add=[{"column": "primary_name"}])])
    with pytest.raises(StagingError, match="names no list this dataset holds or subscribes to"):
        run_staging(
            step,
            sources={"bookings": customers},
            lists={"ofac_sdn": ledgers},
            dataset_id="pid",
            subscribed=["rl-9", "ofac_sdn"], marked=()
        )
    done = run_staging(
        step,
        sources={"bookings": customers},
        lists={"ofac_sdn": deployments},
        dataset_id="pid",
        subscribed=["rl-3"], marked=()
    )
    assert done.output.rows[0].cells["primary_name"] == parsed.entries[1].name


def test_a_list_given_under_another_name_is_refused() -> None:
    """Review round 1, blocker 1: `lists` is keyed by each list's own name; a key that is not the
    list's name never lets a Lookup read a list it did not name."""
    est = reference_table(OWN, [{"estab_id": "1", "name": "HMP Fenwick Moor"}])
    bookings = source_table("bookings", [{"estab_id": "1"}], load_id="ld-1")
    with pytest.raises(
        StagingError, match="the list given as 'branches' is not the list of that name"
    ):
        run_staging(
            STEPS.validate_python([_lookup("branches")]),
            sources={"bookings": bookings},
            lists={"branches": est},
            dataset_id="pid", marked=(), subscribed=()
        )
    with pytest.raises(StagingError, match="the source table given as 'owners'"):
        run_staging(
            STEPS.validate_python([_lookup("establishments")]),
            sources={"owners": bookings},
            lists={"establishments": est},
            dataset_id="pid", marked=(), subscribed=()
        )


@pytest.mark.parametrize(
    "name",
    ["split", "grid_ref", "coordinate_lon", "eval", "msisdn ", "datetime", "card", "person_name"],
)
def test_a_key_is_normalised_only_by_a_one_column_adapter(name: str) -> None:
    problems = _violations([_lookup("establishments", normalise=name)])
    assert problems == [
        f"step 'looked_up' normalises its key with {name!r}, which is not a Knowledge Adapter that "
        "reads one column into one value of text"
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
        subscribed=["rl-3"], marked=()
    )
    assert [r.cells["listed_name"] for r in result.output.rows] == [first.name, None]
    assert result.output.rows[0].refs[1].source == "reference_list:ofac_sdn@v1"
    assert result.reports[0].unmatched == 1
    with pytest.raises(StagingError, match="names no list this dataset holds or subscribes to"):
        run_staging(
            STEPS.validate_python([step]),
            sources={"customers": customers},
            lists={"ofac_sdn": back},
            dataset_id="pid", marked=(), subscribed=()
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
        dataset_id="pid", marked=(), subscribed=()
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
            dataset_id="pid", marked=(), subscribed=()
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
            dataset_id="pid", marked=(), subscribed=()
        )


def test_a_list_s_key_identifies_one_row() -> None:
    with pytest.raises(StagingError, match="holds one key on two rows"):
        reference_table(OWN, [{"estab_id": "FMR"}, {"estab_id": "FMR"}])
    with pytest.raises(StagingError, match="has no key"):
        reference_table(OWN, [{"estab_id": "FMR"}, {"estab_id": " "}])


def test_the_local_store_refuses_a_bucket_never_created(tmp_path: Path) -> None:
    """Rule 15, review round 1 item 9: the stand-in refuses what MinIO refuses, a write into a
    bucket nobody created; and `stage_table` creates its bucket before it writes."""
    store = LocalStore(tmp_path)
    with pytest.raises(FileNotFoundError, match="NoSuchBucket"):
        store.open_output_stream("never/loads/x.parquet")
    table = source_table("bookings", [{"a": "1"}], load_id="ld-1")
    path = stage_table(table, storage=ObjectStorageConfig(bucket="fresh"), load_id="ld-1")
    assert read_staged_table(path, storage=ObjectStorageConfig(bucket="fresh")).rows == table.rows


def test_a_filter_reads_its_declared_values_trimmed_as_it_reads_cells() -> None:
    """Review round 1: `equals: " FMR"` meets a cell "FMR", as `in` does."""
    bookings = source_table("bookings", [{"e": "FMR"}, {"e": " HBK"}, {"e": "XXX"}], load_id="l")
    for keep in ([{"field": "e", "equals": " FMR "}], [{"field": "e", "in": [" FMR", "HBK "]}]):
        step = {"id": "kept", "kind": "filter", "input": "bookings", "keep": keep}
        done = run_staging(
            STEPS.validate_python([step]),
            sources={"bookings": bookings},
            lists={},
            dataset_id="pid", marked=(), subscribed=()
        )
        assert len(done.output.rows) == (1 if "equals" in keep[0] else 2), keep


def test_a_list_s_name_never_writes_outside_its_load_s_staged_folder() -> None:
    """Review round 1: a list's name is free text; quoted in the path, "/" and ".." stay inside."""
    odd = ReferenceList(
        id="rl-x", dataset_id="pid", name="../../x/y", kind="reference", key_column="k", version=1
    )
    table = reference_table(odd, [{"k": "1"}])
    path = stage_table(table, storage=STORE, load_id="ld-1")
    assert path.startswith("staging/loads/ld-1/staged/") and "/" not in path.split("staged/")[1]
    assert read_staged_table(path, storage=STORE).reference == odd


def test_a_union_of_tables_whose_columns_differ_is_refused() -> None:
    """Brief §6: Union stacks two tables with the same columns; one with a column the other lacks
    is refused whole, never stacked with empty cells."""
    a = source_table("a", [{"number": "1", "owner": "x"}], load_id="la")
    b = source_table("b", [{"number": "2"}], load_id="lb")
    step = {"id": "both", "kind": "union", "inputs": ["a", "b"]}
    with pytest.raises(StagingError, match="stacks 'b' and 'a', whose columns differ"):
        run_staging(
            STEPS.validate_python([step]), sources={"a": a, "b": b}, lists={}, dataset_id="pid", marked=(),
            subscribed=()
        )


@pytest.mark.parametrize("adapter", ["split", "datetime", "card", "grid_ref", "eval"])
def test_a_derive_normalising_with_anything_but_a_text_adapter_is_refused_at_the_gate(
    adapter: str,
) -> None:
    """Review round 2: the gate checks a Derive's `normalise` as it checks a key's, so a step that
    would reject every row is refused at save, not found at run."""
    step = {
        "id": "n",
        "kind": "derive",
        "input": "bookings",
        "column": "c",
        "operation": "normalise",
        "columns": ["contact"],
        "settings": {"adapter": adapter},
    }
    assert _violations([step]) == [
        f"step 'n' normalises with {adapter!r}, which is not a Knowledge Adapter that reads one "
        "column into one value of text"
    ]
    assert _violations([{**step, "settings": {"adapter": "msisdn"}}]) == []


def test_a_list_is_deployment_wide_by_its_own_record_never_by_the_caller() -> None:
    """Review round 2: only a list whose own `dataset_id` is the deployment's can be subscribed to;
    another dataset's list stays unreadable whatever the subscription names."""
    assert DEPLOYMENT_WIDE == OFAC.dataset_id
    for subscribed in [("rl-9",), ("rl-9", "ofac_sdn", "ledger")]:
        readable, _ = readable_lists([LEDGERS_OFAC], dataset_id="pid", subscribed=subscribed)
        assert readable == {}
    # Nor does a dataset named as the deployment read the deployment's lists as its own.
    readable, _ = readable_lists([OFAC], dataset_id=DEPLOYMENT_WIDE, subscribed=())
    assert readable == {}


def test_a_bucket_created_by_one_client_is_kept_for_the_next(tmp_path: Path) -> None:
    """Rule 15, review round 2: a bucket is the store's, as in MinIO, not one client's."""
    LocalStore(tmp_path).create_dir("shared")
    with LocalStore(tmp_path).open_output_stream("shared/loads/x.parquet") as sink:
        sink.write(b"x")
