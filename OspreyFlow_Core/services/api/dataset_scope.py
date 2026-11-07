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
first: its source, or a composite's own id (ADR-099 Amendment 14). A write that names its datasets
keeps them. Outside a request (a background job, a script) nothing is stamped, and those writers
name their own.

**The analyst's own writes** (ADR-143 Amendment 1): an entity marked by hand and a manual `SAME_AS`
or `NOT_SAME_AS` name the case's analyst layer, held beside the read set (`analyst_layer`). A case
with no layer yet is given one by the writer, after the route's level check, so they never fall
back to the source; outside a case they are refused (`NoAnalystLayerError`). A branch has a layer
of its own.
Accepted question proposals, accepted extractions and loads name nothing, and so land in the
source as before.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from typing import Any, Protocol

from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ports.graph import BulkGraphLoader, GraphPort
from schemas.domain import (
    EdgeWrite,
    NodeId,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .datasets import COMPOSITE, DatasetStore

_CASE_DATASETS: ContextVar[tuple[str, ...] | None] = ContextVar("case_datasets", default=None)
_CASE_LAYER: ContextVar[str | None] = ContextVar("case_layer", default=None)
#: The request's case, its dataset store and the principal scoped to it: so a writer may make the
#: case's layer when it has none, inside the route after its level check (`analyst_writes_into`),
#: and the stamping graph may tell a composite case's write to a member's node (ADR-099 A15).
_CASE_SCOPE: ContextVar[tuple[str, DatasetStore, Principal] | None] = ContextVar(
    "case_scope", default=None
)


class NoAnalystLayerError(Exception):
    """An analyst's own write with no case's layer to write into: outside a case, or in a case
    that reads nothing. Refused, never written into a source (ADR-143 Amendment 1 item 3)."""


def set_case_datasets(
    datasets: Sequence[str] | None,
    *,
    layer: str | None = None,
    scope: tuple[str, DatasetStore, Principal] | None = None,
) -> None:
    """Called once per request, by `app.get_principal`: the datasets of the request's case, or
    `None` outside a case; the case's analyst layer when it has one in that read set; and the case
    (its id, its store, who asks) for `analyst_writes_into`."""
    _CASE_DATASETS.set(tuple(datasets) if datasets is not None else None)
    _CASE_LAYER.set(layer if datasets is not None and layer in datasets else None)
    _CASE_SCOPE.set(scope if datasets is not None else None)


def case_datasets() -> tuple[str, ...] | None:
    return _CASE_DATASETS.get()


def analyst_layer() -> str | None:
    """The request's case's analyst layer, where the analyst's own writes go (ADR-143 Amendment 1);
    `None` outside a case, or for a case whose layer is not made yet."""
    return _CASE_LAYER.get()


async def analyst_writes_into() -> list[str]:
    """The `datasets` an analyst's own write names (a mark made by hand, a manual link or split):
    the case's layer, never a source (ADR-143 Amendment 1 item 3). A case the migration has not
    reached has none yet; it is made here, by the writer, so only after the route's level check
    has let the caller in, never by `scope_to_case`. Refused with `NoAnalystLayerError` outside a
    case, or in a case that reads nothing: nothing is written then."""
    layer = analyst_layer()
    if layer is not None:
        return [layer]
    scope = _CASE_SCOPE.get()
    held = case_datasets()
    if scope is None or not held:
        raise NoAnalystLayerError("there is no case's analyst layer to write into")
    investigation_id, store, asker = scope
    chosen = await store.chosen_of_case(investigation_id)
    if not chosen:
        raise NoAnalystLayerError("the case reads no dataset")
    # Of the unit of the dataset it reads, as every layer is of its case's unit.
    layer = await store.ensure_layer(
        investigation_id, unit=chosen[0].owning_unit, created_by=asker.id
    )
    set_case_datasets([*held, layer], layer=layer, scope=scope)
    return [layer]


async def scope_to_case(
    principal: Principal, investigation_id: str, store: DatasetStore
) -> Principal:
    """`principal`, reading only the datasets of `investigation_id`. Says nothing about whether the
    principal may open the case: that is the route's own level check, which comes after this, so
    this writes nothing (a case with no layer yet is given one by `analyst_writes_into`)."""
    datasets = await store.ids_of_case(investigation_id)
    layer = await store.layer_of_case(investigation_id) if datasets else None
    scoped = principal.model_copy(update={"datasets": datasets})
    set_case_datasets(datasets, layer=layer, scope=(investigation_id, store, scoped))
    return scoped


class _CasesOf(Protocol):
    async def list_for(self, principal: Principal) -> Sequence[tuple[Any, Any]]: ...


async def scope_to_dataset(
    principal: Principal, dataset_id: str, cases: _CasesOf, store: DatasetStore
) -> Principal | None:
    """`principal`, reading `dataset_id` alone, when one of the cases it holds a level in loads into
    that dataset (the case's first, ADR-099 decision 6; a composite's own id, Amendment 14);
    otherwise `None`. The reach is exactly the Studio's dataset switcher's (ADR-140 Amendment 2): a
    dataset a case of theirs only reads, and another unit's, are not reached. Writes made through it
    are stamped with the dataset."""
    for case, _level in await cases.list_for(principal):
        ids = await store.ids_of_case(case.id)
        if ids and ids[0] == dataset_id:
            set_case_datasets([dataset_id])
            return principal.model_copy(update={"datasets": [dataset_id]})
    return None


def reach_clause(principal: Principal, position: int) -> tuple[str, list[object]]:
    """ADR-099 Amendment 3, for a Postgres store of things made in a case (a saved pattern, a
    watch, an alert): the SQL that keeps a read to the case's datasets, as `AND (...)` with its
    parameter at `$position`. A record made before the amendment names no dataset and stays in
    reach until `scripts.stamp_datasets` places it; the Conduit's own unlimited work reads all."""
    if principal.datasets is None:
        return "", []
    return (
        f" AND (dataset_id = ANY(${position}::text[]) OR dataset_id IS NULL)",
        [list(principal.datasets)],
    )


def made_in(principal: Principal) -> str | None:
    """The dataset a record made by `principal` now belongs to: the first of its case's."""
    return principal.datasets[0] if principal.datasets else None


def outside_any_case(principal: Principal) -> Principal:
    set_case_datasets(None)
    return principal.model_copy(update={"datasets": []})


def _stamp_nodes(nodes: Sequence[NodeWrite], into: str | None) -> list[NodeWrite]:
    if into is None:
        return list(nodes)
    return [n if n.datasets else n.model_copy(update={"datasets": [into]}) for n in nodes]


def _stamp_edges(edges: Sequence[EdgeWrite], into: str | None) -> list[EdgeWrite]:
    if into is None:
        return list(edges)
    return [e if e.datasets else e.model_copy(update={"datasets": [into]}) for e in edges]


class UnknownDatasetError(Exception):
    """A write names a dataset the registry does not hold (ADR-099 Amendment 6). Nothing of that
    write reaches the store: an element in an unregistered dataset is in no case's world, ever."""

    def __init__(self, dataset_ids: Sequence[str]) -> None:
        self.dataset_ids = sorted(set(dataset_ids))
        super().__init__("no such dataset: " + ", ".join(self.dataset_ids))


class DatasetRegistry(Protocol):
    """What the stamping graph asks of the dataset store: which of these ids it holds."""

    async def known(self, dataset_ids: Sequence[str]) -> set[str]: ...


def _named(writes: Sequence[NodeWrite] | Sequence[EdgeWrite]) -> set[str]:
    return {d for w in writes for d in w.datasets}


class DatasetStampingGraph:
    """The Conduit's `GraphPort`: the adapter itself, with the request's case stamped on every
    write that names no dataset. Every other call goes to the adapter unchanged, and a capability
    the adapter lacks (`BulkGraphLoader`) is lacking here too.

    `dataset`, when given, is stamped instead of the request's case: a seed or a script, which runs
    outside any request, names the one dataset everything it writes belongs to."""

    def __init__(
        self,
        inner: GraphPort,
        *,
        dataset: str | None = None,
        registry: DatasetRegistry | None = None,
    ) -> None:
        self._inner = inner
        self._dataset = dataset
        self._registry = registry
        #: Ids the registry has confirmed. A dataset is never deleted, so a confirmation holds.
        self._confirmed: set[str] = set()
        #: Called after every write the store accepted (ADR-100 Amendment 3: kept figures cleared).
        self._after_write: list[Callable[[], Awaitable[None]]] = []

    def after_write(self, hook: Callable[[], Awaitable[None]]) -> None:
        self._after_write.append(hook)

    async def _written(self) -> None:
        for hook in self._after_write:
            await hook()

    def check_against(self, registry: DatasetRegistry) -> None:
        """Every later write is checked against `registry` (the Conduit's dataset store, which
        exists only after the graph is built)."""
        self._registry = registry

    async def _checked(self, writes: Sequence[Any]) -> None:
        if self._registry is None:
            return
        wanted = _named(writes) - self._confirmed
        if not wanted:
            return
        held = await self._registry.known(sorted(wanted))
        self._confirmed |= held
        if missing := wanted - held:
            raise UnknownDatasetError(sorted(missing))

    def _into(self) -> str | None:
        if self._dataset is not None:
            return self._dataset
        held = case_datasets()
        return held[0] if held else None

    @property
    def inner(self) -> GraphPort:
        return self._inner

    def __getattr__(self, name: str) -> Any:
        if name == "bulk_load_edges":  # only `BulkDatasetStampingGraph` has it: see `stamping`
            raise AttributeError(name)
        return getattr(self._inner, name)

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: Any) -> list[NodeId]:
        stamped = _stamp_nodes(nodes, self._into())
        stamped, kept = await self._kept_from_members(stamped)
        await self._checked(stamped)
        ids = await self._inner.upsert_nodes(stamped, tx)
        if kept:
            await self._inner.upsert_edges(kept, tx)
        await self._written()
        return ids

    async def _kept_from_members(
        self, writes: list[NodeWrite]
    ) -> tuple[list[NodeWrite], list[EdgeWrite]]:
        """ADR-099 Amendment 15: under a case reading a composite, a write into the composite that
        names a node already in one of its members becomes a new node in the composite, linked to
        the member's node by a `SAME_AS`; the member's node is not written (rule 6), so no case
        reading only the member sees the change. Asked as the request's own principal (the
        composite and its members, its handling), so the answer tells it nothing it cannot read.
        Outside a request, or a case reading a source, nothing changes."""
        scope = _CASE_SCOPE.get()
        if self._dataset is not None or scope is None or not writes:
            return writes, []
        investigation_id, store, principal = scope
        chosen = await store.chosen_of_case(investigation_id)
        if len(chosen) != 1 or chosen[0].kind != COMPOSITE:
            return writes, []
        composite, members = chosen[0].id, set(chosen[0].members)
        into_composite = [w.id for w in writes if composite in w.datasets]
        if not into_composite:
            return writes, []
        held = await self._inner.get_nodes(into_composite, principal)
        in_a_member = {n.id for n in held if set(n.datasets) & members}
        if not in_a_member:
            return writes, []
        out: list[NodeWrite] = []
        links: list[EdgeWrite] = []
        for write in writes:
            if write.id not in in_a_member:
                out.append(write)
                continue
            fresh = write.model_copy(update={"id": new_node_id(), "datasets": [composite]})
            out.append(fresh)
            links.append(
                EdgeWrite(
                    id=new_edge_id(),
                    type="SAME_AS",
                    source=fresh.id,
                    target=write.id,
                    properties={"score": 1.0},
                    provenance=Provenance(
                        state=ProvenanceState.ASSERTED,
                        sources=[
                            SourceRef(
                                document_id=f"composite:{composite}:{write.id}",
                                locator=write.created_by,
                                excerpt_hash="",
                            )
                        ],
                        first_seen=now_utc(),
                    ),
                    handling=write.handling,
                    created_by=write.created_by,
                    created_at=write.created_at,
                    datasets=[composite],
                )
            )
        return out, links

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: Any) -> list[str]:
        stamped = _stamp_edges(edges, self._into())
        await self._checked(stamped)
        ids = await self._inner.upsert_edges(stamped, tx)
        await self._written()
        return ids

    # A correction or a revert changes what is counted too; each clears what was kept after it.
    async def supersede_node(self, node_id: NodeId, replacement: NodeWrite, tx: Any) -> NodeId:
        new_id = await self._inner.supersede_node(node_id, replacement, tx)
        await self._written()
        return new_id

    async def supersede_edge(self, edge_id: str, replacement: EdgeWrite, tx: Any) -> str:
        new_id = await self._inner.supersede_edge(edge_id, replacement, tx)
        await self._written()
        return new_id

    async def revert_elements(
        self, node_ids: Sequence[NodeId], edge_ids: Sequence[str], tx: Any
    ) -> None:
        await self._inner.revert_elements(node_ids, edge_ids, tx)
        await self._written()

    async def withdraw_elements(
        self, node_ids: Sequence[NodeId], edge_ids: Sequence[str], load_id: str, tx: Any
    ) -> None:
        await self._inner.withdraw_elements(node_ids, edge_ids, load_id, tx)
        await self._written()

    async def restore_withdrawn(self, load_id: str, tx: Any) -> Any:
        restored = await self._inner.restore_withdrawn(load_id, tx)
        await self._written()
        return restored

    async def strip_provenance_references(self, prefix: str) -> int:
        changed: int = await self._inner.strip_provenance_references(prefix)
        await self._written()
        return changed


