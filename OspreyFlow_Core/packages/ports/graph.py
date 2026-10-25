"""`GraphPort` — `spec/00_ARCHITECTURE.md` §2.1.

Persistent property graph: write, traverse, subgraph extraction, schema
management. Gremlin/TinkerPop 3.8 is the query language; the transport is
each adapter's own business (WebSocket/GraphBinary or an HTTP command
endpoint are both conformant). Gremlin never leaves the Vault — nothing
above this port may see it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from schemas.compute import LinkStructure
from schemas.domain import (
    Edge,
    EdgeId,
    EdgeWrite,
    ExpandRequest,
    ListNodesPage,
    NeighbourhoodStats,
    Node,
    NodeId,
    NodeWrite,
    OntologySchema,
    Path,
    PathRequest,
    PatternQuery,
    Principal,
    RoutesAtLength,
    SchemaReport,
    Subgraph,
    TxId,
)
from schemas.explore import (
    RankedLinks,
    RankedNodes,
    RecentLoads,
    RecentlyConfirmed,
    SharedContacts,
    TypeCounts,
)


class SubgraphTooLarge(Exception):
    """`GraphPort.vault_subgraph` would return more than the caller's cap. The counts are of what
    the principal can *see*: reporting what exists would disclose what is hidden (`CLAUDE.md`
    rule 3). `edges` is `None` when the node count alone already breached and edges were not
    counted."""

    def __init__(self, *, nodes: int, edges: int | None) -> None:
        super().__init__(f"{nodes} visible nodes, {edges} visible edges")
        self.nodes = nodes
        self.edges = edges


@dataclass(frozen=True)
class StoredNode:
    """What `GraphPort.stored_writes` says of one node: the load that last wrote it (`None` for a
    write outside a load, a Files-tab upload for one) and whether it is reverted."""

    load_id: str | None
    reverted: bool


class AmbiguousElementId(Exception):
    """`GraphPort.revert_elements` was given an id that two stored types of one kind both hold.
    Ids are unique per type, not across the store, and a load's record keeps no types, so the call
    cannot tell which element it meant; it is refused whole and changes nothing."""

    def __init__(self, kind: str, count: int) -> None:
        super().__init__(f"{count} {kind} id(s) are held by more than one stored type")
        self.kind = kind
        self.count = count


class GraphPort(Protocol):
    #: Query dialects this adapter can render — `{"gremlin"}`,
    #: `{"gremlin", "opencypher"}`, `{"gql"}` — ADR-003's amendment. The
    #: Conduit selects a builder backend from what the configured adapter
    #: advertises; the conformance suite is parametrised by dialect.
    dialects: frozenset[str]

    # Transaction lifecycle. `upsert_nodes`/`upsert_edges` take a `TxId`
    # produced by `begin_transaction`; nothing is durable until
    # `commit_transaction`, and `rollback_transaction` discards every write
    # made under it — the conformance suite's transaction-rollback case
    # exercises exactly this.
    async def begin_transaction(self) -> TxId: ...
    async def commit_transaction(self, tx: TxId) -> None: ...
    async def rollback_transaction(self, tx: TxId) -> None: ...

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: TxId) -> list[NodeId]: ...
    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[EdgeId]: ...

    async def get_node(
        self, node_id: NodeId, principal: Principal, *, include_superseded: bool = False
    ) -> Node | None:
        """`include_superseded=True` is the one way to retrieve a node
        `supersede_node` has replaced — otherwise excluded from every read
        by default (`01_DOMAIN_MODEL.md` §2.4). It only lifts *that*
        exclusion: classification and `handling_code` still apply
        underneath, so a principal who could not see the record cannot see
        its history either."""
        ...

    async def get_nodes(self, node_ids: Sequence[NodeId], principal: Principal) -> list[Node]:
        """ADR-124 decision 6: the given ids looked up alone, with no traversal and no neighbour
        read: resolved through each stored type's unique `id` index, then read through the access
        step, per 1,000 ids (ADR-124 Amendment 2). Access-filtered in the adapter (rule 3), by the
        same step as every other read: `principal`'s clearance, a restricted `handling_code`, the
        case's datasets, and the structural exclusion of a reverted or superseded node. A hidden,
        superseded, reverted or absent id is left out identically: nothing in the result, and no
        error, says which. Each node comes back once however often its id is given, ordered by id.
        No ids give `[]`. `node_ids` is a sequence of ids: a bare `str` is a `TypeError`, since it
        is a sequence of characters and would be read as one-character ids."""
        ...

    async def existing_node_ids(self, node_ids: Sequence[NodeId]) -> set[NodeId]:
        """ADR-127 decision 6. Which of `node_ids` name a node already in the store, **whatever the
        caller may read**: no principal, no access step. For the recipe engine's write path alone,
        to tell a node an upsert merges into from one it creates (a content `Document`'s id is the
        hash of its bytes, so the same text from another load, holder or upload names the same
        node). It answers what `upsert_nodes` would do: a write to a superseded node's id merges
        into it, so it is named; a write to a reverted node's id is a fresh create (ADR-127
        Amendment 6), so a reverted node is not, unless it is also superseded: it stays superseded,
        a write merges, and it is named. A
        route must never call it, or any caller could ask whether an id exists
        (`tests/test_unfiltered_node_lookup_confined.py`). Each id once however often given; no ids
        give the empty set; a bare `str` is a `TypeError`, as for `get_nodes`."""
        ...

    async def get_edges(self, edge_ids: Sequence[EdgeId], principal: Principal) -> list[Edge]:
        """`get_nodes`, for links. A link comes back only when the link *and both its ends* pass
        the access step (rule 3): a readable link to a hidden end is left out as a hidden link is,
        so the result for a list is the result for the list without those ids. A superseded,
        reverted or absent id is left out the same way. Each link comes back once, ordered by id.
        No ids give `[]`. A bare `str` for `edge_ids` is a `TypeError`, as for `get_nodes`. If the
        store holds two copies of one link id (ADR-056 Amendments 15 and 19), the one that comes
        back is whichever the store answered last: the port does not choose between them."""
        ...

    async def supersede_node(self, node_id: NodeId, replacement: NodeWrite, tx: TxId) -> NodeId:
        """`01_DOMAIN_MODEL.md` §2.4: "Nodes are versioned, not
        overwritten. A correction writes a new revision and points the old
        one forward." Writes `replacement` as a new node at
        `revision = node_id's current revision + 1`, sets `node_id`'s own
        `AuditStub.superseded_by` to the new node's id, and returns that
        new id. The old node is never deleted or edited otherwise — every
        prior revision, and the full `superseded_by` chain between them,
        remains individually retrievable via `get_node(...,
        include_superseded=True)`. Phase 6's retraction and Phase 8's
        judgement-review loop are the callers; the capability lands here,
        against the one adapter that exists, so both phases build on a
        conformance-tested primitive rather than each inventing their
        own. Repoints every edge incident to `node_id` onto the new node
        (cloned, not moved — an edge's endpoints are fixed at creation in
        every TinkerPop-family store), so a correction does not silently
        disconnect the corrected node from its own network. The
        superseded originals of those edges are excluded from ordinary
        reads the same way `node_id` itself now is."""
        ...

    async def supersede_edge(self, edge_id: EdgeId, replacement: EdgeWrite, tx: TxId) -> EdgeId:
        """The same operation as `supersede_node`, for an edge. `§3`:
        an edge carries `AuditStub` too, and `01_DOMAIN_MODEL.md` §5's
        `Judgement.supporting`/`contradicting` can name an `EdgeId`
        directly — a correction to the evidence itself must leave that
        reference resolvable to *something*, the same reason a corrected
        `Person` cannot just vanish. Unlike `supersede_node`, there is
        nothing to repoint: nothing in this domain model references an
        edge by id except an assessment's evidence list, which is a
        historical citation, not a live graph reference — it is expected
        to follow the `superseded_by` pointer, not be silently rewritten."""
        ...

    async def find_node(
        self, entity_type: str, identifier_field: str, value: str, principal: Principal
    ) -> Node | None:
        """`01_DOMAIN_MODEL.md` §7's `match_on`/`on_match` needs this: the
        recipe engine's `on_match: reference` looks an entity up by its
        declared identifier before deciding whether to create a new node,
        and there is no other way to express that query — `match()`'s
        `PatternQuery` has no property-value predicate, only an entity
        type. Added in Phase 2, without raising the gap first, the same way
        Phase 1 added transactions and schema management beyond
        `00_ARCHITECTURE.md` §2.1's illustrative snippet.

        Takes no `tx`: it always reads committed state. A node written via
        `upsert_nodes(..., tx)` under a still-open transaction is **not**
        guaranteed visible to `find_node` until that transaction commits —
        confirmed empirically against the ArcadeDB adapter (Phase 5's HMP
        fixture work, `packages/demo_fixtures/hmp_graph.py`), which does
        not offer read-your-writes within one open transaction. A caller
        that needs an `on_match: reference` lookup to see an earlier write
        in the same batch must commit between the write and the lookup, not
        assume `find_node` sees into an open transaction."""
        ...

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        """The Glass's global search box (`02_GLASS_FRONTEND.md`'s workspace
        layout) — `find_node` generalised across
        every entity type's declared `identifiers`
        (`schemas.domain.EntityTypeDef.identifiers`) instead of one
        caller-named `(entity_type, identifier_field)` pair, since the
        analyst does not know which type or field their query matches
        before searching.

        **Exact match, not full text.** `query` must equal a declared
        identifier value for a hit — no substring, prefix or fuzzy
        matching. `03_CONDUIT_MIDDLEWARE.md` §3.3 reserves "full text and
        embeddings" for OpenSearch, not wired into any deployment profile
        yet (Phase 6+/8); building fuzzy matching directly into this
        adapter's Gremlin would duplicate that future component and fight
        the boundary the docs already draw, for a capability (`TextP`-style
        predicates) this adapter has never needed and is not proven to
        support. This method is the v1 scope: it is a genuine capability
        gap `find_node` alone could not close (one caller-named field is not
        a search box), added the same way `find_node` grew `GraphPort` past its own
        illustrative sketch (`00_ARCHITECTURE.md` §2.1) — not a reason to
        also reach for fuzzy matching in the same change.

        Access-filtered exactly like every other read: a node whose
        identifier matches but whose handling excludes `principal` must not
        appear, count toward `limit`, or otherwise be detectable — the same
        existence-leak discipline `find_node` itself already proves."""
        ...

    async def suggest_locations(
        self, name: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        """The geocoder's own candidate retrieval, a disclosed gap — `services/geocoder/
        match.py`'s `match_place_mention` scores caller-supplied
        candidates but has never had a way to find its own; this closes
        that gap for `Location.name` specifically.

        **Deliberately not `search_nodes`, and not full text.**
        `search_nodes` (above) is exact-identifier match, generalised
        across every entity type's `identifiers` — extending it to fuzzy/
        prefix matching would break its own documented contract and, per
        its docstring, "fight the boundary" `03_CONDUIT_MIDDLEWARE.md`
        §3.3 and `04_VAULT_BACKEND.md` draw around full text and
        embeddings living in OpenSearch (Phase 6+/8, not wired into any
        deployment profile yet). This method does not build that
        capability either: it is a coarse, bounded, graph-native prefix/
        substring scan over `Location.name` only — not a Lucene/full-text
        index, no relevance scoring, no tokenisation pipeline — proportionate
        to the geocoder's own "not Splink-grade" scope (`services/geocoder/
        match.py`), which re-scores whatever this returns with `difflib`.

        Access-filtered exactly like every other read: a `Location` whose
        `handling` excludes `principal` must not appear, count toward
        `limit`, or otherwise be detectable."""
        ...

    async def suggest_nodes(
        self,
        prefix: str,
        principal: Principal,
        *,
        limit: int = 10,
        options: SuggestOptions | None = None,
    ) -> NodeSuggestions:
        """The Glass search box as the analyst types (ADR-059): nodes whose declared identifiers
        or indexed string properties **start with** `prefix`, case-sensitively, unless `options`
        (ADR-061) asks for `contains`, an exact match, case to be ignored, or only some types. A
        type name the ontology does not have is refused with `ValueError`. A separate read
        from `search_nodes`, which stays an exact match (its contract, and the reason
        `suggest_locations` is separate too).

        Bounded and graph-native, not full text: a prefix scan of only the entity types that
        carry a suggestable field, label first (an unlabelled lookup scans every vertex,
        ADR-058 Amendment 9). An empty `prefix` is refused with `ValueError`; the Conduit also
        refuses one shorter than its minimum, so a bare scan is never asked for.

        Never truncates silently (rule 2): returns at most `limit` nodes and sets `more` when
        another visible node matched. Access-filtered like every read (rule 3): a node whose
        `handling` excludes `principal` must not appear, count toward `limit` or set `more`."""
        ...

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph: ...

    async def edges_among(
        self,
        node_ids: Sequence[NodeId],
        principal: Principal,
        edge_types: list[str] | None = None,
    ) -> list[Edge]:
        """Every edge whose two ends are both in `node_ids` (ADR-098 decision 1): the links among
        what is on screen, which an expansion (the seed's own links only) leaves out. Each edge
        once. Access-filtered in the adapter (rule 3): an edge the principal may not see, or one
        whose other end they may not see, is absent and counted nowhere. `edge_types` narrows to
        those logical types. An empty or one-node set has none."""
        ...

    async def paths(self, req: PathRequest, principal: Principal) -> list[Path]: ...

    async def paths_at_length(
        self,
        source: NodeId,
        target: NodeId,
        length: int,
        limit: int,
        principal: Principal,
        *,
        edge_types: list[str] | None = None,
    ) -> RoutesAtLength:
        """ADR-116 decision 5: the simple routes of exactly `length` links from `source` to
        `target` — at most `limit` of them, with `more` set when others exist (rule 2) — found with
        the access predicate at every step, as `paths` is (01 §6.3): a route through a node or link
        the principal cannot see is never found, so nothing here, nor the fewest degrees a caller
        works out from it, can show that one exists. A `NOT_SAME_AS` link (an analyst's judgement
        that two records are different people) is never a step on a route."""
        ...

    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph: ...

    async def match_count(
        self, pattern: PatternQuery, principal: Principal, *, ceiling: int
    ) -> int:
        """`spec/02_GLASS_FRONTEND.md` §3.3's "estimated result count" for the visual query
        builder, and `08_ACCEPTANCE_SCENARIOS.md` B19's own "estimated count shown before
        running". **Principal-filtered.** A pattern's estimate is shown directly to the analyst, so
        it must be filtered by this same call, the same way `match()` itself is — an unfiltered
        count here is exactly what the Glass must never see, and the same
        existence-leak-by-aggregate access control must prevent, not a shortcut.

        Compiles the identical access-filtered traversal `match()` does (same `has_access`
        injected at every step) up to a `.dedup().count()` tail in place of `match()`'s own
        `.select(...).by(elementMap())` — cheaper (no property hydration) while guaranteeing the
        count and the eventual result set can never disagree about *who* is let through, only
        about how many are materialised.

        `ceiling` bounds the traversal's own `.limit()` before `.count()` — a real, unavoidable
        cost bound for a weakly-constrained pattern, not `pattern.limit` itself (a caller
        deciding whether a match needs the job hand-off, `03_CONDUIT_MIDDLEWARE.md` §3.3, must
        see past `pattern.limit` to know how far past it the true count goes). A returned count
        equal to `ceiling` means "at least `ceiling`", never a claim that `ceiling` is the exact
        total — the caller is the one that knows whether its own `ceiling` was exact or a floor,
        since this method's own return type carries no such flag itself."""
        ...

    async def neighbourhood_stats(
        self, node_id: NodeId, principal: Principal
    ) -> NeighbourhoodStats: ...

    async def type_counts(self, principal: Principal) -> TypeCounts:
        """`06_DECISIONS.md` ADR-100: how many nodes of each entity type and links of each link
        type `principal` can see. Counted in the store with the access step (rule 3): a hidden or
        other-dataset node is in no count, and a link counts only when both its ends can be seen."""
        ...

    async def most_connected(
        self,
        principal: Principal,
        *,
        entity_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> RankedNodes:
        """`06_DECISIONS.md` ADR-100: nodes by degree, most first, ties by id; of one entity type
        when named. A degree counts only links `principal` can see to nodes it can see, so a
        ranking is the same as in a graph where nothing hidden existed (rule 3). `total` is how
        many nodes are ranked; a page past the end is empty, never a slice that looks whole."""
        ...

    async def busiest_links(
        self,
        principal: Principal,
        *,
        edge_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
        node_id: str | None = None,
    ) -> RankedLinks:
        """`06_DECISIONS.md` ADR-100 decision 5: links by how many records each stands for
        (`occurrences`), most first, ties by id, of one link type when named, each with both its
        ends. Only links `principal` can see whose two ends it can see are ranked or counted in
        `total` (rule 3); a page past the end is empty. With `node_id` (Amendment 8), only that
        node's own links are ranked — how a dense node is brought to the canvas with its N busiest
        rather than all or nothing — under exactly the same access rules."""
        ...

    async def link_structure(
        self, principal: Principal, *, max_nodes: int, max_edges: int
    ) -> LinkStructure:
        """`06_DECISIONS.md` ADR-100 Amendment 5: every node and link `principal` can see, as only
        its structure (ids, types, ends, weights), for the case's groups. Access in the read
        (rule 3): a hidden node is absent and so is every link to it. Over a cap it raises
        `SubgraphTooLarge` with the counts of what the principal can see, never a slice (rule 2);
        the counts are taken first, so a breach is cheap."""
        ...

    async def recent_loads(self, principal: Principal, *, limit: int = 10) -> RecentLoads:
        """`06_DECISIONS.md` ADR-100 decision 7, Amendment 6: what `principal` can see, grouped by
        the load that wrote it (`audit.load_id`; `None` for what no load wrote), the newest first
        by its newest element, ties by id. Only visible nodes, and visible links whose two ends are
        visible, are counted, and a load that wrote nothing visible is not listed (rule 3); `total`
        is how many loads are."""
        ...

    async def recently_confirmed(
        self, principal: Principal, *, limit: int = 10
    ) -> RecentlyConfirmed:
        """`06_DECISIONS.md` ADR-100 decision 7, Amendment 6: the nodes `principal` can see whose
        provenance says an analyst confirmed them, the latest first, ties by id; `total` is how
        many. A superseded revision is not one (rule 3's access step excludes it)."""
        ...

    async def shared_contacts(
        self,
        node_id: NodeId,
        principal: Principal,
        *,
        edge_type: str,
        min_shared: int = 2,
        limit: int = 10,
    ) -> SharedContacts:
        """`06_DECISIONS.md` ADR-100 Amendment 7 decision 4: the nodes linked by `edge_type` to at
        least `min_shared` of the nodes `node_id` links to by it, most shared first, ties by id,
        with how many there are. Every link and node on the way passes the access step (rule 3):
        a hidden contact or link is in no count. A node the principal cannot see shares with
        nobody."""
        ...

    async def apply_schema(self, schema: OntologySchema) -> SchemaReport: ...
    async def revert_schema(self, to_version: int) -> SchemaReport: ...

    async def list_nodes(
        self,
        entity_type: str,
        principal: Principal,
        *,
        cursor: NodeId | None = None,
        limit: int = 500,
    ) -> ListNodesPage:
        """The first bulk read this port has ever had — `06_DECISIONS.md`
        ADR-025: the corpus-wide resolution trigger needs "every `Person`
        node," and nothing before this could produce it (`find_node`/
        `search_nodes` need an exact identifier value, `expand`/`paths`
        need a known seed, `match` needs a bounded pattern). Paginated,
        access-controlled exactly like every other read.

        **Cursor: keyset on `id`, not an offset.** `NodeId`s are ULIDs —
        lexicographically sortable and fixed at creation
        (`01_DOMAIN_MODEL.md` §2) — so `cursor` is the last id already
        returned and a page selects `id > cursor`, ordered by `id`. This is
        not snapshot isolation: a node written *after* a scan starts is
        picked up by a later page in the ordinary case (its id sorts after
        the current cursor), never duplicated, and a node that already
        existed is visited exactly once regardless of what else is written
        concurrently while the scan runs. `06_DECISIONS.md` ADR-025's own
        "re-run whole, never resume from a checkpoint" recovery model is
        what makes this an acceptable trade rather than a defect: a node
        missed by one pass (only possible under ULID clock skew across
        writers) is corrected by the next triggered run, not by this
        method trying to guarantee a perfect snapshot it cannot cheaply
        give.

        **Not `limit_exceeded`'s contract.** That typed error is
        analyst-facing — three interactive options a person chooses
        between (`03_CONDUIT_MIDDLEWARE.md` §4). This method's only caller
        is a service principal that pages; there is no one to offer a
        choice to. `ListNodesPage.next_cursor is None` is the sole signal
        of exhaustion, never an empty `nodes` list on its own — a page can
        legitimately return zero *visible* nodes while more exist further
        on, if this page's key range happens to be entirely hidden from
        `principal`. A caller that pages once and treats it as the whole
        population recreates, one layer up, exactly the silent truncation
        rule 2 forbids this port from producing itself.

        Access-filtered exactly like every other read: a node hidden from
        `principal` must not appear, must not count toward `limit`, and
        the pagination shape itself (page count, last page size, whether a
        final page carries a `next_cursor`) must be identical to a graph
        where that hidden node never existed — the same existence-leak
        discipline `find_node`/`search_nodes` already prove, extended to a
        paginated result."""
        ...

    async def vault_subgraph(
        self, principal: Principal, *, max_nodes: int, max_edges: int
    ) -> Subgraph:
        """`06_DECISIONS.md` ADR-057: every node and edge `principal` can see in the graph this
        adapter is connected to (under ADR-056, one vault's graph; a case supplies only the
        authorisation, never the scope). The overview's read.

        **Access control is in the read itself,** like every other (`CLAUDE.md` rule 3): a hidden
        node is absent, is not counted, and its edges are absent. A count of hidden elements is
        what the Conduit must never pass on, and `Subgraph` has no field for one.

        **Never a slice (rule 2).** Over `max_nodes` or `max_edges` this raises `SubgraphTooLarge`
        carrying the counts of what the principal can see; it never returns a subset. The adapter
        counts before it reads, so a breach is cheap.

        **Not paged, deliberately.** The caller needs the whole subgraph at once to find
        communities; the caps (the working set's 50,000 and 250,000) bound it. A page that looked
        like the whole
        would be the silent truncation rule 2 forbids, which is why `list_nodes`' cursor is not
        reused."""
        ...

    async def revert_elements(
        self, node_ids: Sequence[NodeId], edge_ids: Sequence[EdgeId], tx: TxId
    ) -> None:
        """Marks existing elements reverted (`AuditStub.reverted`,
        `01_DOMAIN_MODEL.md` §2.4) — `services/ingest/load_revert.py` is
        the only caller. A reverted element is invisible to every read
        method afterwards, any principal, the same way a hidden record is
        invisible to an unauthorised one; it is never actually deleted, so
        the audit trail stays intact. No `principal` argument, matching
        `upsert_nodes`/`upsert_edges` — this is a backend write attributed
        by the caller's own audit trail (the load ledger), not a
        principal-scoped read.

        Each id is resolved to its stored type through that type's unique `id` index, nodes among
        the vertex types and links among the edge types only, and set reverted by SQL on that
        type, in chunks. An id held by two types of one kind raises `AmbiguousElementId` before
        anything is written. Setting the flag again changes nothing, so a rerun is safe."""
        ...

    async def live_edges_touching(self, node_ids: Sequence[NodeId]) -> set[EdgeId]:
        """ADR-127 Amendment 6. The ids of the live links (neither reverted nor superseded) with
        one of `node_ids` at either end, **whatever the caller may read**: no principal, no access
        step. For the revert alone, to tell whether a link outside the load being reverted rests on
        a node the load created (a later load may only have referenced the node, which its record
        keeps as a count). A route must never call it
        (`tests/test_unfiltered_node_lookup_confined.py`). Each id once however often given; no ids
        give the empty set; a bare `str` is a `TypeError`."""
        ...

    async def live_nodes_naming_geometry(
        self, geometry_refs: Sequence[str]
    ) -> dict[str, set[NodeId]]:
        """As `live_edges_touching`, for the geometry partition: for each of `geometry_refs` that a
        live node (neither reverted nor superseded) names in its `geometry_ref`, the ids of those
        nodes, whatever the caller may read. A ref no live node names is absent from the answer.
        For the revert alone, so a point a later load's `Location` still names is not removed. No
        refs give `{}`; a bare `str` is a `TypeError`."""
        ...

    async def stored_writes(self, node_ids: Sequence[NodeId]) -> dict[NodeId, StoredNode]:
        """As `live_edges_touching`, for the last write to each node: its stored `audit.load_id`
        (`None` for a write outside a load) and whether it is reverted, whatever the caller may
        read and whatever the node's state (a superseded node is answered too). An id no node
        holds is absent. A write onto an existing node rewrites the load (a merge, even one by
        another load or by an upload, and a fresh create over a reverted node), so this is how the
        revert tells that a node it created has since been written by someone else, and whether an
        earlier attempt already reverted it. For the revert alone. No ids give `{}`; a bare `str`
        is a `TypeError`."""
        ...

    async def strip_provenance_references(self, prefix: str) -> int:
        """Removes every provenance entry whose `document_id` starts with `prefix` from every link
        in the Vault, superseded and reverted ones included, and returns how many links changed
        (ADR-124 decision 11). `scripts/strip_change_provenance.py` is the only caller: it removes
        the `manual:change:<old id>` and `manual:remove-picture:<old id>` entries that successors
        written before U10 carry, naming a link a reader of the successor may not be able to read.

        No `principal` argument, like `revert_elements`: it is an operator's one-off write on the
        stored body, not a read. It changes no claim, only a reference, which is the named
        exception to ADR-080's "every change is a supersede": nothing is superseded, `audit` is
        untouched, and the link keeps its other sources. Idempotent: a second call with the same
        prefix changes nothing and returns 0."""
        ...


SuggestMode = Literal["starts_with", "contains", "exact"]


@dataclass(frozen=True)
class SuggestOptions:
    """How `GraphPort.suggest_nodes` matches (ADR-061). The default is exactly ADR-059's: the
    value **starts with** what was typed, case-sensitively, on every type that carries a string
    identifier. `ignore_case` and `contains` cannot use an index, so they scan the labelled types;
    `types` (entity type names) narrows that scan."""

    mode: SuggestMode = "starts_with"
    ignore_case: bool = False
    types: tuple[str, ...] | None = None


@dataclass(frozen=True)
class NodeSuggestions:
    """What `GraphPort.suggest_nodes` found for a partial value: the first `limit` visible nodes,
    and whether more visible nodes matched. `more` is counted after the access filter, so it can
    never say that a hidden node exists (ADR-059)."""

    nodes: list[Node] = field(default_factory=list)
    more: bool = False


@dataclass(frozen=True)
class BulkEdgeResult:
    """What `BulkGraphLoader.bulk_load_edges` did, in full: nothing is dropped silently.

    `written` are the ids of the edges now stored, one per distinct pair. `collisions` are the
    aggregated writes whose pair was already stored; they were **not** written, and the caller
    routes them through `GraphPort.upsert_edges`, which merges (ADR-058 D3). `received` is how
    many `EdgeWrite`s arrived, so `received - len(written) - len(collisions)` is the number
    collapsed by aggregating repeated pairs in this call."""

    written: list[EdgeId] = field(default_factory=list)
    collisions: list[EdgeWrite] = field(default_factory=list)
    received: int = 0
    chunks: int = 0


@runtime_checkable
class BulkGraphLoader(Protocol):
    """An optional capability of a graph adapter (ADR-058): write a *set* of edges in bulk.

    `upsert_edges` is the low-volume path: it merges on write, weighs each edge against the live
    corpus and costs several store round trips per edge. A set that arrives together (an Ingest
    Studio publish, a seed) goes through this instead, and the engine falls back to chunked
    `upsert_edges` for an adapter that does not declare it. The contract:

    - **Validation is identical to `upsert_edges`.** Every edge is checked against the active
      ontology (type, properties, endpoint types) and the handling scheme. The loader is never
      trusted: a bad edge raises `OntologyError`, and it raises *before anything is written*.
    - **Endpoints already exist,** committed by the caller (a node written in the same load is
      written first). A missing endpoint raises `OntologyError`, as `upsert_edges` does.
    - **Repeated pairs are aggregated** by the one shared merge rule (`schemas.merge`): occurrences
      add, every provenance source is kept, the interval widens, the first write's id survives.
    - **A pair already stored is not written** and comes back in `collisions` (a reverted edge is
      not a collision, as in `upsert_edges`: a fresh edge starts).
    - **Weights are against the corpus as it stands at the end of the load** (existing edges plus
      this call's), with the formula and `WeightComponents` unchanged and `computed_at` the end of
      the load (`01_DOMAIN_MODEL.md` §6.1, ADR-058 D4).
    - **No `TxId`.** The call is too large for one transaction, so the adapter commits in chunks of
      `chunk_size` edges, each in its own. A failure part-way raises with the earlier chunks
      committed; the caller reverts by `load_id` and reruns, it does not resume (ADR-058 D6).
    - `progress(done, total)` is called after each chunk if given.
    """

    async def bulk_load_edges(
        self,
        edges: Sequence[EdgeWrite],
        *,
        chunk_size: int = 500,
        progress: Callable[[int, int], None] | None = None,
    ) -> BulkEdgeResult: ...
