"""The grading change against the real graph store (ADR-143 decision 11, C13; L3.7; rule 15's
second worked example: the offline tests run over `BoardGraph`, a fake, so the rewrite is also
proved against ArcadeDB itself).

**Live, against a lane's leased stack** (`scripts/stack_lease.sh`): a throwaway ArcadeDB database
(`conformance_*`, dropped afterwards). Two people and a link between them are drawn through the board
service under case K's real scope, so what is changed is what a board writes; the change is run
through `BoardGradedItems` over the bare adapter, as `scripts/grading_change.py` runs it.

What a mistake would do, and the case that catches it:
- a dry run that writes, a rewrite that loses the item's marking, datasets, properties or the rest of
  its assertion, a link rewritten as a second link beside the first, or an original overwritten at a
  second change: `test_the_change_rewrites_each_grade_in_the_store_keeping_its_original_and_the_rest`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme, sources_in_full
from ontology.packs import load_deployment_ontology
from schemas.boards import DrawnItemInput, DrawnLinkInput
from schemas.domain import Grading, Principal
from services.api.board_store import BoardItem, InMemoryBoardItemStore
from services.api.boards import Boards
from services.api.case_views import InMemoryCaseViewStore
from services.api.dataset_scope import scope_to_case, stamping
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.grading import BoardGradedItems, change, operator_reader, parse_mapping

UNIT = "unit-1"
K = "case-k"
ALICE = Principal(id="alice", clearance="SECRET", org_unit=UNIT, roles=["analyst"])

pytestmark = pytest.mark.skipif(
    not os.environ.get("OSPREY_LANE") and not os.environ.get("CI"),
    reason="needs a leased lane stack's ArcadeDB (OSPREY_LANE and its pinned ARCADEDB_HTTP_PORT)",
)

FIVE_TO_THREE = """
from: 5x5x5
to: 3x5x2
source: {A: A, B: A, C: B, D: C, E: C}
intelligence: {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
handling: {"1": P, "2": P, "3": P, "4": C, "5": C}
"""

THREE_TO_FIVE = """
from: 3x5x2
to: 5x5x5
source: {A: A, B: C, C: E}
intelligence: {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
handling: {P: "1", C: "4"}
"""


@pytest.fixture
async def drawn() -> AsyncIterator[SimpleNamespace]:
    ontology, scheme = load_deployment_ontology(), load_uk_le_scheme()
    datasets = InMemoryDatasetStore()
    datasets.add(
        Dataset(id="src", name="Prison intel", owning_unit=UNIT, created_by="eng",
                created_at=datetime(2026, 11, 1, tzinfo=UTC))
    )  # fmt: skip
    datasets.cases[K] = ["src"]
    await datasets.ensure_layer(K, unit=UNIT, created_by="alice")
    async with arcadedb_adapter(ontology, scheme) as adapter:
        items = InMemoryBoardItemStore()
        boards = Boards(
            graph=stamping(adapter, registry=datasets), views=InMemoryCaseViewStore(),
            items=items, datasets=datasets, ontology=ontology, scheme=scheme,
            media=InMemoryMediaStore(),
        )  # fmt: skip
        scoped = await scope_to_case(ALICE, K, datasets)
        board = await boards.views.save_board(K, "Wing B", "alice", node_ids=[])

        async def person(name: str, grade: Grading) -> str:
            made = await boards.declare(
                board,
                DrawnItemInput(type="Person", label=name, marking="OFFICIAL", grading=grade,
                               source_note="Wing officer report", properties={"family_name": name}),
                scoped,
            )  # fmt: skip
            return made.element_id

        tall = await person("Tall", Grading(source="B", intelligence="2", handling="1"))
        short = await person("Short", Grading(source="C", intelligence="3", handling="4"))
        link = await boards.link(
            board,
            DrawnLinkInput(type="ASSOCIATE_OF", label="seen together", marking="OFFICIAL",
                           grading=Grading(source="A", intelligence="1", handling="1"),
                           source_note="Visits log", source=tall, target=short),
            scoped,
        )  # fmt: skip

        async def registered() -> list[BoardItem]:
            return list(items.items.values())

        yield SimpleNamespace(
            adapter=adapter, nodes=[tall, short], edge=link.element_id,
            port=BoardGradedItems(
                adapter, registered, operator_reader(scheme, org_unit=UNIT), written_by="ops-1"
            ),
            reader=operator_reader(scheme, org_unit=UNIT),
        )


async def _stored(world: SimpleNamespace) -> dict[str, dict[str, Any]]:
    """Each drawn element as stored, the fields the change must keep and the two it changes."""
    with sources_in_full():
        nodes = await world.adapter.get_nodes(world.nodes, world.reader)
        edges = await world.adapter.get_edges([world.edge], world.reader)
    found: dict[str, dict[str, Any]] = {}
    for element in [*nodes, *edges]:
        drawn = element.provenance.drawn
        assert drawn is not None
        found[element.id] = {
            "grading": drawn.grading,
            "original": drawn.original_grading,
            "kept": (
                element.type, element.properties, element.handling, element.datasets,
                drawn.model_dump(exclude={"grading", "original_grading"}),
            ),
        }
    return found


async def _links_of_the_pair(world: SimpleNamespace) -> int:
    """Every link stored in the drawn link's own type: the throwaway database holds no other, so a
    rewrite that wrote a second link beside the first counts two."""
    held = await world.adapter._holders("edge", [world.edge])
    assert len(held) == 1, held
    rows = await world.adapter._client.sql(f"SELECT count(*) AS n FROM `{held[0][0]}`")
    return int(rows[0]["n"])


async def test_the_change_rewrites_each_grade_in_the_store_keeping_its_original_and_the_rest(
    drawn: SimpleNamespace,
) -> None:
    async def audit(plan: Any) -> None:
        audited.append(plan)

    audited: list[Any] = []
    before = await _stored(drawn)
    assert len(before) == 3 and all(v["original"] is None for v in before.values())

    planned = await change(
        drawn.port, parse_mapping(FIVE_TO_THREE), current="5x5x5", dry_run=True, audit=audit
    )
    assert planned.to_change == 3 and planned.written == 0
    assert await _stored(drawn) == before and audited == []

    done = await change(
        drawn.port, parse_mapping(FIVE_TO_THREE), current="5x5x5", dry_run=False, audit=audit
    )
    assert done.written == 3 and len(audited) == 1
    after = await _stored(drawn)
    tall, short = drawn.nodes
    assert after[tall]["grading"] == Grading(
        scheme="3x5x2", source="A", intelligence="2", handling="P"
    )
    assert after[short]["grading"] == Grading(
        scheme="3x5x2", source="B", intelligence="3", handling="C"
    )
    for element_id, was in before.items():
        assert after[element_id]["original"] == was["grading"], element_id
        assert after[element_id]["kept"] == was["kept"], element_id
    assert await _links_of_the_pair(drawn) == 1

    # Back again: the original is the grade before the first change, never the middle one.
    await change(
        drawn.port, parse_mapping(THREE_TO_FIVE), current="3x5x2", dry_run=False, audit=audit
    )
    again = await _stored(drawn)
    for element_id, was in before.items():
        assert again[element_id]["original"] == was["grading"], element_id
        assert again[element_id]["grading"].scheme == "5x5x5"
    assert await _links_of_the_pair(drawn) == 1
