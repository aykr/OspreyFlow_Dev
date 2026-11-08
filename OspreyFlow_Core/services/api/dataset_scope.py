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
first, its source. A write that names its datasets keeps them. Outside a request (a background
job, a script) nothing is stamped, and those writers name their own.

**A composite is read-only for now** (ADR-099 Amendments 14 and 15; the owner, 7 November 2026).
A case reading a composite reads its members and keeps its own analyst layer; every other write in
it, and every write into a composite's id, is refused in words (`CompositeReadOnlyError`): by each
writing service after its own read of what it would change (so what the reader cannot see answers
as not found), by a route dependency for the case's and the Studio's loading routes, and by
`DatasetStampingGraph` as the last word.

**The analyst's own writes** (ADR-143 Amendment 1): an entity marked by hand and a manual `SAME_AS`
or `NOT_SAME_AS` name the case's analyst layer, held beside the read set (`analyst_layer`). A case
with no layer yet is given one by the writer, after the route's level check, so they never fall
back to the source; outside a case they are refused (`NoAnalystLayerError`). A branch holds no
layer of its own: it reads its original case's, read-only, and only for a reader holding a level on
the original; every write into it is refused (`BranchLayerError`, ADR-144 Amendment 1 decision 2).
A case opened from an alert keeps an empty layer of its own. An alert resting on a case's layer is
written into that layer (`rule_evaluation._alert_datasets`).
Accepted question proposals, accepted extractions and loads name nothing, and so land in the
source as before.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from typing import Any, Protocol

from ports.graph import BulkGraphLoader, GraphPort
from schemas.domain import (
    Edge,
    EdgeWrite,
    Node,
    NodeId,
    NodeWrite,
    Principal,
    TxId,
)
from schemas.ingest import LinkPriorState

from .datasets import COMPOSITE, BranchLayerError, Dataset, DatasetStore, reads_dataset_names

_CASE_DATASETS: ContextVar[tuple[str, ...] | None] = ContextVar("case_datasets", default=None)
_CASE_LAYER: ContextVar[str | None] = ContextVar("case_layer", default=None)
#: A branch's original case's layer, which the branch reads and never writes (ADR-144 Amendment 1
#: decision 2): set by `scope_to_case`, judged by the stamping graph's last word.
_READ_ONLY_LAYER: ContextVar[str | None] = ContextVar("read_only_layer", default=None)
#: The request's case, its dataset store and the principal scoped to it: so a writer may make the
#: case's layer when it has none, inside the route after its level check (`analyst_writes_into`),
#: and a write may be refused in a case reading a composite (`refuse_in_a_composite_case`).
_CASE_SCOPE: ContextVar[tuple[str, DatasetStore, Principal] | None] = ContextVar(
    "case_scope", default=None
)


