"""In-memory fakes for `WorkingSetService` unit tests. `WorkingSetStorage`
and the two `GraphPort` methods the service calls are both structural
(`Protocol`), so exercising the service's own logic — the cap check,
`filtered_count`'s arithmetic, the reconnect gap detection — needs neither
a live Valkey nor a live ArcadeDB. `tests/services/api/working_set/
test_valkey_store.py` covers `ValkeyWorkingSetStore` itself against the
real thing, once `make dev-up` exists to provide one.
"""

from __future__ import annotations

from collections.abc import Sequence

from services.api.working_set.models import WorkingSetDelta

from schemas.domain import (
    Edge,
    EdgeId,
    EdgeWrite,
    ExpandRequest,
    Node,
    NodeId,
    Principal,
    Subgraph,
    TxId,
)


class FakeWorkingSetStore:
    def __init__(self) -> None:
        self._nodes: dict[str, dict[NodeId, Node]] = {}
        self._edges: dict[str, dict[EdgeId, Edge]] = {}
        self._seq: dict[str, int] = {}
        self._deltas: dict[str, list[WorkingSetDelta]] = {}
        self._thresholds: dict[str, float] = {}
        #: Set to simulate the capped stream trimming older entries —
        #: `None` means unbounded (the default; most tests don't care).
        self.stream_maxlen: int | None = None

    def _n(self, investigation_id: str) -> dict[NodeId, Node]:
        return self._nodes.setdefault(investigation_id, {})

    def _e(self, investigation_id: str) -> dict[EdgeId, Edge]:
        return self._edges.setdefault(investigation_id, {})

    def _d(self, investigation_id: str) -> list[WorkingSetDelta]:
        return self._deltas.setdefault(investigation_id, [])

    async def source_fidelity_nodes(self, investigation_id: str) -> dict[NodeId, Node]:
        return dict(self._n(investigation_id))

    async def source_fidelity_edges(self, investigation_id: str) -> dict[EdgeId, Edge]:
        return dict(self._e(investigation_id))

    async def node_ids(self, investigation_id: str) -> set[NodeId]:
        return set(self._n(investigation_id))

    async def edge_ids(self, investigation_id: str) -> set[EdgeId]:
        return set(self._e(investigation_id))

    async def add_nodes(self, investigation_id: str, nodes: Sequence[Node]) -> None:
        self._n(investigation_id).update({n.id: n for n in nodes})

    async def add_edges(self, investigation_id: str, edges: Sequence[Edge]) -> None:
        self._e(investigation_id).update({e.id: e for e in edges})

    async def remove_nodes(self, investigation_id: str, node_ids: Sequence[NodeId]) -> None:
        store = self._n(investigation_id)
        for node_id in node_ids:
            store.pop(node_id, None)

    async def remove_edges(self, investigation_id: str, edge_ids: Sequence[EdgeId]) -> None:
        store = self._e(investigation_id)
        for edge_id in edge_ids:
            store.pop(edge_id, None)

    async def node_count(self, investigation_id: str) -> int:
        return len(self._n(investigation_id))

    async def edge_count(self, investigation_id: str) -> int:
        return len(self._e(investigation_id))

    async def next_seq(self, investigation_id: str) -> int:
        self._seq[investigation_id] = self._seq.get(investigation_id, 0) + 1
        return self._seq[investigation_id]

    async def current_seq(self, investigation_id: str) -> int:
        return self._seq.get(investigation_id, 0)

    async def append_delta(self, investigation_id: str, delta: WorkingSetDelta) -> None:
        deltas = self._d(investigation_id)
        deltas.append(delta)
        if self.stream_maxlen is not None and len(deltas) > self.stream_maxlen:
            del deltas[: len(deltas) - self.stream_maxlen]

    async def deltas_after(
        self, investigation_id: str, since_seq: int
    ) -> list[WorkingSetDelta] | None:
        current = await self.current_seq(investigation_id)
        if since_seq >= current:
            return []
        # Filter to "after `since_seq`" first, the same way `XRANGE
        # (since_seq-0 +` does against the real stream — only *then* is
        # the first entry's seq meaningful as "the oldest retained entry
        # the client doesn't already have", which is what the gap check
        # below actually needs to compare against.
        after = [d for d in self._d(investigation_id) if d.seq > since_seq]
        if not after or after[0].seq != since_seq + 1:
            return None  # trimmed past what the client last saw
        return after

    async def clear(self, investigation_id: str) -> None:
        self._nodes.pop(investigation_id, None)
        self._edges.pop(investigation_id, None)
        self._seq.pop(investigation_id, None)
        self._deltas.pop(investigation_id, None)
        self._thresholds.pop(investigation_id, None)

    async def get_threshold(self, investigation_id: str) -> float | None:
        return self._thresholds.get(investigation_id)

    async def set_threshold(self, investigation_id: str, tau: float) -> None:
        self._thresholds[investigation_id] = tau


class FakeGraphPort:
    """`expand`/`expand_candidate_count` plus the transaction/`upsert_edges` trio
    `manual_link`/`manual_split` need — the full set `WorkingSetService` actually calls, still no
    real ArcadeDB. Configure `expand_result` and `candidate_count` per test; `expand_requests`
    records every call for assertions like "the same request drove both calls". `committed_edges`
    records every edge a test's `manual_link`/`manual_split` call actually persisted (only after
    `commit_transaction`, never after a `rollback_transaction`), so a test can assert on the write
    without needing a real transactional store."""

    def __init__(self, expand_result: Subgraph, candidate_count: int) -> None:
        self.expand_result = expand_result
        self.candidate_count = candidate_count
        self.expand_requests: list[ExpandRequest] = []
        self.candidate_count_requests: list[ExpandRequest] = []
        self.committed_edges: list[EdgeWrite] = []
        self._pending_edges: dict[TxId, list[EdgeWrite]] = {}
        self._next_tx = 0

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        self.expand_requests.append(req)
        return self.expand_result

    async def expand_candidate_count(self, req: ExpandRequest) -> int:
        self.candidate_count_requests.append(req)
        return self.candidate_count

    async def begin_transaction(self) -> TxId:
        self._next_tx += 1
        tx = f"tx-{self._next_tx}"
        self._pending_edges[tx] = []
        return tx

    async def commit_transaction(self, tx: TxId) -> None:
        self.committed_edges.extend(self._pending_edges.pop(tx))

    async def rollback_transaction(self, tx: TxId) -> None:
        self._pending_edges.pop(tx, None)

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[EdgeId]:
        self._pending_edges[tx].extend(edges)
        return [e.id for e in edges]
