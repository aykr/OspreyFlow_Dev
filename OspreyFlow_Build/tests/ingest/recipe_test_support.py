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

import asyncio
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pyarrow.fs as pa_fs
import pytest
from conduit_common.identity import new_edge_id
from ontology.errors import OntologyError
from ontology.handling import audience_of, load_uk_le_scheme, merge_handling
from ontology.validation import validate_edge_endpoints, validate_properties
from ports.graph import StoredLink, StoredNode
from schemas.domain import EdgeWrite, NodeWrite, OntologySchema
from schemas.ingest import LinkPriorState
from schemas.merge import aggregate_edge_writes
from services.ingest import staging


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
                return SimpleNamespace(id=node.id, type=node.type)
        return None

    async def get_nodes(self, node_ids: Sequence[str], principal: Any) -> list[Any]:
        """The nodes the ids name, committed ones, each once, ordered by id. Models no access
        filtering (the class docstring says so): `BlindGraph` in
        `test_load_record_created_and_merged.py` is the one that shows the loader nothing.
        The real port returns whole `Node`s; this carries the id, type and marking a caller reads
        (an alert's own handlings, ADR-134 decision 3), as the first committed write left them."""
        known: dict[str, NodeWrite] = {}
        for n in self.committed_nodes:
            known.setdefault(n.id, n)
        return [
            SimpleNamespace(id=i, type=known[i].type, handling=known[i].handling)
            for i in sorted(set(node_ids) & known.keys())
        ]

    async def get_edges(self, edge_ids: Sequence[str], principal: Any) -> list[Any]:
        """The committed links the ids name, each once, ordered by id. Models no access filtering
        (the class docstring says so); `BlindToEdges` in `test_load_record_created_and_merged.py`
        is the one that shows the loader nothing.
        The real port returns whole `Edge`s; this carries the id, type and marking a caller reads
        (ADR-134 decision 3), as the first committed write left them."""
        known: dict[str, EdgeWrite] = {}
        for e in self.committed_edges:
            known.setdefault(e.id, e)
        return [
            SimpleNamespace(id=i, type=known[i].type, handling=known[i].handling)
            for i in sorted(set(edge_ids) & known.keys())
        ]

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

    def _validate_edge(self, edge: EdgeWrite) -> None:
        """What `upsert_edges` refuses before anything else: a type the ontology lacks, an undeclared
        property, an end that does not exist, an end the type does not allow."""
        ontology = self._schema()
        edge_type = ontology.edge_type(edge.type)
        if edge_type is None:
            raise OntologyError(f"{edge.type!r} is not a type in the active ontology")
        validate_properties(edge_type, edge.properties)
        if edge.writes < 1:
            raise OntologyError(f"a write standing for {edge.writes} writes: at least one")
        source_type = self._type_of(edge.source)
        target_type = self._type_of(edge.target)
        if source_type is None:
            raise OntologyError(f"edge source {edge.source!r} does not exist")
        if target_type is None:
            raise OntologyError(f"edge target {edge.target!r} does not exist")
        validate_edge_endpoints(edge_type, source_type=source_type, target_type=target_type)

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: object) -> list[str]:
        for edge in edges:
            # A real adapter awaits the store for every write, so the loop gets a turn between
            # them; the stand-in's linear scans over a million nodes must not hold it either
            # (ADR-127 Amendment 29: a stall here is the stand-in's, not the run's).
            await asyncio.sleep(0)
            self._validate_edge(edge)
        self.open_edges.extend(edges)
        return [e.id for e in edges]


