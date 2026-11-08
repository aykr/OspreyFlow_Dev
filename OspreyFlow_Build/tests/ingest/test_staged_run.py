"""The redesign's phase 7 exit, offline: the prototype's "Visits and contacts" pipeline without its
two expert steps builds and runs on synthetic data (`fixtures/visits_and_contacts/`, rule 9), and
every element it creates is traceable to its source rows (ADR-140 decision 11; the orchestrator's
settlement of 8 November 2026, Q2 (a): one `SourceRef` per input row in `provenance.sources`).

The graph is the shared stand-in that refuses what ArcadeDB refuses (`recipe_test_support.py`);
the staged Parquet is written to a temporary directory and read back. The same run against the real
adapter, reading provenance back from the store, is `test_staged_provenance_live.py`.

What a mistake would do, and the case that catches it:

- a Join that drops one side's refs, so a link made from a joined row names only the booking and
  not the number-owner row that said who uses the number
  (`test_a_join_s_provenance_survives_to_the_link_it_makes`; shown red with `source_refs` dropped
  at the join);
- an element made from a staged row that names no source row, or a source that is not one of the
  pipeline's (`test_every_element_names_the_source_rows_it_came_from`);
- Test and the load disagreeing about which rows are rejected, or why
  (`test_test_and_the_load_reject_the_same_rows`);
- a row lost between the source and Map without a word (`test_every_booking_is_accounted_for`).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from services.ingest.recipe_loader import load_recipe
from services.ingest.staged_run import dry_run_staged_recipe, run_staged_recipe
from services.ingest.staging import ObjectStorageConfig
from services.ingest.staging_catalogue import StagedTable, reference_table, source_table

from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.dataset_model import ReferenceList
from schemas.domain import Principal
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    ValidatingGraph,
    local_staging,
)

FIXTURES = Path(__file__).parent / "fixtures" / "visits_and_contacts"
ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="loader-1", clearance="SECRET", org_unit="unit-1")
ESTABLISHMENTS = ReferenceList(
    id="rl-est",
    dataset_id="pid",
    name="establishments",
    kind="reference",
    key_column="estab_id",
    version=3,
)
SOURCES = {"visit_bookings", "number_owners", "reference_list:establishments@v3"}


def _rows(name: str) -> list[dict[str, str]]:
    with (FIXTURES / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def inputs() -> tuple[dict[str, StagedTable], dict[str, StagedTable]]:
    sources = {
        "visit_bookings": source_table(
            "visit_bookings", _rows("visit_bookings.csv"), load_id="ld-vb-1", key=["booking_id"]
        ),
        "number_owners": source_table(
            "number_owners", _rows("number_owners.csv"), load_id="ld-no-1", key=["number"]
        ),
    }
    lists = {"establishments": reference_table(ESTABLISHMENTS, _rows("establishments.csv"))}
    return sources, lists


RECIPE = load_recipe(FIXTURES / "visits_and_contacts_recipe.yaml")


async def load() -> tuple[Any, ValidatingGraph]:
    sources, lists = inputs()
    graph = ValidatingGraph(ONTOLOGY)
    tx = await graph.begin_transaction()
    done = await run_staged_recipe(
        RECIPE,
        sources=sources,
        lists=lists,
        dataset_id="pid",
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        tx=tx,  # type: ignore[arg-type]
        principal=LOADER,
        load_id="ld-run-1",
        investigation_scope="case-1",
        storage=ObjectStorageConfig(bucket="staging"),
        scheme=SCHEME,
    )
    await graph.commit_transaction(tx)
    return done, graph


def _refs(element: Any) -> list[tuple[str, str, str | None, str | None]]:
    return [(s.document_id, s.locator, s.row_key, s.load_id) for s in element.provenance.sources]


def _node(graph: ValidatingGraph, type_: str, field: str, value: str) -> Any:
    found = [
        n for n in graph.committed_nodes if n.type == type_ and n.properties.get(field) == value
    ]
    assert len(found) == 1, (type_, value, found)
    return found[0]


async def test_a_join_s_provenance_survives_to_the_link_it_makes() -> None:
    _done, graph = await load()
    whitlow = _node(graph, "Person", "family_name", "WHITLOW")
    number = _node(graph, "Endpoint", "value_normalised", "+447700900718")
    uses = [e for e in graph.committed_edges if e.type == "USES"]
    assert [(e.source, e.target) for e in uses if e.source == whitlow.id] == [
        (whitlow.id, number.id)
    ]
    link = next(e for e in uses if e.source == whitlow.id)
    sources = {(d, loc, load) for d, loc, _key, load in _refs(link)}
    # The booking that gave the number, the owner row that said whose it is, the list row that
    # named the establishment: each with its own load.
    assert ("visit_bookings", "row 0", "ld-vb-1") in sources
    assert ("number_owners", "row 0", "ld-no-1") in sources
    assert ("reference_list:establishments@v3", "row 0", None) in sources
    # And to the node: the owner was made from the joined row, so it names the owner row too.
    assert ("number_owners", "row 0", "ld-no-1") in {
        (d, loc, ld) for d, loc, _k, ld in _refs(whitlow)
    }


async def test_every_element_names_the_source_rows_it_came_from() -> None:
    _done, graph = await load()
    elements = [*graph.committed_nodes, *graph.committed_edges]
    assert elements
    for element in elements:
        refs = _refs(element)
        assert refs, element
        for document, locator, key, load_id in refs:
            assert document in SOURCES, document
            assert locator.startswith("row ") and key
            assert (load_id is None) == document.startswith("reference_list:")
    booking = _node(graph, "Document", "message_id", "VB-2605-002")
    assert booking.properties["title"] == "HMP Halbeck · Wed 5 Nov 10:00"
    assert {d for d, *_ in _refs(booking)} == SOURCES


async def test_every_booking_is_accounted_for() -> None:
    done, _graph = await load()
    reports = {r.step: r for r in done.staging.reports}
    assert reports["with_establishment"].rows_in == 6
    assert reports["with_establishment"].unmatched == 1  # XXX, kept with no establishment
    assert reports["with_owner"].unmatched == 2  # 003's and 006's numbers have no owner
    assert reports["with_owner"].rejected == 1  # 004: "not given" is no number
    staging_rejections = [r for r in done.report.rejections if r.reason.startswith("staging step")]
    assert [(r.row_index, r.reason) for r in staging_rejections] == [
        (3, "staging step with_owner: contact_number: a phone number has no letters in it")
    ]
    assert all("not given" not in r.reason for r in done.report.rejections)
    # Five bookings reach Map; one of them (006, booked "yesterday") Map itself rejects.
    assert done.report.rows_read == 5
    assert len(done.report.rejections) == 2
    assert set(done.staged_paths) == {"with_establishment", "with_owner", "titled"}


async def test_test_and_the_load_reject_the_same_rows() -> None:
    done, _graph = await load()
    sources, lists = inputs()
    tested = await dry_run_staged_recipe(
        RECIPE,
        sources=sources,
        lists=lists,
        dataset_id="pid",
        graph=ValidatingGraph(ONTOLOGY),  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        principal=LOADER,
        scheme=SCHEME,
    )

    def rejected(records: Any) -> list[tuple[int, str]]:
        return [(r.row_index, r.reason) for r in records]

    assert rejected(tested.result.rejections) == rejected(done.report.rejections)
    assert len(tested.result.rejections) == 2
    # And Test shows the provenance the load writes.
    tested_owner = next(
        n
        for n in tested.result.nodes
        if n.type == "Person" and n.properties["family_name"] == "WHITLOW"
    )
    assert ("number_owners", "row 0", "ld-no-1") in {
        (s.document_id, s.locator, s.load_id) for s in tested_owner.provenance.sources
    }
