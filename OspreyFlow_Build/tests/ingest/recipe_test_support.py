"""What the recipe-engine tests in this folder share: a graph stand-in that refuses what the
ArcadeDB adapter refuses, and the local-staging fixture.

**The graph (`ValidatingGraph`).** Bound to the ontology it is given, it refuses (rule 15: a fake
refuses what the real store refuses) a type the ontology lacks (`adapter.py` `upsert_nodes` and
`upsert_edges`), an undeclared property (`validate_properties`, run for every node and link), and a
link whose ends its type does not allow (`validate_edge_endpoints`). It models the transaction: a
write is "committed" only after `commit_transaction` (which refuses a commit after a rollback, as a
real session would, and counts commits), and a rollback records what it discarded, so a test can
show a refusal came at the write it names and that nothing was committed. `find_node` answers from
what is committed or open, so `on_match: reference` finds a node an earlier run or an earlier row
wrote. It does not model access filtering; a test that needs it states so.

**The staging fixture (`local_staging`, autouse once imported into a test module).** The engine
stages every run as Parquet through `staging.filesystem`, which is the object store's. Pointed at a
temporary directory instead, the same write and read-back happen and no store is touched.

Import both into a test module with `# noqa: F401` on the fixture.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pyarrow.fs as pa_fs
import pytest
from services.ingest import staging

from ontology.errors import OntologyError
from ontology.validation import validate_edge_endpoints, validate_properties
from schemas.domain import EdgeWrite, NodeWrite, OntologySchema


class LocalStore:
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
def local_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "staging"
    root.mkdir()
    monkeypatch.setattr(staging, "filesystem", lambda config: LocalStore(root))


class ValidatingGraph:
    """See the module docstring. `ontology` may be a callable, so a test can plant a variant
    through it."""

    def __init__(self, ontology: OntologySchema | Any) -> None:
        self._ontology = ontology
        self.committed_nodes: list[NodeWrite] = []
        self.committed_edges: list[EdgeWrite] = []
        self.open_nodes: list[NodeWrite] = []
        self.open_edges: list[EdgeWrite] = []
        self.discarded_nodes: list[NodeWrite] = []
        self.discarded_edges: list[EdgeWrite] = []
        self.rolled_back = 0
        self.commits = 0
        self._begun = 0
        self._rolled_back_txs: set[object] = set()

    def _schema(self) -> OntologySchema:
        return self._ontology() if callable(self._ontology) else self._ontology

    @property
    def nodes(self) -> dict[str, NodeWrite]:
        return {n.id: n for n in self.committed_nodes}

    @property
    def edges(self) -> list[EdgeWrite]:
        return self.committed_edges

    async def begin_transaction(self) -> str:
        self._begun += 1
        return f"tx-{self._begun}"

    async def commit_transaction(self, tx: object) -> None:
        # A rolled-back session has nothing left to commit; the real store refuses it.
        if tx in self._rolled_back_txs:
            raise RuntimeError(f"transaction {tx!r} was rolled back and cannot be committed")
        self.commits += 1
        self.committed_nodes.extend(self.open_nodes)
        self.committed_edges.extend(self.open_edges)
        self.open_nodes, self.open_edges = [], []

    async def rollback_transaction(self, tx: object) -> None:
        self.discarded_nodes.extend(self.open_nodes)
        self.discarded_edges.extend(self.open_edges)
        self.open_nodes, self.open_edges = [], []
        self._rolled_back_txs.add(tx)
        self.rolled_back += 1

    async def find_node(self, entity_type: str, field: str, value: str, principal: Any) -> Any:
        for node in [*self.committed_nodes, *self.open_nodes]:
            if node.type == entity_type and str(node.properties.get(field)) == value:
                return SimpleNamespace(id=node.id)
        return None

    async def get_nodes(self, node_ids: Sequence[str], principal: Any) -> list[Any]:
        """The nodes the ids name, committed ones, each once, ordered by id. Models no access
        filtering (the class docstring says so): `BlindGraph` in
        `test_load_record_created_and_merged.py` is the one that shows the loader nothing."""
        known = {n.id for n in self.committed_nodes}
        return [SimpleNamespace(id=i) for i in sorted(set(node_ids) & known)]

    async def get_edges(self, edge_ids: Sequence[str], principal: Any) -> list[Any]:
        """The committed links the ids name, each once, ordered by id. Models no access filtering
        (the class docstring says so); `BlindToEdges` in `test_load_record_created_and_merged.py`
        is the one that shows the loader nothing."""
        known = {e.id for e in self.committed_edges}
        return [SimpleNamespace(id=i) for i in sorted(set(edge_ids) & known)]

    async def existing_node_ids(self, node_ids: Sequence[str]) -> set[str]:
        """The ids that name a node, committed or open, whoever may read it: the port's internal,
        unfiltered check (the class docstring says this stand-in models no access filtering, so it
        is the same answer either way; `BlindGraph` in `test_load_record_created_and_merged.py` is
        the one that hides nodes from `get_nodes`)."""
        known = {n.id for n in [*self.committed_nodes, *self.open_nodes]}
        return set(node_ids) & known

    def _type_of(self, node_id: str) -> str | None:
        for node in [*self.committed_nodes, *self.open_nodes]:
            if node.id == node_id:
                return node.type
        return None

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: object) -> list[str]:
        ontology = self._schema()
        for node in nodes:
            entity_type = ontology.entity_type(node.type)
            if entity_type is None:
                raise OntologyError(f"{node.type!r} is not a type in the active ontology")
            validate_properties(entity_type, node.properties)
        self.open_nodes.extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: object) -> list[str]:
        ontology = self._schema()
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