class MergingGraph(ValidatingGraph):
    """`ValidatingGraph`, with the real store's link merge (`_find_existing_edge`, ADR-102
    Amendment 3): a link of the same type between the same two parties, in either order for an
    undirected type, is merged into when it has the write's audience (`audience_of`: classification,
    handling code, datasets, and the units under a restricted code), unless it has been reverted or
    superseded; its id comes back, so the caller's own id differs from the one returned. A write of
    another audience is a link of its own. A test marks a link reverted by adding its id to
    `reverted`.

    **The merge itself is the adapter's** (rule 15: a fake does what the real store does): the
    stored link is replaced by `schemas.merge.aggregate_edge_writes` over the stored link and the
    write, the one rule both of the adapter's write paths use. So occurrences add, the interval
    widens (and is open if either is), provenance sources are kept, the latest write's properties win
    unless they would lower an asserted link (`merge_properties`), datasets are added and the handling
    is merged and never lowered; the first write's id, ends and creation stay. A rollback puts back
    what a merge replaced."""

    def __init__(self, ontology: Any) -> None:
        super().__init__(ontology)
        self.reverted: set[str] = set()
        #: Element id -> the load that withdrew it (ADR-110 Amendment 6 point 3); each is reverted.
        self.withdrawn: dict[str, str] = {}
        self.reverted_calls: list[tuple[list[str], list[str]]] = []
        self.superseded: set[str] = set()
        self._scheme = load_uk_le_scheme()
        #: What each merge replaced, so a rollback puts it back: (the list, its index, the link).
        self._replaced: list[tuple[list[EdgeWrite], int, EdgeWrite]] = []
        #: The revision of each link (the `writes` it was made with, and each merged write's `writes`
        #: added to it), which the adapter keeps in `audit.revision` and chooses among a pair's links
        #: by (ADR-127 Amendment 19).
        self._revision: dict[str, int] = {}
        self._revisions_before: list[tuple[str, int | None]] = []
        #: Each link's last writing load, as the adapter keeps it in `audit.load_id`: a merge sets
        #: it to the merging write's (ADR-110 Amendment 16 reads it to know a link written since).
        self._last_load: dict[str, str | None] = {}
        self._last_loads_before: list[tuple[str, str | None, bool]] = []

    async def commit_transaction(self, tx: object) -> None:
        await super().commit_transaction(tx)
        self._replaced = []
        self._revisions_before = []
        self._last_loads_before = []

    async def rollback_transaction(self, tx: object) -> None:
        await super().rollback_transaction(tx)
        for held, index, before in reversed(self._replaced):
            held[index] = before
        for link_id, previous in reversed(self._revisions_before):
            if previous is None:
                self._revision.pop(link_id, None)
            else:
                self._revision[link_id] = previous
        for link_id, load, held in reversed(self._last_loads_before):
            if held:
                self._last_load[link_id] = load
            else:
                self._last_load.pop(link_id, None)
        self._replaced = []
        self._revisions_before = []
        self._last_loads_before = []

    def _merged(self, existing: EdgeWrite, edge: EdgeWrite, fresh: list[EdgeWrite]) -> None:
        """Replace `existing` where it is held by what the adapter would leave stored."""
        merged = aggregate_edge_writes(
            [existing, edge],
            directed=lambda name: bool(self._schema().edge_type(name).directed),  # type: ignore[union-attr]
            handling=lambda old, new: merge_handling(old, new, self._scheme),
            audience=self._audience,  # type: ignore[arg-type]
        )
        (aggregated,) = merged
        self._revisions_before.append((existing.id, self._revision.get(existing.id)))
        self._revision[existing.id] = (
            self._revision.get(existing.id, existing.writes) + edge.writes
        )
        self._note_last_load(existing.id, edge.load_id)
        for held in (self.committed_edges, self.open_edges, fresh):
            for index, link in enumerate(held):
                if link is existing:
                    self._replaced.append((held, index, existing))
                    held[index] = aggregated.write
                    return

    def _note_last_load(self, link_id: str, load_id: str | None) -> None:
        self._last_loads_before.append(
            (link_id, self._last_load.get(link_id), link_id in self._last_load)
        )
        self._last_load[link_id] = load_id

    def _held(self, link_id: str) -> tuple[list[EdgeWrite], int] | None:
        for held in (self.committed_edges, self.open_edges):
            for index, link in enumerate(held):
                if link.id == link_id:
                    return held, index
        return None

    # --- a link's prior state (ADR-110 Amendment 16), as the adapter keeps it -----------------

    async def read_link_state(self, edge_id: str, tx: object = None) -> LinkPriorState | None:
        found = self._held(edge_id)
        if found is None:
            return None
        held, index = found
        link = held[index]
        return LinkPriorState(
            edge_id=edge_id,
            edge_type=link.type,
            revision=self._revision.get(edge_id, link.writes),
            load_id=self._last_load.get(edge_id, link.load_id),
            handling=link.handling,
            stored={"write": link.model_dump(mode="json")},
        )

    async def restore_link_state(
        self, state: LinkPriorState, *, written_by: str, tx: object
    ) -> bool:
        """As the adapter: only while the link's last writing load is `written_by`; the link put
        back whole, at the marking the state was read at."""
        found = self._held(state.edge_id)
        if found is None:
            return False
        held, index = found
        if self._last_load.get(state.edge_id, held[index].load_id) != written_by:
            return False
        prior = EdgeWrite.model_validate(state.stored["write"])
        self._replaced.append((held, index, held[index]))
        held[index] = prior.model_copy(update={"handling": state.handling})
        self._revisions_before.append((state.edge_id, self._revision.get(state.edge_id)))
        self._revision[state.edge_id] = state.revision
        self._note_last_load(state.edge_id, state.load_id)
        return True

    def _audience(self, edge: EdgeWrite) -> object:
        return audience_of(edge.handling, edge.datasets, self._scheme)

    async def upsert_edges(self, edges: Any, tx: object) -> list[str]:
        ids: list[str] = []
        fresh: list[EdgeWrite] = []
        for edge in edges:
            await asyncio.sleep(0)  # as above: a real write awaits the store
            # As the adapter: every write is validated first, whether or not it merges.
            self._validate_edge(edge)
            directed = self._schema().edge_type(edge.type).directed  # type: ignore[union-attr]
            ends = (edge.source, edge.target)
            same = [
                e
                for e in [*self.committed_edges, *self.open_edges, *fresh]
                if e.type == edge.type
                and e.id not in self.reverted
                and e.id not in self.superseded
                and (
                    (e.source, e.target) == ends or (not directed and (e.target, e.source) == ends)
                )
                and self._audience(e) == self._audience(edge)
            ]
            # The adapter's deterministic choice among a pair's links of one audience (ADR-102
            # Amendment 4): the higher revision, then the later creation, then the greater id.
            existing = (
                max(same, key=lambda e: (self._revision.get(e.id, e.writes), e.created_at, e.id))
                if same
                else None
            )
            if existing is not None:
                self._merged(existing, edge, fresh)
                ids.append(existing.id)
            else:
                # Edge `id` is UNIQUE (`schema.py`): a link of another audience holding this id
                # means the write is a link of its own under a new one, which is returned.
                held = {e.id for e in [*self.committed_edges, *self.open_edges, *fresh]}
                if edge.id in held:
                    edge = edge.model_copy(update={"id": new_edge_id()})
                fresh.append(edge)
                self._revisions_before.append((edge.id, self._revision.get(edge.id)))
                self._revision[edge.id] = edge.writes
                self._note_last_load(edge.id, edge.load_id)
                ids.append(edge.id)
        await super().upsert_edges(fresh, tx)
        return ids

    # --- the revert (ADR-127 Amendment 6), as the adapter does it ---------------------------

    async def revert_elements(self, node_ids: Any, edge_ids: Any, tx: object) -> None:
        """Marks the named nodes and links reverted, by id and nothing else (`reverted` holds the
        ids of both, which never collide). Idempotent, as setting the flag again is."""
        self.reverted_calls.append((list(node_ids), list(edge_ids)))
        self.reverted.update(node_ids)
        self.reverted.update(edge_ids)
        # Reverting the load that created an element clears its withdrawal (ADR-110 Amendment 6
        # point 3), so a later restore cannot bring it back.
        for element_id in [*node_ids, *edge_ids]:
            self.withdrawn.pop(element_id, None)

    # --- a full snapshot's withdrawal (ADR-110 Amendment 6 point 3), as the adapter does it ----

    async def withdraw_elements(
        self, node_ids: Sequence[str], edge_ids: Sequence[str], load_id: str, tx: object
    ) -> None:
        """Marks each live element reverted and withdrawn by `load_id`; one already reverted (or
        withdrawn) is left as it is, as the adapter's `AND reverted = false` leaves it."""
        for element_id in [*node_ids, *edge_ids]:
            if element_id in self.reverted:
                continue
            self.reverted.add(element_id)
            self.withdrawn[element_id] = load_id

    async def restore_withdrawn(self, load_id: str, tx: object) -> Any:
        """Brings back what `load_id` withdrew, except a link whose pair a live link of the same
        type joins again (written since), as the adapter skips it."""
        from ports.graph import RestoredElements

        mine = [i for i, by in self.withdrawn.items() if by == load_id]
        edges = {e.id: e for e in self.committed_edges}
        nodes, links = [], []
        for element_id in mine:
            link = edges.get(element_id)
            if link is not None:
                again = any(
                    e.id != link.id and e.type == link.type
                    and {e.source, e.target} == {link.source, link.target}
                    and e.id not in self.reverted and e.id not in self.superseded
                    for e in self.committed_edges
                )  # fmt: skip
                if again:
                    continue
                links.append(element_id)
            else:
                nodes.append(element_id)
            self.reverted.discard(element_id)
            del self.withdrawn[element_id]
        return RestoredElements(node_ids=tuple(nodes), edge_ids=tuple(links))

    async def find_node(self, entity_type: str, field: str, value: str, principal: Any) -> Any:
        """A reverted node is no match, as the adapter's read leaves it out: a later write of the
        same value is a fresh create."""
        for node in [*self.committed_nodes, *self.open_nodes]:
            if (
                node.type == entity_type
                and str(node.properties.get(field)) == value
                and node.id not in self.reverted
            ):
                return SimpleNamespace(id=node.id, type=node.type)
        return None

    async def existing_node_ids(self, node_ids: Sequence[str]) -> set[str]:
        """A node that is reverted and not superseded is left out: a write onto it is a fresh
        create. One that is also superseded is still named, because a write to it still merges
        (the adapter's `render_live_node_ids_sql`, ADR-127 Amendment 8)."""
        return await super().existing_node_ids(node_ids) - (self.reverted - self.superseded)

    async def get_nodes(self, node_ids: Sequence[str], principal: Any) -> list[Any]:
        return [
            n for n in await super().get_nodes(node_ids, principal) if n.id not in self.reverted
        ]

    async def get_edges(self, edge_ids: Sequence[str], principal: Any) -> list[Any]:
        return [
            e for e in await super().get_edges(edge_ids, principal) if e.id not in self.reverted
        ]

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: object) -> list[str]:
        """A write onto a reverted node replaces it: the node is live again with the write's body
        alone, and the reverted body is not kept (the adapter's `replaces_reverted`)."""
        for node in nodes:
            if node.id in self.reverted:
                self.reverted.discard(node.id)
                self.withdrawn.pop(node.id, None)
                self.committed_nodes = [n for n in self.committed_nodes if n.id != node.id]
        return await super().upsert_nodes(nodes, tx)

    async def live_edges_touching(self, node_ids: Sequence[str]) -> set[str]:
        """The live links (not reverted, not superseded) at either end, whoever may read them: the
        committed ones, as the adapter's read outside any transaction sees them (rule 15: a load's
        own open links are not seen, so a withdrawal cannot lean on them)."""
        wanted = set(node_ids)
        return {
            e.id
            for e in self.committed_edges
            if (e.source in wanted or e.target in wanted)
            and e.id not in self.reverted
            and e.id not in self.superseded
        }

    async def live_nodes_naming_geometry(self, geometry_refs: Sequence[str]) -> dict[str, set[str]]:
        named: dict[str, set[str]] = {}
        for node in [*self.committed_nodes, *self.open_nodes]:
            ref = node.properties.get("geometry_ref")
            if ref in set(geometry_refs) and node.id not in self.reverted:
                named.setdefault(str(ref), set()).add(node.id)
        return named

    async def stored_writes(self, node_ids: Sequence[str]) -> dict[str, Any]:
        """The load each node was last written by, and whether it is reverted: a later write of the
        same id wins."""
        found: dict[str, Any] = {}
        for node in [*self.committed_nodes, *self.open_nodes]:
            if node.id in set(node_ids):
                found[node.id] = StoredNode(load_id=node.load_id, reverted=node.id in self.reverted)
        return found

    async def stored_link_states(self, edge_ids: Sequence[str]) -> dict[str, StoredLink]:
        known = {e.id for e in [*self.committed_edges, *self.open_edges]}
        return {
            e: StoredLink(reverted=e in self.reverted, superseded=e in self.superseded)
            for e in edge_ids
            if e in known
        }

    @property
    def live_nodes(self) -> dict[str, NodeWrite]:
        return {i: n for i, n in self.nodes.items() if i not in self.reverted}
