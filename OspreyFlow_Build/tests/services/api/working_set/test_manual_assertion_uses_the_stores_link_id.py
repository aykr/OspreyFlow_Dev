"""ADR-102 Amendment 3: a manual `SAME_AS` asserted twice between one pair, in one audience, merges
into the link already there, and `upsert_edges` returns that link's id, not the one sent.

What `WorkingSetService._manual_assertion` does after the write must use the id returned: the
change-stream entry names the link the store holds, and the cluster recomputation counts that link
once, under its own id, not once under it and once under an id nothing holds. The graph fake merges
a second write onto the pair as the adapter does."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from services.api.working_set import service as service_module
from services.api.working_set.service import WorkingSetService
from services.resolve.projection import compute_clusters

from schemas.domain import AuditStub, Edge, EdgeWrite, Subgraph, TxId

from .fakes import FakeGraphPort, FakeWorkingSetStore
from .test_manual_resolution import INVESTIGATION, PRINCIPAL, SCHEME, _person


class MergingGraph(FakeGraphPort):
    """A graph that holds one `SAME_AS` link per pair: a second write between the pair is the first
    link, and its id comes back. `expand` shows the links held."""

    def __init__(self) -> None:
        super().__init__(Subgraph(nodes=[_person("n1"), _person("n2")], edges=[]))
        self.held: dict[frozenset[str], EdgeWrite] = {}
        self.sent: list[str] = []

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[str]:
        ids: list[str] = []
        for write in edges:
            self.sent.append(write.id)
            held = self.held.setdefault(frozenset((write.source, write.target)), write)
            ids.append(held.id)
        return ids

    async def expand(self, req: Any, principal: Any) -> Subgraph:
        edges = [
            Edge(
                id=w.id,
                type=w.type,
                source=w.source,
                target=w.target,
                properties=dict(w.properties),
                provenance=w.provenance,
                handling=w.handling,
                audit=AuditStub(created_at=w.created_at, created_by=w.created_by),
            )
            for w in self.held.values()
        ]
        return Subgraph(nodes=[_person("n1"), _person("n2")], edges=edges)


class RecordingValkey:
    """Just the stream append `ChangeStreamWriter.publish` makes."""

    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []

    async def xadd(self, key: str, fields: dict[str, str]) -> str:
        self.entries.append(fields)
        return f"{len(self.entries)}-0"


async def test_a_second_manual_same_as_on_a_pair_is_published_and_clustered_under_the_stored_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FakeWorkingSetStore()
    graph = MergingGraph()
    valkey = RecordingValkey()
    service = WorkingSetService(graph, store, SCHEME, valkey=valkey)  # type: ignore[arg-type]
    await store.add_nodes(INVESTIGATION, [_person("n1"), _person("n2")])

    await service.manual_link(INVESTIGATION, "n1", "n2", PRINCIPAL)
    (first_id,) = graph.sent

    clustered: list[list[str]] = []

    def recording(ids: Any, same_as: Sequence[Edge], not_same_as: Any, tau: float) -> Any:
        clustered.append([e.id for e in same_as])
        return compute_clusters(ids, same_as, not_same_as, tau)

    monkeypatch.setattr(service_module, "compute_clusters", recording)
    _, entry = await service.manual_link(INVESTIGATION, "n1", "n2", PRINCIPAL)

    assert len(graph.sent) == 2 and graph.sent[1] != first_id, "the second write sent a fresh id"
    assert entry is not None and entry.edge_ids == [first_id]
    assert valkey.entries[1]["edge_ids"] == first_id
    # The recomputation after the write counts the one link under its one id.
    assert set(clustered[-1]) == {first_id}
