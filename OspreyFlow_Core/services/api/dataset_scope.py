"""What a request may read, and what it writes into (`06_DECISIONS.md` ADR-099 decisions 4 to 6).

**Reads.** `app.get_principal` scopes every request's principal: to the datasets of the case its
path names (`/v1/investigations/{investigation_id}/...`), and to none for any other path, so a read
outside a case sees nothing (default-deny). A route that names its case elsewhere (an analytics
body, an alert's own case) scopes explicitly with `scope_to_case`. Only the Conduit's own
background work reads unlimited (`Principal.datasets is None`); no request handler is given that
principal. The limit itself is applied in the graph adapter (`AccessFilter`) and, for bodies the
working set already holds, by `ontology.handling.principal_may_read`.

**Writes.** Everything the Conduit writes for a case (a marked entity, an accepted finding, a file
added, a Studio load run from the case) must belong to one of the case's datasets, or it would
vanish from the case as it is written. Rather than ask every write path to remember, the request's
case is held in a context variable when its principal is scoped, and `DatasetStampingGraph`, the
graph the Conduit's services are given, stamps any write that names no dataset with the case's
first. A write that names its datasets keeps them. Outside a request (a background job, a script)
nothing is stamped, and those writers name their own.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextvars import ContextVar
from typing import Any

from ports.graph import GraphPort
from schemas.domain import EdgeWrite, NodeId, NodeWrite, Principal

from .datasets import DatasetStore

_CASE_DATASETS: ContextVar[tuple[str, ...] | None] = ContextVar("case_datasets", default=None)


def set_case_datasets(datasets: Sequence[str] | None) -> None:
    """Called once per request, by `app.get_principal`: the datasets of the request's case, or
    `None` outside a case."""
    _CASE_DATASETS.set(tuple(datasets) if datasets is not None else None)


def case_datasets() -> tuple[str, ...] | None:
    return _CASE_DATASETS.get()


async def scope_to_case(
    principal: Principal, investigation_id: str, store: DatasetStore
) -> Principal:
    """`principal`, reading only the datasets of `investigation_id`. Says nothing about whether the
    principal may open the case: that is the route's own level check."""
    datasets = await store.ids_of_case(investigation_id)
    set_case_datasets(datasets)
    return principal.model_copy(update={"datasets": datasets})


def outside_any_case(principal: Principal) -> Principal:
    set_case_datasets(None)
    return principal.model_copy(update={"datasets": []})


def _stamp_nodes(nodes: Sequence[NodeWrite]) -> list[NodeWrite]:
    held = case_datasets()
    if not held:
        return list(nodes)
    return [n if n.datasets else n.model_copy(update={"datasets": [held[0]]}) for n in nodes]


def _stamp_edges(edges: Sequence[EdgeWrite]) -> list[EdgeWrite]:
    held = case_datasets()
    if not held:
        return list(edges)
    return [e if e.datasets else e.model_copy(update={"datasets": [held[0]]}) for e in edges]


class DatasetStampingGraph:
    """The Conduit's `GraphPort`: the adapter itself, with the request's case stamped on every
    write that names no dataset. Every other call goes to the adapter unchanged, and a capability
    the adapter lacks (`BulkGraphLoader`) is lacking here too."""

    def __init__(self, inner: GraphPort) -> None:
        self._inner = inner

    @property
    def inner(self) -> GraphPort:
        return self._inner

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._inner, name)
        if name == "bulk_load_edges":

            async def bulk_load_edges(edges: Sequence[EdgeWrite], **kwargs: Any) -> Any:
                return await attribute(_stamp_edges(edges), **kwargs)

            return bulk_load_edges
        return attribute

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: Any) -> list[NodeId]:
        return await self._inner.upsert_nodes(_stamp_nodes(nodes), tx)

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: Any) -> list[str]:
        return await self._inner.upsert_edges(_stamp_edges(edges), tx)


__all__: Sequence[str] = (
    "DatasetStampingGraph",
    "case_datasets",
    "outside_any_case",
    "scope_to_case",
    "set_case_datasets",
)
