"""The pack export says whether the pack holds material the exporter may not view, and never how
much (ADR-124 decision 9, ruled for packs on 25 October 2026).

`PackExport.withheld` is `bool | None`: under `disclose` the exporter's standing sentence for the
pack's own material, true or false and never `None`; under `omit` it is absent. The scope is the
pack's own items (`packs.readable`): an item the exporter's handling does not clear, or an entity
item whose node the exporter's graph read no longer returns. It is not the case's stored set. The
ledger entry holds the same yes or no. Pure: `export_pack` over a graph stand-in and a ledger that
records, no connection. The route, the real ledger and the HTTP shape are `test_pack_export.py`.

The graph stand-in judges a node by its handling alone, as `test_packs.py`'s `_Graph` does. What the
real adapter does with a node outside the exporter's datasets is not shown here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.packs import PackVersion, StoredPackItem, export_pack, item_visible

from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AuditStub,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.packs import EntitySnapshot, PackExportRequest, ReportPack

SCHEME = load_uk_le_scheme()
NOW = datetime(2026, 3, 1, tzinfo=UTC)
OFFICIAL = Principal(id="low", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
SECRET = Principal(id="high", clearance="SECRET", org_unit="unit-1", roles=["analyst"])


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(
        classification=classification, handling_code="P", owning_unit="unit-1", originator="unit-1"
    )


class _Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}

    def add(self, node_id: str, classification: str, datasets: list[str]) -> None:
        self.nodes[node_id] = Node(
            id=node_id,
            type="Person",
            properties={"name": node_id},
            handling=_handling(classification),
            datasets=datasets,
            provenance=Provenance(
                state=ProvenanceState.ASSERTED,
                first_seen=NOW,
                sources=[SourceRef(document_id="d1", locator="p1", excerpt_hash="h")],
            ),
            audit=AuditStub(created_at=NOW, created_by="ed", revision=1),
        )

    async def get_node(
        self, node_id: str, principal: Principal, *, include_superseded: bool = False
    ) -> Node | None:
        node = self.nodes.get(node_id)
        if node is None or not item_visible([node.handling], principal, SCHEME):
            return None
        return node


class _Ledger:
    def __init__(self) -> None:
        self.entries: list[Any] = []

    async def record(self, entry: Any) -> None:
        self.entries.append(entry)


def _note(item_id: str, classification: str) -> StoredPackItem:
    return StoredPackItem(
        id=item_id,
        kind="note",
        marking=classification,
        added_by="ed",
        added_at=NOW,
        note=item_id,
        handlings=[_handling(classification)],
    )


def _entity(item_id: str, node_id: str, classification: str = "OFFICIAL") -> StoredPackItem:
    return StoredPackItem(
        id=item_id,
        kind="entity",
        marking=classification,
        added_by="ed",
        added_at=NOW,
        entity=EntitySnapshot(node_id=node_id, entity_type="Person", name=node_id, caption="c"),
        handlings=[_handling(classification)],
    )


async def _export(
    items: list[StoredPackItem], graph: _Graph, reader: Principal, policy: str = "disclose"
) -> tuple[Any, _Ledger]:
    ledger = _Ledger()
    pack = ReportPack(
        id="p1", investigation_id="inv-1", title="t", created_by="ed", created_at=NOW,
        updated_at=NOW,
    )  # fmt: skip
    version = PackVersion(pack_id="p1", version=1, published_at=NOW, published_by="ed", items=items)
    result = await export_pack(
        pack=pack,
        version=version,
        request=PackExportRequest(),
        exporter=reader,
        scheme=SCHEME,
        graph=graph,  # type: ignore[arg-type]
        ledger=ledger,  # type: ignore[arg-type]
        policy=policy,  # type: ignore[arg-type]
    )
    return result, ledger


async def test_pack_material_hidden_by_handling_is_true_and_a_cleared_exporter_gets_false() -> None:
    """Violation caught: the pack export a count (`2`) to a recipient, or no signal at all."""
    items = [_note("n1", "OFFICIAL"), _note("n2", "SECRET"), _note("n3", "SECRET")]
    low, _ = await _export(items, _Graph(), OFFICIAL)
    high, _ = await _export(items, _Graph(), SECRET)
    assert low.withheld is True
    assert high.withheld is False


async def test_an_entity_item_hidden_by_handling_is_true() -> None:
    graph = _Graph()
    graph.add("pub", "OFFICIAL", ["a"])
    graph.add("sec", "SECRET", ["a"])
    result, _ = await _export([_entity("e1", "pub"), _entity("e2", "sec")], graph, OFFICIAL)
    assert result.withheld is True


async def test_the_hidden_items_datasets_make_no_difference() -> None:
    """Violation caught (rule 3): the flag turns on where the hidden material sits. Two packs that
    differ only in the datasets of the hidden node say the same thing, true in both."""
    answers = []
    for datasets in (["a"], ["b"], []):
        graph = _Graph()
        graph.add("pub", "OFFICIAL", ["a"])
        graph.add("sec", "SECRET", datasets)
        result, _ = await _export([_entity("e1", "pub"), _entity("e2", "sec")], graph, OFFICIAL)
        answers.append(result.withheld)
    assert answers == [True, True, True]


async def test_readable_material_in_another_dataset_is_false() -> None:
    """The other half, for the handling-only stand-in: a node the exporter may read, whatever its
    datasets, withholds nothing."""
    answers = []
    for datasets in (["a"], ["b"]):
        graph = _Graph()
        graph.add("one", "OFFICIAL", datasets)
        result, _ = await _export([_entity("e1", "one"), _note("n1", "OFFICIAL")], graph, OFFICIAL)
        answers.append(result.withheld)
    assert answers == [False, False]


@pytest.mark.parametrize("held_back", [True, False])
async def test_under_omit_the_pack_has_no_flag_and_the_ledger_has_the_yes_or_no(
    held_back: bool,
) -> None:
    items = [_note("n1", "OFFICIAL"), *([_note("n2", "SECRET")] if held_back else [])]
    result, ledger = await _export(items, _Graph(), OFFICIAL, policy="omit")
    assert result.withheld is None
    (entry,) = ledger.entries
    assert entry.withheld is held_back


async def test_under_disclose_the_flag_is_never_none_and_matches_the_ledger() -> None:
    for extra in ([], [_note("n2", "SECRET")]):
        result, ledger = await _export([_note("n1", "OFFICIAL"), *extra], _Graph(), OFFICIAL)
        assert isinstance(result.withheld, bool)
        assert ledger.entries[0].withheld is result.withheld
        assert "withheld_count" not in result.model_dump()