class BulkDatasetStampingGraph(DatasetStampingGraph):
    """The same, over an adapter that is a `BulkGraphLoader`, and so one itself. The method is
    declared here, not passed on by `__getattr__`: Python's runtime protocol check looks attributes
    up statically, so a passed-on method does not make the wrapper a `BulkGraphLoader`, and the
    Enron seed, asking that question, refused to write after deleting its links (7 October 2026)."""

    async def bulk_load_edges(self, edges: Sequence[EdgeWrite], **kwargs: Any) -> Any:
        inner: Any = self.inner
        stamped = _stamp_edges(edges, self._into())
        await self._checked(stamped)
        result = await inner.bulk_load_edges(stamped, **kwargs)
        await self._written()
        return result


def stamping(
    inner: GraphPort, *, dataset: str | None = None, registry: DatasetRegistry | None = None
) -> DatasetStampingGraph:
    """The stamping graph over `inner`: a `BulkGraphLoader` exactly when `inner` is one. With a
    `registry`, every write's datasets are checked against it first."""
    if isinstance(inner, BulkGraphLoader):
        return BulkDatasetStampingGraph(inner, dataset=dataset, registry=registry)
    return DatasetStampingGraph(inner, dataset=dataset, registry=registry)


__all__: Sequence[str] = (
    "BulkDatasetStampingGraph",
    "DatasetRegistry",
    "UnknownDatasetError",
    "DatasetStampingGraph",
    "stamping",
    "case_datasets",
    "outside_any_case",
    "scope_to_case",
    "analyst_layer",
    "analyst_writes_into",
    "NoAnalystLayerError",
    "set_case_datasets",
)