class CompositeReadOnlyError(Exception):
    """ADR-099 Amendments 14 and 15 (the owner, 7 November 2026): a write, other than into the
    case's own analyst layer, in a case reading a composite, or any write into a composite's id.
    Refused before anything is written; a composite is read-only for now."""

    def __init__(self, composite: str | None = None, *, in_a_case: bool = True) -> None:
        #: `composite`: its name, where the asker may be told dataset names (ADR-099 Amendment 11,
        #: `reads_dataset_names`); otherwise none is named. `in_a_case`: false for a write into a
        #: composite's id with no case (the Studio's routes of a dataset, a schedule's).
        named = f"the composite “{composite}”" if composite else "a composite"
        said = f"This case reads {named}" if in_a_case else f"This is {named}"
        super().__init__(
            f"{said}, which is read-only for now: do this in a case that reads that dataset."
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
    _READ_ONLY_LAYER.set(None)


def case_datasets() -> tuple[str, ...] | None:
    return _CASE_DATASETS.get()


def analyst_layer() -> str | None:
    """The request's case's analyst layer, where the analyst's own writes go (ADR-143 Amendment 1);
    `None` outside a case, or for a case whose layer is not made yet."""
    return _CASE_LAYER.get()


def read_only_layer() -> str | None:
    """The original case's layer a branch reads, read-only (ADR-144 Amendment 1 decision 2); `None`
    outside a branch. Set for every reader of the branch, so a write into it is refused for each,
    though only a reader holding a level on the original reads it (`scope_to_case`)."""
    return _READ_ONLY_LAYER.get()


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
    if _READ_ONLY_LAYER.get() is not None:
        raise BranchLayerError  # a branch writes into no layer (ADR-144 Amendment 1 decision 2)
    chosen = await store.chosen_of_case(investigation_id)
    if not chosen:
        raise NoAnalystLayerError("the case reads no dataset")
    # Of the unit of the dataset it reads, as every layer is of its case's unit.
    layer = await store.ensure_layer(
        investigation_id, unit=chosen[0].owning_unit, created_by=asker.id
    )
    # Not `set_case_datasets`, which would forget the case's scope.
    _CASE_DATASETS.set((*held, layer))
    _CASE_LAYER.set(layer)
    return [layer]


def with_the_layer(principal: Principal) -> Principal:
    """`principal` reading its case's read set as it now stands: after `analyst_writes_into` has
    made the case's layer mid-request, so the rest of the request reads what it has just written."""
    held = case_datasets()
    if held is None or principal.datasets is None or list(held) == list(principal.datasets):
        return principal
    return principal.model_copy(update={"datasets": list(held)})


async def _composite_read() -> Dataset | None:
    """The composite the request's case reads, if it reads one (ADR-099 Amendment 12)."""
    scope = _CASE_SCOPE.get()
    if scope is None:
        return None
    chosen = await scope[1].chosen_of_case(scope[0])
    return chosen[0] if len(chosen) == 1 and chosen[0].kind == COMPOSITE else None


async def reads_a_composite() -> bool:
    """Whether the request's case reads a composite (ADR-099 Amendment 12)."""
    return await _composite_read() is not None


def _refusal(composite: Dataset) -> CompositeReadOnlyError:
    """The refusal, naming the composite to an asker who may be told dataset names."""
    scope = _CASE_SCOPE.get()
    named = scope is not None and reads_dataset_names(scope[2])
    return CompositeReadOnlyError(composite.name if named else None)


async def refuse_in_a_composite_case() -> None:
    """ADR-099 Amendment 15: every write in a case reading a composite, other than into the case's
    own analyst layer, is refused. A writing service calls this after its own read of what it would
    change, so what the reader cannot see still answers as not found, and before it writes or
    stores anything."""
    composite = await _composite_read()
    if composite is not None:
        raise _refusal(composite)


async def refuse_unless_in_the_layer(elements: Sequence[Node | Edge]) -> None:
    """`refuse_in_a_composite_case` for a write that changes elements already read: it goes ahead
    in a composite case only when each is wholly the case's layer's (an alert's own node and its
    `SAME_AS`, written there, ADR-099 Amendment 15 item 2), as the stamping graph's last word
    would judge it; any other is refused before anything is written."""
    composite = await _composite_read()
    if composite is None:
        return
    layer = analyst_layer()
    if layer is None or any(set(e.datasets) != {layer} for e in elements):
        raise _refusal(composite)


async def refuse_writing_a_node_in_a_composite_case(
    graph: GraphPort, node_id: NodeId, principal: Principal
) -> None:
    """`refuse_in_a_composite_case` for a route correcting a node by id: only once the node is read
    as `principal`; one it cannot read is left to the writer, which answers it as not found. Even a
    node wholly in the case's layer: a correction repoints every link incident to the node
    (`GraphPort.supersede_node`), and a link the case cannot read cannot be judged from here. The
    close of an alert raised in the case is the one correction allowed, its node's only links its
    own `ALERTED_ON` (`refuse_unless_in_the_layer`)."""
    if await graph.get_nodes([node_id], principal):
        await refuse_in_a_composite_case()


#: Whether a principal holds any level on a case (its Viewer check, answered as a yes or no).
HoldsALevel = Callable[[Principal, str], Awaitable[bool]]


async def scope_to_case(
    principal: Principal,
    investigation_id: str,
    store: DatasetStore,
    *,
    holds_a_level: HoldsALevel | None = None,
) -> Principal:
    """`principal`, reading only the datasets of `investigation_id`. Says nothing about whether the
    principal may open the case: that is the route's own level check, which comes after this, so
    this writes nothing (a case with no layer yet is given one by `analyst_writes_into`).

    In a branch, the original case's layer is read only by a reader who holds a level on the
    original (`holds_a_level`; the orchestrator's call of 7 November 2026, on rule 3, as for the
    alert jump): a member of the branch alone reads no layer, and with no check to ask, no one
    does. Either way nothing is written into it (`BranchLayerError`)."""
    datasets = await store.ids_of_case(investigation_id)
    layer = await store.layer_of_case(investigation_id) if datasets else None
    borrowed = await store.read_only_layer_of(investigation_id) if datasets and not layer else None
    if borrowed is not None and borrowed in datasets:
        original = await store.case_of_layer(borrowed)
        if (
            holds_a_level is None
            or original is None
            or not await holds_a_level(principal, original)
        ):
            datasets = [d for d in datasets if d != borrowed]
    scoped = principal.model_copy(update={"datasets": datasets})
    set_case_datasets(datasets, layer=layer, scope=(investigation_id, store, scoped))
    if borrowed is not None:
        _READ_ONLY_LAYER.set(borrowed)  # refused as a write for every reader of the branch
    return scoped


async def scope_a_monitor(
    deployer: Principal, investigation_id: str, rule_dataset: str | None, store: DatasetStore
) -> Principal:
    """A monitor's deployer for one run outside any request (a re-screening, the daily sweep),
    scoped to the rule's case as a request is, so what it writes is judged as a request's would be.
    Decided by what the case reads, never by the dataset the rule names: in a case reading a
    composite it reads the case and its alert goes into the case's layer (ADR-099 Amendment 15 item
    2), whichever dataset the rule was made naming (a member's, from before the case read a
    composite, or the composite's own id). In any other case, a rule naming a source of its own
    reads that source alone, as before."""
    scoped = await scope_to_case(deployer, investigation_id, store)
    if await reads_a_composite() or not rule_dataset:
        return scoped
    if await store.composites_among([rule_dataset]):
        return scoped
    set_case_datasets([rule_dataset])
    return deployer.model_copy(update={"datasets": [rule_dataset]})


class _CasesOf(Protocol):
    async def list_for(self, principal: Principal) -> Sequence[tuple[Any, Any]]: ...


async def scope_to_dataset(
    principal: Principal, dataset_id: str, cases: _CasesOf, store: DatasetStore
) -> Principal | None:
    """`principal`, reading `dataset_id` alone, when one of the cases it holds a level in loads into
    that dataset (the case's first, ADR-099 decision 6; a composite's own id, Amendment 14);
    otherwise `None`. The reach is exactly the Studio's dataset switcher's (ADR-140 Amendment 2): a
    dataset a case of theirs only reads, and another unit's, are not reached. Writes made through it
    are stamped with the dataset, and refused when it is a composite (Amendment 15)."""
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
    """What the stamping graph asks of the dataset store: which of these ids it holds, and which are
    composites (read-only for now, ADR-099 Amendment 15)."""

    async def known(self, dataset_ids: Sequence[str]) -> set[str]: ...
    async def composites_among(self, dataset_ids: Sequence[str]) -> set[str]: ...


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

    async def _refuse_loading_here(self) -> None:
        """A load's revert, withdrawal or restore in a case reading a composite, or in a composite
        the Studio reached, is a write into it: refused (ADR-099 Amendment 15)."""
        into = self._into()
        await self._refuse_into_a_composite({into} if into else set())

    @property
    def inner(self) -> GraphPort:
        return self._inner

    def __getattr__(self, name: str) -> Any:
        if name == "bulk_load_edges":  # only `BulkDatasetStampingGraph` has it: see `stamping`
            raise AttributeError(name)
        if name == "restore_link_state":  # a write: declared above, with its guard, or absent
            raise AttributeError(name)
        return getattr(self._inner, name)

    async def _refuse_into_a_read_only_layer(self, datasets: set[str]) -> None:
        """The last word on ADR-144 Amendment 1 decision 2: a branch reads its original case's
        layer and writes nothing into it, a correction of what is in it included."""
        read_only = _READ_ONLY_LAYER.get()
        if read_only is not None and read_only in datasets:
            raise BranchLayerError

    async def _refuse_into_a_composite(self, datasets: set[str]) -> None:
        """The last word on ADR-099 Amendment 15: in a case reading a composite, only a write wholly
        into the case's own analyst layer goes ahead; and no write names a composite's id, under a
        case or not (the Studio reaches a dataset with no case). Before anything is written."""
        if self._dataset is not None:
            return
        await self._refuse_into_a_read_only_layer(datasets)
        layer = analyst_layer()
        composite = await _composite_read()
        if composite is not None and (not datasets or datasets != {layer}):
            raise _refusal(composite)
        if self._registry is not None and datasets:
            if await self._registry.composites_among(sorted(datasets)):
                raise CompositeReadOnlyError(in_a_case=False)

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: Any) -> list[NodeId]:
        stamped = _stamp_nodes(nodes, self._into())
        await self._refuse_into_a_composite(_named(stamped))
        await self._checked(stamped)
        ids = await self._inner.upsert_nodes(stamped, tx)
        await self._written()
        return ids

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: Any) -> list[str]:
        stamped = _stamp_edges(edges, self._into())
        await self._refuse_into_a_composite(_named(stamped))
        await self._checked(stamped)
        ids = await self._inner.upsert_edges(stamped, tx)
        await self._written()
        return ids

    async def _refuse_correcting(
        self, held: Sequence[Node] | Sequence[Edge], replacement: Sequence[str]
    ) -> None:
        """A correction keeps the old element's datasets (Amendment 2 decision 2), so it is judged
        by them and by what the replacement names. In a case reading a composite it goes ahead only
        for an old element the case can see and that is wholly the case's layer's; one it cannot
        see is refused in the same words, which says nothing, since every other correction there is
        refused too. Under no case's scope (the Studio's, `scope_to_dataset`), the dataset it is
        made in and what the replacement names are still asked of the registry: no composite's."""
        if self._dataset is not None:
            return
        named = set(replacement)
        if await reads_a_composite():
            if not held:
                await refuse_in_a_composite_case()
            for old in held:
                await self._refuse_into_a_composite(set(old.datasets) | named)
            return
        into = self._into()
        await self._refuse_into_a_composite(
            named | ({into} if into else set()) | {d for old in held for d in old.datasets}
        )

    async def _held_for(self, read: Callable[[Principal], Awaitable[Any]]) -> list[Any]:
        """The old element, as the request's case reads it; nothing outside a case."""
        scope = _CASE_SCOPE.get()
        if scope is None or self._dataset is not None:
            return []
        return list(await read(scope[2]))

    # A correction or a revert changes what is counted too; each clears what was kept after it.
    async def supersede_node(self, node_id: NodeId, replacement: NodeWrite, tx: Any) -> NodeId:
        held = await self._held_for(lambda reader: self._inner.get_nodes([node_id], reader))
        await self._refuse_correcting(held, replacement.datasets)
        new_id = await self._inner.supersede_node(node_id, replacement, tx)
        await self._written()
        return new_id

    async def supersede_edge(self, edge_id: str, replacement: EdgeWrite, tx: Any) -> str:
        held = await self._held_for(lambda reader: self._inner.get_edges([edge_id], reader))
        await self._refuse_correcting(held, replacement.datasets)
        new_id = await self._inner.supersede_edge(edge_id, replacement, tx)
        await self._written()
        return new_id

    async def revert_elements(
        self, node_ids: Sequence[NodeId], edge_ids: Sequence[str], tx: Any
    ) -> None:
        await self._refuse_loading_here()
        await self._inner.revert_elements(node_ids, edge_ids, tx)
        await self._written()

    async def withdraw_elements(
        self, node_ids: Sequence[NodeId], edge_ids: Sequence[str], load_id: str, tx: Any
    ) -> None:
        await self._refuse_loading_here()
        await self._inner.withdraw_elements(node_ids, edge_ids, load_id, tx)
        await self._written()

    async def restore_withdrawn(self, load_id: str, tx: Any) -> Any:
        await self._refuse_loading_here()
        restored = await self._inner.restore_withdrawn(load_id, tx)
        await self._written()
        return restored

    async def strip_provenance_references(self, prefix: str) -> int:
        changed: int = await self._inner.strip_provenance_references(prefix)
        await self._written()
        return changed

    async def restore_link_state(self, state: LinkPriorState, tx: TxId) -> bool:
        """ADR-110 Amendment 16: a load's revert writing, so refused in a case reading a composite
        (ADR-099 Amendment 15), as the revert's other writes are; and the kept figures are cleared
        after it. It names no dataset of its own: the link keeps the datasets its prior state
        holds. Declared here, never passed on by `__getattr__`, which refuses the name."""
        await self._refuse_loading_here()
        restored = await self._inner.restore_link_state(state, tx)
        await self._written()
        return restored


