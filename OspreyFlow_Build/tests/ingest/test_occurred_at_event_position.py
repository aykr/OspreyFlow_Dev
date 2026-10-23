"""ADR-120 Amendment 7 decision 1: a throw-over's yard position, yard and item reach the event
through its `OCCURRED_AT` link, through the recipe engine, against the deployment's own ontology
(core plus NIEM), not the core alone. What a mistake would do, and the case that catches it:

- `OCCURRED_AT` declaring none of the four, so the graph refuses the first throw-over link and the
  run fails outright (`test_a_throw_over_link_carries_its_position_yard_and_item_to_its_event`);
- a text latitude left a string, so the event has no position and the map never draws it (the same
  case: `lat` and `lon` must be floats on the event);
- an undeclared link property accepted, so the graph would hold whatever a column was called
  (`test_an_undeclared_link_property_fails_the_run_and_commits_nothing`).

The load goes through `load_with_rules` with no rules (`studio_publish.py`), the one place that
begins, rolls back and commits the transaction, so "nothing committed" is production code's doing.
The graph stand-in refuses what the ArcadeDB adapter refuses (rule 15): a type the ontology lacks
(`adapter.py` `upsert_nodes` and `upsert_edges`), an undeclared property (`validate_properties`,
called for every node and link), and a link whose ends its type does not allow
(`validate_edge_endpoints`). It models the transaction: a write is "committed" only after
`commit_transaction` (which refuses a commit after a rollback, as a real session would, and counts
commits), and a rollback records what it discarded, so the refusal is shown to come at the link's
own write and not earlier. The run's Parquet staging goes to a temporary local
directory, not the deployment's object store."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pyarrow.fs as pa_fs
import pytest
from services.api.studio_publish import load_with_rules
from services.ingest import staging

from ontology.errors import OntologyError
from ontology.packs import load_deployment_ontology
from ontology.validation import validate_edge_endpoints, validate_properties
from schemas.analytics import EventRecord
from schemas.domain import EdgeWrite, NodeWrite, OntologySchema, Principal
from schemas.ingest import Recipe

LOADER = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1")
LOAD_ID = "load-occurred-at-position-1"


class _LocalStore:
    """The slice of the object store's file system the staging module uses, over a directory. An
    object store has no directories to make before a write; a disk does, so a write makes them."""

    def __init__(self, root: Path) -> None:
        self._fs = pa_fs.SubTreeFileSystem(str(root), pa_fs.LocalFileSystem())

    def create_dir(self, path: str) -> None:
        self._fs.create_dir(path, recursive=True)

    def open_output_stream(self, path: str) -> Any:
        self._fs.create_dir(path.rsplit("/", 1)[0], recursive=True)
        return self._fs.open_output_stream(path)

    def open_input_file(self, path: str) -> Any:
        return self._fs.open_input_file(path)


@pytest.fixture(autouse=True)
def _local_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The engine stages every run as Parquet through `staging.filesystem`, which is the object
    store's. Pointed at a temporary directory instead, the same write and read-back happen and no
    store is touched."""
    root = tmp_path / "staging"
    root.mkdir()
    monkeypatch.setattr(staging, "filesystem", lambda config: _LocalStore(root))


def _ontology() -> OntologySchema:
    """The one place the test's ontology comes from, so a variant can be planted through it."""
    return load_deployment_ontology()


class TransactionalGraph:
    """A fake graph bound to `_ontology()` that refuses as the real adapter does."""

    def __init__(self) -> None:
        self.committed_nodes: list[NodeWrite] = []
        self.committed_edges: list[EdgeWrite] = []
        self.open_nodes: list[NodeWrite] = []
        self.open_edges: list[EdgeWrite] = []
        self.discarded_nodes: list[NodeWrite] = []
        self.discarded_edges: list[EdgeWrite] = []
        self.rolled_back = 0
        self.commits = 0

    async def begin_transaction(self) -> str:
        return "tx-1"

    async def commit_transaction(self, tx: object) -> None:
        # A rolled-back session has nothing left to commit; the real store refuses it.
        if self.rolled_back:
            raise RuntimeError(f"transaction {tx!r} was rolled back and cannot be committed")
        self.commits += 1
        self.committed_nodes.extend(self.open_nodes)
        self.committed_edges.extend(self.open_edges)
        self.open_nodes, self.open_edges = [], []

    async def rollback_transaction(self, tx: object) -> None:
        self.discarded_nodes.extend(self.open_nodes)
        self.discarded_edges.extend(self.open_edges)
        self.open_nodes, self.open_edges = [], []
        self.rolled_back += 1

    async def find_node(self, *args: Any, **kwargs: Any) -> None:
        return None

    def _type_of(self, node_id: str) -> str | None:
        for node in [*self.committed_nodes, *self.open_nodes]:
            if node.id == node_id:
                return node.type
        return None

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: object) -> list[str]:
        ontology = _ontology()
        for node in nodes:
            entity_type = ontology.entity_type(node.type)
            if entity_type is None:
                raise OntologyError(f"{node.type!r} is not a type in the active ontology")
            validate_properties(entity_type, node.properties)
        self.open_nodes.extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: object) -> list[str]:
        ontology = _ontology()
        for edge in edges:
            edge_type = ontology.edge_type(edge.type)
            if edge_type is None:
                raise OntologyError(f"{edge.type!r} is not a type in the active ontology")
            validate_properties(edge_type, edge.properties)
            source_type = self._type_of(edge.source)
            target_type = self._type_of(edge.target)
            if source_type is None:
                raise OntologyError(f"edge source {edge.source!r} does not exist")
            if target_type is None:
                raise OntologyError(f"edge target {edge.target!r} does not exist")
            validate_edge_endpoints(edge_type, source_type=source_type, target_type=target_type)
        self.open_edges.extend(edges)
        return [e.id for e in edges]


