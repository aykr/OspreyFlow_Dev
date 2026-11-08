"""A merge in a case made from another before L3.2, against a real ArcadeDB (a lane's leased test
stack; L3.2 item 3, the lane review's round 2).

The adapter unions a merged node's datasets. So a write naming no dataset, stamped into the source,
whose id is a node of the original's layer, would put that node into the source every other case
reads. A member holding no level on the original cannot read the node, so a check on what they read
would let it through. The case writes nothing at all (`refuse_writing_in_an_unconverted_case`), and
this shows the refusal holding at the real adapter, red with it removed.
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api import dataset_scope
from services.api.dataset_scope import set_case_datasets, stamping
from services.api.datasets import TouchesTheOriginalsWorkError

from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal

from .test_unconverted_case_writes import _a_case_made_from_another, _merging, _nobody_holds

ONTOLOGY = load_default_ontology()
READS_ALL = Principal(id="reader", clearance="SECRET", org_unit="unit-1")


@pytest.fixture(autouse=True)
def _no_case_left_in_scope() -> object:
    yield
    set_case_datasets(None)


async def _a_strangers_merge(graph: Any) -> tuple[list[str], Exception | None]:
    """The original's node, written into its layer; then the stranger's write of the same id from
    the case made from it. Returns the node's datasets after, and the refusal if any."""
    store, layer, _ = await _a_case_made_from_another(_nobody_holds)  # scoped as their request is
    # The original's node, through the adapter itself, which names its datasets and reads no scope.
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([_merging("theirs").model_copy(update={"datasets": [layer]})], tx)
    await graph.commit_transaction(tx)
    graph_for_the_case = stamping(graph, registry=store)
    tx = await graph_for_the_case.begin_transaction()
    refused: Exception | None = None
    try:
        await graph_for_the_case.upsert_nodes([_merging("theirs")], tx)
        await graph_for_the_case.commit_transaction(tx)
    except TouchesTheOriginalsWorkError as error:
        refused = error
        await graph_for_the_case.rollback_transaction(tx)
    set_case_datasets(None)
    node = await graph.get_node("theirs", READS_ALL)
    assert node is not None
    return sorted(node.datasets), refused


async def test_a_strangers_merge_is_refused_at_the_real_adapter() -> None:
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        datasets, refused = await _a_strangers_merge(graph)
    assert refused is not None
    assert "src" not in datasets


async def test_the_merge_check_fails_at_the_real_adapter_with_the_refusal_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15, red: the refusal removed, the adapter's merge carries the original's layer node
    into the source."""

    async def allowed() -> None:
        return None

    monkeypatch.setattr(dataset_scope, "refuse_writing_in_an_unconverted_case", allowed)
    async with arcadedb_adapter(ONTOLOGY, load_uk_le_scheme()) as graph:
        datasets, refused = await _a_strangers_merge(graph)
    assert refused is None
    assert "src" in datasets