class BulkDatasetStampingGraph(DatasetStampingGraph):
    """The same, over an adapter that is a `BulkGraphLoader`, and so one itself. The method is
    declared here, not passed on by `__getattr__`: Python's runtime protocol check looks attributes
    up statically, so a passed-on method does not make the wrapper a `BulkGraphLoader`, and the
    Enron seed, asking that question, refused to write after deleting its links (7 October 2026)."""

    async def bulk_load_edges(self, edges: Sequence[EdgeWrite], **kwargs: Any) -> Any:
        inner: Any = self.inner
        stamped = _stamp_edges(edges, self._into())
        await self._refuse_into_a_composite(_named(stamped))
        await self._checked(stamped)
        result = await inner.bulk_load_edges(stamped, **kwargs)
        await self._written()
        return result


def stamping(
    inner: GraphPort,
    *,
    dataset: str | None = None,
    registry: DatasetRegistry | None = None,
) -> DatasetStampingGraph:
    """The stamping graph over `inner`: a `BulkGraphLoader` exactly when `inner` is one. With a
    `registry`, every write's datasets are checked against it first, a composite's refused."""
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
    "scope_a_monitor",
    "analyst_layer",
    "analyst_writes_into",
    "with_the_layer",
    "CompositeReadOnlyError",
    "reads_a_composite",
    "refuse_in_a_composite_case",
    "refuse_unless_in_the_layer",
    "refuse_writing_a_node_in_a_composite_case",
    "NoAnalystLayerError",
    "HoldsALevel",
    "read_only_layer",
    "set_case_datasets",
)