def _throw_over_recipe(*, undeclared: bool = False) -> Recipe:
    link_properties: dict[str, Any] = {
        "lat": {"field": "lat"},
        "lon": {"field": "lon"},
        "yard": {"field": "yard"},
        "item_type": {"field": "item_type"},
    }
    if undeclared:
        link_properties["recovered"] = {"field": "recovered"}
    ontology = _ontology()
    return Recipe.model_validate(
        {
            "id": "throw-over",
            "version": 1,
            "label": "Throw-overs",
            "connector": {"profile": "csv"},
            "ontology_version": ontology.version,
            "pack_versions": {"niem": 3},
            "defaults": {
                "provenance": {"state": "asserted"},
                "handling": {
                    "classification": "OFFICIAL",
                    "handling_code": "P",
                    "originator": "unit-1",
                    "owning_unit": "unit-1",
                },
            },
            "row_template": {
                "entities": [
                    {
                        "ref": "incident",
                        "pole_class": "event",
                        "type": "Incident",
                        "properties": {
                            "incident_ref": {"field": "incident_ref"},
                            "category": {"field": "category"},
                            "occurred_at": {"field": "occurred_at"},
                        },
                    },
                    {
                        "ref": "place",
                        "pole_class": "location",
                        "type": "Location",
                        "properties": {"site_ref": {"field": "site_ref"}},
                    },
                ],
                "edges": [
                    {
                        "type": "OCCURRED_AT",
                        "from": "incident",
                        "to": "place",
                        "temporal": {
                            "at": {"field": "occurred_at", "transform": "datetime(tz=UTC)"}
                        },
                        "properties": link_properties,
                    }
                ],
            },
        }
    )


def _row() -> dict[str, str]:
    """CSV-shaped: every value is text, as the connector produces it."""
    return {
        "incident_ref": "I0001ZZ",
        "category": "throw_over",
        "occurred_at": "2026-03-05T14:30:00Z",
        "site_ref": "S0001ZZ",
        "lat": "51.43",
        "lon": "-1.15",
        "yard": "03",
        "item_type": "mobile phone",
        "recovered": "yes",
    }


async def _run(graph: TransactionalGraph, recipe: Recipe) -> tuple[Any, list[EventRecord]]:
    report, events, _held = await load_with_rules(
        recipe,
        [_row()],
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=_ontology(),
        load_id=LOAD_ID,
        investigation_scope="case-1",
        source="throw-overs.csv",
        rules=None,
    )
    return report, events


async def test_a_throw_over_link_carries_its_position_yard_and_item_to_its_event() -> None:
    graph = TransactionalGraph()
    report, events = await _run(graph, _throw_over_recipe())
    assert report.rejections == []
    (event,) = [e for e in events if e.edge_type == "OCCURRED_AT"]
    assert isinstance(event.lat, float) and event.lat == 51.43
    assert isinstance(event.lon, float) and event.lon == -1.15
    assert event.properties["yard"] == "03"
    assert event.properties["item_type"] == "mobile phone"
    assert graph.commits == 1 and graph.rolled_back == 0
    (link,) = graph.committed_edges
    assert link.properties == {
        "lat": 51.43,
        "lon": -1.15,
        "yard": "03",
        "item_type": "mobile phone",
    }


async def test_an_undeclared_link_property_fails_the_run_and_commits_nothing() -> None:
    graph = TransactionalGraph()
    # Naming `recovered` alone: while the four are undeclared the message names them too, and a
    # run that failed for that reason would otherwise pass here.
    with pytest.raises(
        OntologyError, match=re.escape("'OCCURRED_AT' does not declare property 'recovered'")
    ):
        await _run(graph, _throw_over_recipe(undeclared=True))
    # The refusal came at the link's own write: the row's Incident and Location were written into
    # the open transaction first, no link was, and the rollback discarded exactly those two nodes.
    assert graph.rolled_back == 1 and graph.commits == 0
    assert sorted(n.type for n in graph.discarded_nodes) == ["Incident", "Location"]
    assert graph.discarded_edges == []
    assert graph.open_nodes == [] and graph.open_edges == []
    assert graph.committed_nodes == [] and graph.committed_edges == []
