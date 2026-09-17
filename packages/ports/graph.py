"""`GraphPort` — `docs/00_ARCHITECTURE.md` §2.1.

Persistent property graph: write, traverse, subgraph extraction, schema
management. Gremlin/TinkerPop 3.8 is the query language; the transport is
each adapter's own business (WebSocket/GraphBinary or an HTTP command
endpoint are both conformant). Gremlin never leaves the Vault — nothing
above this port may see it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from schemas.domain import (
    EdgeId,
    EdgeWrite,
    ExpandRequest,
    NeighbourhoodStats,
    Node,
    NodeId,
    NodeWrite,
    OntologySchema,
    Path,
    PathRequest,
    PatternQuery,
    Principal,
    SchemaReport,
    Subgraph,
    TxId,
)


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
        fixture work, `tests/scenarios/fixtures/hmp_graph.py`), which does
        not offer read-your-writes within one open transaction. A caller
        that needs an `on_match: reference` lookup to see an earlier write
        in the same batch must commit between the write and the lookup, not
        assume `find_node` sees into an open transaction."""
        ...
    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        """The Glass's global search box (`02_GLASS_FRONTEND.md`'s workspace
        layout, `07_BUILD_PLAN.md` Phase 4) — `find_node` generalised across
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
        a search box), added the same way `find_node` and
        `expand_candidate_count` themselves grew `GraphPort` past its own
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
        """The geocoder's own candidate retrieval (`07_BUILD_PLAN.md`'s
        Phase 5 known-gaps list) — `services/geocoder/
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

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph: ...

    async def expand_candidate_count(self, req: ExpandRequest) -> int:
        """The unfiltered half of `Subgraph.filtered_count`'s comparison
        (`01_DOMAIN_MODEL.md` §8.2, Phase 3 — `07_BUILD_PLAN.md`): how many
        nodes the *same* seed set, depth, edge-type and temporal scope as
        `expand(req, principal)` would reach with neither access axis
        applied. No `Principal` argument, matching `revert_elements` — not
        a principal-scoped read, and it returns only a bare count, never a
        node, an id or a property, so it cannot itself disclose which
        nodes are hidden or why. `services/api`'s Working-Set Service is
        the only sanctioned caller: it already holds the properly-filtered
        result of the matching `expand()` call under its own authority,
        and `expand_candidate_count(req) - len(filtered.nodes)` is
        `filtered_count` — the comparison `GraphPort` alone cannot make
        from inside one filtered call, since a single `expand()` only ever
        sees the already-filtered result (`01_DOMAIN_MODEL.md` §8.2's own
        reasoning for why this couldn't be computed before this port grew
        this method)."""
        ...

    async def paths(self, req: PathRequest, principal: Principal) -> list[Path]: ...
    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph: ...

    async def neighbourhood_stats(
        self, node_id: NodeId, principal: Principal
    ) -> NeighbourhoodStats: ...

    async def apply_schema(self, schema: OntologySchema) -> SchemaReport: ...
    async def revert_schema(self, to_version: int) -> SchemaReport: ...

    async def revert_elements(
        self, node_ids: Sequence[NodeId], edge_ids: Sequence[EdgeId], tx: TxId
    ) -> None:
        """Marks existing elements reverted (`AuditStub.reverted`,
        `01_DOMAIN_MODEL.md` §2.4) — `services/ingest`'s `revert_load` is
        the only caller. A reverted element is invisible to every read
        method afterwards, any principal, the same way a hidden record is
        invisible to an unauthorised one; it is never actually deleted, so
        the audit trail stays intact. No `principal` argument, matching
        `upsert_nodes`/`upsert_edges` — this is a backend write attributed
        by the caller's own audit trail (the load ledger), not a
        principal-scoped read."""
        ...
