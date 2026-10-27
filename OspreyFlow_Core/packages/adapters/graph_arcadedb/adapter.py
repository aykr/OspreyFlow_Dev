"""`GraphArcadeDBAdapter` — full `GraphPort` over ArcadeDB.

Every read method injects the access filter into the traversal itself
(`access_filter.py`) — never fetches broadly and filters the result — so an
unauthorised principal's query runs the same code path, with the same
predicate, whether or not a hidden record exists.

Every write validates against the ontology before it touches the store
(`ontology/validation.py`) — a property's declared type, a required
property's presence, and an edge's declared endpoint types are all checked
here, on the write path, not left for a caller to have got right.

No read here counts what it left out: a figure for what the reader may not read points at it
(ADR-124 decision 1), so `Subgraph` has no such field.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Hashable, Mapping, Sequence
from datetime import datetime
from typing import Any

from conduit_common.identity import new_edge_id, now_utc
from ontology.errors import OntologyError
from ontology.handling import HandlingScheme, audience_of, audience_parts, merge_handling
from ontology.pattern_where import check_pattern_conditions
from ontology.validation import validate_edge_endpoints, validate_properties
from ontology.weights import WeightRules, load_weight_rules
from ports.graph import (
    AmbiguousElementId,
    BulkEdgeResult,
    FindLimitExceeded,
    NodeSuggestions,
    StoredLink,
    StoredNode,
    SubgraphTooLarge,
    SuggestOptions,
)
from schemas.compute import LinkStructure, StructureEdge, StructureNode
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeId,
    EdgeWrite,
    ExpandRequest,
    Handling,
    Interval,
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
    Provenance,
    RoutesAtLength,
    SchemaReport,
    Subgraph,
    TxId,
    WeightComponents,
)
from schemas.explore import (
    ConfirmedNode,
    LoadSummary,
    RankedLink,
    RankedLinks,
    RankedNode,
    RankedNodes,
    RecentLoads,
    RecentlyConfirmed,
    SharedContact,
    SharedContacts,
    TypeCounts,
)
from schemas.merge import merge_datasets, merge_interval, merge_properties, merge_provenance

from .access_filter import AccessFilter
from .builders import (
    BusiestLinksBuilder,
    ExpandBuilder,
    FindByIdentifierBuilder,
    GetNodeBuilder,
    ListNodesBuilder,
    MatchBuilder,
    MostConnectedBuilder,
    NeighbourhoodStatsBuilder,
    PathBuilder,
    RoutesAtLengthBuilder,
    SearchNodesBuilder,
    SuggestLocationsBuilder,
    SuggestNodesBuilder,
    render_edges_among_gremlin,
    render_existing_ids_sql,
    render_get_edges_gremlin,
    render_get_nodes_gremlin,
    render_link_structure_gremlin,
    render_live_node_ids_sql,
    render_recent_loads_gremlin,
    render_recently_confirmed_gremlin,
    render_record_id_lookup_sql,
    render_shared_contacts_gremlin,
    render_type_counts_gremlin,
    suggestion_scope,
)
from .bulk import BulkEdgeLoader, BulkTransport, GremlinBulkTransport
from .client import ArcadeDBClient
from .gremlin_literals import (
    groovy_identifier,
    groovy_string_list_literal,
    groovy_string_literal,
)
from .naming import logical_type_name, physical_type_name, set_edge_aliases
from .schema import apply_schema as _apply_schema_ddl
from .schema import drop_schema as _drop_schema_ddl
from .serialization import (
    edge_from_element_map,
    edge_write_to_properties,
    node_from_element_map,
    node_write_to_properties,
)
from .weight import compute_weight

#: Ids per query for `get_nodes` and `get_edges` (ADR-124 decision 6): one `IN` list stays a bounded
#: parameter however many ids a caller asks for.
_ID_CHUNK = 1000

#: What ArcadeDB calls a record: `#<bucket>:<position>`. Checked before one is put in a Gremlin
#: literal, though the store is what said it.
_RECORD_ID = re.compile(r"^#\d+:\d+$")


#: How many links `strip_provenance_references` reads at a time.
_STRIP_PAGE = 500


def _without_references(provenance: object, prefix: str) -> dict[str, Any] | None:
    """`provenance` with every source whose `document_id` starts with `prefix` removed, or `None`
    when none does (nothing to write). Only `sources` changes."""
    if not isinstance(provenance, dict):
        return None
    sources = provenance.get("sources")
    if not isinstance(sources, list):
        return None
    kept = [
        s
        for s in sources
        if not (isinstance(s, dict) and str(s.get("document_id", "")).startswith(prefix))
    ]
    if len(kept) == len(sources):
        return None
    return {**provenance, "sources": kept}


def _id_chunks(ids: Sequence[str]) -> list[list[str]]:
    """`ids` without repeats, in the order given, in lists of at most `_ID_CHUNK`. No ids give no
    lists, so an empty read sends no query. A bare `str` is refused: it is a sequence of
    characters, and `get_nodes("01ABC")` would look up five one-character ids."""
    if isinstance(ids, str):
        raise TypeError("ids must be a sequence of ids, not a single string")
    unique = list(dict.fromkeys(ids))
    return [unique[start : start + _ID_CHUNK] for start in range(0, len(unique), _ID_CHUNK)]


#: How many nodes sharing one identifier value `find_node(also=...)` reads to choose among. Two
#: Endpoints sharing a text with different kinds is the case it exists for. More than this many
#: visible nodes sharing one value is ordinary (each source keeps its own copy, rule 6), so the read
#: is one past it and a lookup that overflows without a match raises `FindLimitExceeded`.
FIND_WITH_ALSO_LIMIT = 50


class GraphArcadeDBAdapter:
    """`spec/00_ARCHITECTURE.md` §2.1. `dialects` is `{"gremlin"}` in Phase 1
    (ADR-003's amendment) — a second dialect adds a `render_<dialect>` to
    each builder in `builders.py`, not a change here."""

    dialects: frozenset[str] = frozenset({"gremlin"})

    def __init__(
        self,
        client: ArcadeDBClient,
        handling_scheme: HandlingScheme,
        *,
        weight_rules: WeightRules | None = None,
        bulk_transport: BulkTransport | None = None,
    ) -> None:
        self._client = client
        self._access = AccessFilter(handling_scheme)
        self._scheme = handling_scheme
        # The weights file is read once, here: every weight this adapter stores is computed under
        # this version's rules and records it (ADR-120 D3).
        self._weight_rules = weight_rules or load_weight_rules()
        # The bulk-load capability (`ports.graph.BulkGraphLoader`, ADR-058). The transport is
        # swappable so the loader's logic is testable without a store.
        self._bulk = BulkEdgeLoader(
            bulk_transport or GremlinBulkTransport(client),
            self._weight_rules,
            handling_scheme=handling_scheme,
        )
        self._schema: OntologySchema | None = None
        # In-memory only: a real migration runner persists applied versions
        # to survive a restart. Reverting to a version never applied in
        # this adapter's lifetime is out of scope for Phase 1.
        self._schema_history: dict[int, OntologySchema] = {}

    # --- transactions --------------------------------------------------

    async def begin_transaction(self) -> TxId:
        return await self._client.begin_transaction()

    async def commit_transaction(self, tx: TxId) -> None:
        await self._client.commit_transaction(tx)

    async def rollback_transaction(self, tx: TxId) -> None:
        await self._client.rollback_transaction(tx)

    async def aclose(self) -> None:
        """Stops the keep-alive of every transaction still open (ADR-127 Amendment 20) and closes
        the connections."""
        await self._client.aclose()

    # --- writes ----------------------------------------------------------

    def _require_schema(self) -> OntologySchema:
        if self._schema is None:
            raise OntologyError("no ontology schema has been applied — call apply_schema first")
        return self._schema

    async def _find_existing_node(
        self, node_id: NodeId, *, session_id: TxId
    ) -> dict[str, Any] | None:
        """Unfiltered by design — an internal lookup during a trusted write, the same as
        `_node_type`'s and `supersede_node`'s own. A second `upsert_nodes` call for the same id
        (a re-ingested load; the same fixture seeded twice, `tests/conformance/graph_port/
        test_suite.py`'s own case for this) must find and update the existing node, never insert
        a duplicate that collides on the same declared `id` property."""
        node_lit = groovy_string_literal(node_id)
        results = await self._client.gremlin(
            f'g.V().has("id",{node_lit}).elementMap()', session_id=session_id
        )
        return results[0] if results else None

    async def upsert_nodes(self, nodes: Sequence[NodeWrite], tx: TxId) -> list[NodeId]:
        """A real upsert, keyed on `write.id` — select-then-branch (`UPDATE ... WHERE id = :id`
        vs `INSERT INTO`), the same shape `upsert_edges` below already uses, not ArcadeDB's own
        `UPDATE ... UPSERT`: merging provenance and bumping `audit.revision` both need the
        existing row's own values *before* the write, so a preceding lookup is unavoidable either
        way, and branching on it explicitly reads the same as `upsert_edges`'s own `existing is
        not None` shape rather than a second, differently-shaped mechanism.

        **What merges, what does not — the same split `_merge_provenance`'s own docstring already
        states for edges.** `provenance` merges (`01_DOMAIN_MODEL.md` §7: every source row
        reference is retained; de-duplicated by `(document_id, locator)`), and `audit.revision`
        increments rather than resetting. The write's own `properties`/`handling`/`resolution`
        are the latest write's values (except that a write never lowers an asserted node:
        `schemas.merge`), not deep-merged field by field — the same "latest write
        wins" `upsert_edges` already applies to everything it does not name as cumulative, since
        there is no way to resolve two *conflicting* values for one ontology property without
        inventing a merge rule the ontology itself does not declare. Nothing is silently dropped
        by this: the one thing `01_DOMAIN_MODEL.md` requires never to shrink — the provenance
        list — never does.
        """
        schema = self._require_schema()
        ids: list[NodeId] = []
        for write in nodes:
            entity_type = schema.entity_type(write.type)
            if entity_type is None:
                raise OntologyError(f"{write.type!r} is not a type in the active ontology")
            validate_properties(entity_type, write.properties)

            node_id = write.id
            existing = await self._find_existing_node(node_id, session_id=tx)
            # A reverted node is not merged into (ADR-127 Amendment 6): its body, marking and
            # datasets were taken back with its load, so none of them may carry into the write.
            # The write is a fresh create under the same id, which `UPDATE` below clears of
            # `reverted` because the new audit is `reverted = false`.
            replaces_reverted = existing is not None and existing.get("reverted") is True
            if existing is not None and not replaces_reverted:
                existing_audit = AuditStub.model_validate(existing["audit"])
                audit = existing_audit.model_copy(
                    update={
                        "revision": existing_audit.revision + 1,
                        "load_id": write.load_id,
                        "recipe_id": write.recipe_id,
                        "recipe_version": write.recipe_version,
                    }
                )
                merged_provenance = self._merge_provenance(
                    existing.get("provenance"), write.provenance
                )
                merged_properties = self._merge_properties(existing, write)
                merged_datasets = merge_datasets(existing.get("datasets"), write.datasets)
                merged_handling = self._merge_handling(existing, write.handling)
            else:
                audit = AuditStub(
                    created_at=write.created_at,
                    created_by=write.created_by,
                    load_id=write.load_id,
                    recipe_id=write.recipe_id,
                    recipe_version=write.recipe_version,
                    # Only `reverted` is cleared: a node superseded as well stays the old revision,
                    # so reads keep following its successor (the stored property is left as it is).
                    superseded_by=(
                        existing.get("superseded_by")
                        if existing is not None and replaces_reverted
                        else None
                    ),
                )
                merged_provenance = write.provenance
                merged_properties = write.properties
                merged_datasets = merge_datasets(None, write.datasets)
                merged_handling = write.handling

            merged_write = write.model_copy(
                update={
                    "properties": merged_properties,
                    "provenance": merged_provenance,
                    "datasets": merged_datasets,
                    "handling": merged_handling,
                }
            )
            props = node_write_to_properties(
                merged_write, node_id=node_id, audit=audit, entity_type=entity_type
            )
            type_name = groovy_identifier(physical_type_name(write.type))
            set_clause = ", ".join(f"{key} = :{key}" for key in props)
            if existing is not None:  # live (merged above) or reverted (replaced whole)
                await self._client.sql(
                    f"UPDATE {type_name} SET {set_clause} WHERE id = :id",
                    params=props,
                    session_id=tx,
                )
            else:
                await self._client.sql(
                    f"INSERT INTO {type_name} SET {set_clause}", params=props, session_id=tx
                )
            ids.append(node_id)
        return ids

    async def _node_type(self, node_id: NodeId, *, session_id: TxId) -> str | None:
        node_lit = groovy_string_literal(node_id)
        results = await self._client.gremlin(
            f'g.V().has("id",{node_lit}).label()', session_id=session_id
        )
        if not results:
            return None
        return logical_type_name(results[0]["result"])

    async def _find_existing_edge(
        self,
        type_name: str,
        source: NodeId,
        target: NodeId,
        *,
        directed: bool,
        audience: Hashable,
        session_id: TxId,
    ) -> dict[str, Any] | None:
        """`01_DOMAIN_MODEL.md` §3: one summarised edge per pair per type.
        A second `upsert_edges` call for the same (type, source, target) —
        the same pair recurring in a later ingest load — must find and
        merge into this edge, never add a second one. A *reverted* edge is
        excluded: a later load touching the same pair starts a fresh edge
        rather than silently resurrecting retracted data by piling more
        occurrences onto it. A *superseded* edge is excluded too: its
        replacement is the pair's edge now (`supersede_edge` leaves the old
        one in place for citations), and a write merged into the old one
        would vanish from every ordinary read.

        **Only a link of the write's own audience** (ADR-102 Amendment 3): the same classification,
        handling code, set of datasets and, under a restricted code, units (`audience_of`). A link
        another audience can see is not this write's to merge into, however it matches by pair, or a
        reader of the first would see the link vanish and its path and degree move when a stricter
        write arrived, and a link restricted to one unit would carry another unit's row. The pair's
        links are all read and the one of this audience, if any, is returned. There is usually at
        most one, since writes of one audience merge, but `supersede_edge` can put a replacement
        beside a live link of its audience, so the choice is deterministic: the higher revision,
        then the later creation, then the greater id, never whichever the store returns first."""
        src_lit = groovy_string_literal(source)
        tgt_lit = groovy_string_literal(target)
        label_lit = groovy_string_literal(type_name)
        step = "outE" if directed else "bothE"
        other = "inV" if directed else "otherV"
        query = (
            f'g.V().has("id",{src_lit}).{step}({label_lit}).has("reverted",false)'
            f'.hasNot("superseded_by").where({other}().has("id",{tgt_lit})).elementMap()'
        )
        results = await self._client.gremlin(query, session_id=session_id)
        same = [row for row in results if self._stored_audience(row) == audience]
        if not same:
            return None

        def newest(row: Mapping[str, Any]) -> tuple[int, datetime, str]:
            audit = AuditStub.model_validate(row["audit"])
            return (audit.revision, audit.created_at, str(row["id"]))

        return max(same, key=newest)

    async def _edge_id_taken(self, type_name: str, edge_id: EdgeId, *, session_id: TxId) -> bool:
        """Whether an edge of this type already holds `edge_id`, whatever its state. Edge `id` is
        UNIQUE per type (`schema.py`) and a reverted or superseded edge keeps its id, so this asks
        no `reverted` or `superseded_by` question. Asked of the type's unique `id` index by SQL, as
        `get_nodes` and `existing_node_ids` are, not by a traversal that may scan the type."""
        rows = await self._client.sql(
            render_existing_ids_sql(type_name), params={"ids": [edge_id]}, session_id=session_id
        )
        return bool(rows)

    def _stored_audience(self, row: Mapping[str, Any]) -> Hashable:
        """The audience of a stored link read back as an element map: the same key `audience_of`
        gives the write. A link with no datasets property has none."""
        datasets = row.get("datasets") or []
        return audience_parts(
            str(row.get("handling_classification")),
            str(row.get("handling_code")),
            [datasets] if isinstance(datasets, str) else [str(d) for d in datasets],
            str(row.get("originator")),
            str(row.get("owning_unit")),
            self._scheme,
        )

    async def _sum_occurrences(self, query: str, session_id: TxId) -> int:
        results = await self._client.gremlin(query, session_id=session_id)
        if not results:
            return 0
        return int(results[0].get("result") or 0)

    async def _corpus_edge_stats(
        self,
        type_name: str,
        source: NodeId,
        target: NodeId,
        *,
        session_id: TxId,
        corpus_total: int | None = None,
    ) -> tuple[int, int, int]:
        """Occurrences-weighted degree of `source` and `target` and the
        corpus-wide total for this edge type, *before* this write's own
        delta is added — `upsert_edges` adds that delta itself, since it is
        the one write not yet reflected in the store at the moment this
        query runs. Reverted and superseded edges are excluded
        throughout: retracted data must not still weigh on the corpus statistics live edges are
        scored against, and a superseded link's occurrences live on in its successor (ADR-120
        Amendment 5), so counting both would count them twice.

        `corpus_total`, when the caller already holds it, is used as it stands and the store is not
        asked: the total is a whole-corpus traversal, and `upsert_edges` reads it once per call and
        carries it forward rather than once per edge (ADR-056 Amendment 22)."""
        label_lit = groovy_string_literal(type_name)
        src_lit = groovy_string_literal(source)
        tgt_lit = groovy_string_literal(target)
        source_degree = await self._sum_occurrences(
            f'g.V().has("id",{src_lit}).bothE({label_lit}).has("reverted",false)'
            '.hasNot("superseded_by").values("occurrences").sum()',
            session_id,
        )
        target_degree = await self._sum_occurrences(
            f'g.V().has("id",{tgt_lit}).bothE({label_lit}).has("reverted",false)'
            '.hasNot("superseded_by").values("occurrences").sum()',
            session_id,
        )
        if corpus_total is not None:
            return source_degree, target_degree, corpus_total
        corpus_total = await self._sum_occurrences(
            # Reached from the vertices, each edge once through its source's out-list: a scan of the
            # type (`g.E()`) also counts the stray second records ArcadeDB sometimes stores, which
            # no traversal reaches (ADR-056 Amendment 19). It visits every vertex, so it costs a
            # vertex scan more than the edge scan did. A link that is reverted or superseded is not
            # counted, as no read returns it (ADR-120 Amendment 5).
            f'g.V().outE({label_lit}).has("reverted",false).hasNot("superseded_by")'
            '.values("occurrences").sum()',
            session_id,
        )
        return source_degree, target_degree, corpus_total

    @staticmethod
    def _merge_provenance(existing: object, incoming: Provenance) -> Provenance:
        """The merge rule is shared with the bulk path (`schemas.merge`, ADR-058 D5): the stored
        value arrives as a dict, so it is validated and handed to the shared rule."""
        return merge_provenance(Provenance.model_validate(existing) if existing else None, incoming)

    @staticmethod
    def _merge_properties(existing: dict[str, Any], write: NodeWrite | EdgeWrite) -> dict[str, Any]:
        """The shared rule (`schemas.merge.merge_properties`): the latest write's properties, unless
        it would lower an asserted element."""
        stored = existing.get("provenance")
        return merge_properties(
            existing.get("properties"),
            write.properties,
            existing_provenance=Provenance.model_validate(stored) if stored else None,
            incoming_provenance=write.provenance,
        )

    @staticmethod
    def _merge_interval(existing: object, incoming: Interval | None) -> Interval | None:
        return merge_interval(Interval.model_validate(existing) if existing else None, incoming)

    async def upsert_edges(self, edges: Sequence[EdgeWrite], tx: TxId) -> list[EdgeId]:
        schema = self._require_schema()
        ids: list[EdgeId] = []
        now = now_utc()
        # Read once per call, per type, then carried forward: the corpus total is a whole-corpus
        # traversal, and the only change it can see during this call is the call's own writes
        # (ADR-056 Amendment 22). Never kept between calls, since anything may write or revert then.
        corpus_totals: dict[str, int] = {}
        for write in edges:
            edge_type = schema.edge_type(write.type)
            if edge_type is None:
                raise OntologyError(f"{write.type!r} is not a type in the active ontology")
            validate_properties(edge_type, write.properties)
            if write.writes < 1:
                raise OntologyError(
                    f"a write standing for {write.writes} writes: a link is the product of at "
                    "least one"
                )

            source_type = await self._node_type(write.source, session_id=tx)
            target_type = await self._node_type(write.target, session_id=tx)
            if source_type is None:
                raise OntologyError(f"edge source {write.source!r} does not exist")
            if target_type is None:
                raise OntologyError(f"edge target {write.target!r} does not exist")
            validate_edge_endpoints(edge_type, source_type=source_type, target_type=target_type)

            type_name = groovy_identifier(physical_type_name(write.type))
            existing = await self._find_existing_edge(
                type_name,
                write.source,
                write.target,
                directed=edge_type.directed,
                audience=audience_of(write.handling, write.datasets, self._scheme),
                session_id=tx,
            )

            if existing is not None:
                edge_id = str(existing["id"])
                merged_occurrences = int(existing.get("occurrences") or 1) + write.occurrences
                merged_interval = self._merge_interval(existing.get("interval"), write.interval)
                merged_provenance = self._merge_provenance(
                    existing.get("provenance"), write.provenance
                )
                merged_properties = self._merge_properties(existing, write)
                merged_datasets = merge_datasets(existing.get("datasets"), write.datasets)
                merged_handling = self._merge_handling(existing, write.handling)
                existing_audit = AuditStub.model_validate(existing["audit"])
                audit = existing_audit.model_copy(
                    update={
                        "revision": existing_audit.revision + write.writes,
                        "load_id": write.load_id,
                        "recipe_id": write.recipe_id,
                        "recipe_version": write.recipe_version,
                    }
                )
            else:
                # A write of a fixed id (`HOLDS`, a mention, a seeder's pair id) whose id a link of
                # another audience holds cannot create under it: edge `id` is UNIQUE. It is a link
                # of its own under a new id, which is what this call returns (ADR-102 Amendment 3).
                edge_id = write.id
                if await self._edge_id_taken(type_name, edge_id, session_id=tx):
                    edge_id = new_edge_id()
                merged_occurrences = write.occurrences
                merged_interval = write.interval
                merged_provenance = write.provenance
                merged_properties = write.properties
                merged_datasets = merge_datasets(None, write.datasets)
                merged_handling = write.handling
                audit = AuditStub(
                    created_at=write.created_at,
                    created_by=write.created_by,
                    revision=write.writes,
                    load_id=write.load_id,
                    recipe_id=write.recipe_id,
                    recipe_version=write.recipe_version,
                )

            weight, components = await self._weigh_edge(
                type_name,
                write,
                merged_occurrences=merged_occurrences,
                merged_interval=merged_interval,
                now=now,
                session_id=tx,
                corpus_total=corpus_totals.get(type_name),
            )
            # `corpus_total_occurrences` is the total with this write's delta in it, which is what
            # the store would answer for the next edge of this type once this one is written.
            corpus_totals[type_name] = components.corpus_total_occurrences
            merged_write = write.model_copy(
                update={
                    "properties": merged_properties,
                    "occurrences": merged_occurrences,
                    "interval": merged_interval,
                    "provenance": merged_provenance,
                    "datasets": merged_datasets,
                    "handling": merged_handling,
                }
            )
            props = edge_write_to_properties(
                merged_write,
                edge_id=edge_id,
                audit=audit,
                edge_type=edge_type,
                weight=weight,
                weight_components=components,
            )
            # Bound Gremlin/Groovy variable names are prefixed: TinkerPop
            # statically imports `T.id`/`T.label` as bare `id`/`label` in
            # this scripting context, so a parameter literally named `id`
            # silently resolves to that enum instead of the bound value.
            bound_params = {f"prop_{key}": value for key, value in props.items()}
            _date_keys = {"valid_from", "valid_to"}
            property_steps = "".join(
                f".property({key!r}, new Date(prop_{key}))"
                if key in _date_keys
                else f".property({key!r}, prop_{key})"
                for key in props
            )
            if existing is not None:
                edge_lit = groovy_string_literal(edge_id)
                command = f'g.E().has("id",{edge_lit}){property_steps}'
                await self._client.gremlin(command, params=bound_params, session_id=tx)
                if merged_interval is not None and merged_interval.valid_to is None:
                    # ADR-127 decision 11: a merge that leaves the span open writes no flattened
                    # `valid_to`, so the closed write's own would stay, a wrong end for the next
                    # reader. Removed by SQL on the type, through its unique `id` index, in the same
                    # transaction as the update above.
                    await self._client.sql(
                        f"UPDATE `{type_name}` REMOVE valid_to WHERE id = :id",
                        params={"id": edge_id},
                        session_id=tx,
                    )
            else:
                command = (
                    f'g.V().has("id", src).as("__src")'
                    f'.V().has("id", tgt)'
                    f'.addE("{type_name}").from("__src"){property_steps}'
                )
                await self._client.gremlin(
                    command,
                    params={"src": write.source, "tgt": write.target, **bound_params},
                    session_id=tx,
                )
            ids.append(edge_id)
        return ids

    async def bulk_load_edges(
        self,
        edges: Sequence[EdgeWrite],
        *,
        chunk_size: int = 500,
        progress: Callable[[int, int], None] | None = None,
    ) -> BulkEdgeResult:
        """`ports.graph.BulkGraphLoader` (ADR-058): the contract is stated there, the logic is
        `bulk.BulkEdgeLoader`'s. No `TxId`: it commits in chunks of its own."""
        return await self._bulk.load(
            self._require_schema(), edges, chunk_size=chunk_size, progress=progress
        )

    async def _weigh_edge(
        self,
        type_name: str,
        write: EdgeWrite,
        *,
        merged_occurrences: int,
        merged_interval: Interval | None,
        now: datetime,
        session_id: TxId,
        corpus_total: int | None = None,
    ) -> tuple[float, WeightComponents]:
        """`01_DOMAIN_MODEL.md` §6.1. `merged_occurrences` already reflects
        this write; the corpus-wide degree/total queries do not yet, since
        the store has not been updated at the point they run — so this
        write's own delta (`write.occurrences`) is added to each below."""
        source_degree, target_degree, corpus_total = await self._corpus_edge_stats(
            type_name, write.source, write.target, session_id=session_id, corpus_total=corpus_total
        )
        delta = write.occurrences
        # A link from a node to itself is read back twice from that node (`bothE`), so the stored
        # degree already counts a stored loop's occurrences twice and this write's must be added
        # twice too, as the bulk loader counts it (ADR-120 Amendment 4). The type's total counts
        # each edge once.
        self_loop = write.source == write.target
        degree_delta = 2 * delta if self_loop else delta
        components = WeightComponents(
            occurrences=merged_occurrences,
            corpus_pair_count=merged_occurrences,
            corpus_source_degree=source_degree + degree_delta,
            corpus_target_degree=target_degree + degree_delta,
            corpus_total_occurrences=corpus_total + delta,
            computed_at=now,
            parameter_set=self._weight_rules.parameter_set(write.type),
        )
        weight = compute_weight(
            components,
            edge_type=write.type,
            valid_to=merged_interval.valid_to if merged_interval else None,
            now=now,
            rules=self._weight_rules,
            self_loop=self_loop,
        )
        return weight, components

    # --- reads -----------------------------------------------------------

    async def get_node(
        self, node_id: NodeId, principal: Principal, *, include_superseded: bool = False
    ) -> Node | None:
        query = GetNodeBuilder(node_id, include_superseded=include_superseded).render_gremlin(
            self._access, principal
        )
        results = await self._client.gremlin(query)
        if not results:
            return None
        return node_from_element_map(results[0], principal)

    async def _types_with_unique_id(self, kind: str) -> list[str]:
        """The stored types of `kind` (`"vertex"` or `"edge"`) a lookup by id can ask, from the
        store itself on every call (ADR-124 Amendment 2): exactly those that carry a unique index
        on `id` alone. Not this process's applied ontology: a link type another process created
        since (a proposal's own storage type) would be left out, and its links would read as
        absent. A type without that index is not asked, since asking would scan it."""
        types = await self._client.sql("SELECT name, type, indexes FROM schema:types")
        return [
            t["name"]
            for t in types
            if t.get("type") == kind
            and any(
                i.get("unique") is True and i.get("properties") == ["id"]
                for i in t.get("indexes") or []
            )
        ]

    async def _record_ids(self, type_names: Sequence[str], ids: list[str]) -> list[str]:
        """The record ids of the elements holding `ids`, over each stored type in `type_names`
        (ADR-124 decision 6). One SQL query per type, run together: a type's own unique `id` index
        answers it, which Gremlin's `has("id", within(...))` does not (it scans the store). The
        ids are bound as `:ids`. Nothing here is access-filtered and nothing leaves the adapter:
        the Gremlin step that follows is what applies the access step. Every type asked exists,
        so there is no missing type to read as no rows: any error is raised."""
        found = await asyncio.gather(
            *(
                self._client.sql(render_record_id_lookup_sql(t), params={"ids": ids})
                for t in type_names
            )
        )
        rids: list[str] = []
        for rows in found:
            for row in rows:
                rid = row.get("rid")
                if not isinstance(rid, str) or not _RECORD_ID.match(rid):
                    raise ValueError(f"not an ArcadeDB record id: {rid!r}")
                rids.append(rid)
        return rids

    async def get_nodes(self, node_ids: Sequence[NodeId], principal: Principal) -> list[Node]:
        found: dict[str, Node] = {}
        chunks = _id_chunks(node_ids)
        types = await self._types_with_unique_id("vertex") if chunks else []
        for chunk in chunks:
            rids = await self._record_ids(types, chunk)
            # Sent even when no id resolved: an absent id must cost what a hidden one costs.
            query = render_get_nodes_gremlin(rids, self._access, principal)
            for record in await self._client.gremlin(query):
                node = node_from_element_map(record, principal)
                found[node.id] = node
        return [found[node_id] for node_id in sorted(found)]

    async def existing_node_ids(self, node_ids: Sequence[NodeId]) -> set[NodeId]:
        found: set[NodeId] = set()
        chunks = _id_chunks(node_ids)
        types = await self._types_with_unique_id("vertex") if chunks else []
        for chunk in chunks:
            rows = await asyncio.gather(
                *(
                    self._client.sql(render_live_node_ids_sql(t), params={"ids": chunk})
                    for t in types
                )
            )
            found.update(str(row["id"]) for result in rows for row in result)
        return found

    async def get_edges(self, edge_ids: Sequence[EdgeId], principal: Principal) -> list[Edge]:
        found: dict[str, Edge] = {}
        chunks = _id_chunks(edge_ids)
        types = await self._types_with_unique_id("edge") if chunks else []
        for chunk in chunks:
            rids = await self._record_ids(types, chunk)
            # Sent even when no id resolved, as above.
            query = render_get_edges_gremlin(rids, self._access, principal)
            for record in await self._client.gremlin(query):
                edge = edge_from_element_map(record, principal)
                found[edge.id] = edge
        return [found[edge_id] for edge_id in sorted(found)]

    async def find_node(
        self,
        entity_type: str,
        identifier_field: str,
        value: str,
        principal: Principal,
        *,
        also: Mapping[str, str] | None = None,
    ) -> Node | None:
        # `also` names properties that are not stored top-level (an Endpoint's kind), so they
        # cannot be asked for in the query: the visible nodes sharing the value are read, one past
        # the bound, and the first carrying them is taken. One past, so that overflowing is
        # knowable: more than the bound read with no match is `FindLimitExceeded`, never `None`
        # (rule 2), since an unread node might match. Without `also`, one node is read.
        query = FindByIdentifierBuilder(
            entity_type, identifier_field, value, limit=FIND_WITH_ALSO_LIMIT + 1 if also else 1
        ).render_gremlin(self._access, principal)
        results = await self._client.gremlin(query)
        for element in results:
            node = node_from_element_map(element, principal)
            if all(str(node.properties.get(k)) == v for k, v in (also or {}).items()):
                return node
        if also and len(results) > FIND_WITH_ALSO_LIMIT:
            raise FindLimitExceeded(entity_type, identifier_field, FIND_WITH_ALSO_LIMIT)
        return None

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        schema = self._require_schema()
        # **Declared identifiers, plus every property the ontology marks `indexed: true`** —
        # round 13cd, and the second half is the fix.
        #
        # `identifiers:` is a list of *property names* for `Person` (`nino`), `Device` (`imei`),
        # `Location` (`postcode`) and `Organisation` (`org_ref`), and searching them works. For
        # `Endpoint` it is not: `01_DOMAIN_MODEL.md` declares `identifiers: [e164, handle, email,
        # imsi]`, which are identifier **kinds**, while the value always lives in
        # `value_normalised` and the kind in `endpoint_kind`. The two lists do not even agree —
        # `endpoint_kind`'s enum says `msisdn` where `identifiers` says `e164`.
        #
        # **Nothing in this repository has ever written an `e164` property**, checked directly, so
        # every ingested or seeded `Endpoint` was invisible to search: an analyst could load a
        # number and then not find it. Measured over the wire in REPORT-13bf — `POST /v1/search`
        # for `+441621926368` returned 0 hits after a load that demonstrably created it.
        #
        # `indexed: true` is the ontology's own statement that a property is one you look things
        # up by, which is exactly what an index is for, so it is the right second source rather
        # than a special case naming `Endpoint`. A new type gets searchable identifiers by
        # declaring them, with no change here.
        #
        # **A stated consequence, not an accident:** `Location.name` is also `indexed: true`, so
        # an exact search for a location's name now returns it. That is a legitimate hit rather
        # than a leak — the access filter below applies unchanged, and `suggest_locations` remains
        # the separate prefix-search route.
        searchable_fields = {
            field for entity in schema.entity_types for field in entity.identifiers
        }
        searchable_fields |= {
            prop.name
            for entity in schema.entity_types
            for prop in entity.properties
            if prop.indexed
        }
        identifier_fields = tuple(sorted(searchable_fields))
        if not identifier_fields:
            return []
        builder = SearchNodesBuilder(identifier_fields, query, limit=limit)
        results = await self._client.gremlin(builder.render_gremlin(self._access, principal))
        return [node_from_element_map(r, principal) for r in results]

    async def suggest_locations(
        self, name: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        builder = SuggestLocationsBuilder(name, limit=limit)
        results = await self._client.gremlin(builder.render_gremlin(self._access, principal))
        return [node_from_element_map(r, principal) for r in results]

    async def suggest_nodes(
        self,
        prefix: str,
        principal: Principal,
        *,
        limit: int = 10,
        options: SuggestOptions | None = None,
    ) -> NodeSuggestions:
        if not prefix:
            raise ValueError("suggest_nodes needs a prefix: an empty one is a scan of every vertex")
        options = options or SuggestOptions()
        labels, fields = suggestion_scope(self._require_schema(), options.types)
        if not labels:
            return NodeSuggestions()
        builder = SuggestNodesBuilder(
            labels,
            fields,
            prefix,
            limit=limit,
            mode=options.mode,
            ignore_case=options.ignore_case,
        )
        results = await self._client.gremlin(builder.render_gremlin(self._access, principal))
        nodes = [node_from_element_map(r, principal) for r in results]
        return NodeSuggestions(nodes=nodes[:limit], more=len(nodes) > limit)

    async def vault_subgraph(
        self, principal: Principal, *, max_nodes: int, max_edges: int
    ) -> Subgraph:
        """ADR-057 stage 3. Not implemented yet, on purpose: the port's conformance cases come first
        (`CLAUDE.md` rule 1), and this must fail loudly, never return an empty graph."""
        raise NotImplementedError(
            "vault_subgraph is ADR-057 stage 3; its conformance cases come first"
        )

    async def list_nodes(
        self,
        entity_type: str,
        principal: Principal,
        *,
        cursor: NodeId | None = None,
        limit: int = 500,
    ) -> ListNodesPage:
        builder = ListNodesBuilder(entity_type, cursor, limit)
        results = await self._client.gremlin(builder.render_gremlin(self._access, principal))
        nodes = [node_from_element_map(r, principal) for r in results]
        # A short page is not itself proof of exhaustion (the port's own
        # docstring): only ask for one more than requested to know whether
        # a further page exists would need a second query, so instead the
        # correct signal is "this page came back full" — a page shorter
        # than `limit` cannot be followed by more of *this* entity type
        # under keyset-on-id ordering, since every remaining node's id is
        # necessarily greater than every id already returned.
        next_cursor = nodes[-1].id if len(nodes) == limit else None
        return ListNodesPage(nodes=nodes, next_cursor=next_cursor)

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        builder = ExpandBuilder(req)
        seed_records = await self._client.gremlin(
            builder.render_seed_nodes_gremlin(self._access, principal)
        )
        node_records = await self._client.gremlin(
            builder.render_nodes_gremlin(self._access, principal)
        )
        edge_records = await self._client.gremlin(
            builder.render_edges_gremlin(self._access, principal)
        )
        nodes_by_id = {
            r["id"]: node_from_element_map(r, principal) for r in (*seed_records, *node_records)
        }
        return Subgraph(
            nodes=list(nodes_by_id.values()),
            edges=[edge_from_element_map(r, principal) for r in edge_records],
        )

    async def edges_among(
        self,
        node_ids: Sequence[str],
        principal: Principal,
        edge_types: list[str] | None = None,
    ) -> list[Edge]:
        if len(set(node_ids)) < 2:
            return []
        records = await self._client.gremlin(
            render_edges_among_gremlin(sorted(set(node_ids)), self._access, principal, edge_types)
        )
        return [edge_from_element_map(r, principal) for r in records]

    async def paths(self, req: PathRequest, principal: Principal) -> list[Path]:
        query = PathBuilder(req).render_gremlin(self._access, principal)
        if query is None:
            return []
        results = await self._client.gremlin(query)
        return await self._hydrate_paths([record["result"] for record in results], principal)

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
        builder = RoutesAtLengthBuilder(
            source, target, length, limit, tuple(edge_types) if edge_types is not None else None
        )
        query = builder.render_gremlin(self._access, principal)
        if query is None:
            return RoutesAtLength(length=length, paths=[], more=False)
        raw_paths: list[list[str]] = [r["result"] for r in await self._client.gremlin(query)]
        return RoutesAtLength(
            length=length,
            paths=await self._hydrate_paths(raw_paths[:limit], principal),
            more=len(raw_paths) > limit,
        )

    async def _hydrate_paths(self, raw_paths: list[list[str]], principal: Principal) -> list[Path]:
        """Each found path's alternating node and link ids, as full nodes and links."""
        if not raw_paths:
            return []

        # `06_DECISIONS.md` ADR-033: hydrate every distinct id across every found path in two
        # batch queries (nodes, edges), not per-path or per-step — bounded by k*max_hops, tiny
        # against the working-set scale every other builder here is sized for.
        all_node_ids = sorted({node_id for steps in raw_paths for node_id in steps[0::2]})
        all_edge_ids = sorted({edge_id for steps in raw_paths for edge_id in steps[1::2]})
        node_query = PathBuilder.render_hydrate_nodes_gremlin(all_node_ids, self._access, principal)
        node_results = await self._client.gremlin(node_query)
        nodes_by_id = {r["id"]: node_from_element_map(r, principal) for r in node_results}
        edges_by_id: dict[EdgeId, Edge] = {}
        if all_edge_ids:
            edge_query = PathBuilder.render_hydrate_edges_gremlin(
                all_node_ids, all_edge_ids, self._access, principal
            )
            edge_results = await self._client.gremlin(edge_query)
            edges_by_id = {r["id"]: edge_from_element_map(r, principal) for r in edge_results}

        paths: list[Path] = []
        for steps in raw_paths:
            node_ids = steps[0::2]
            edge_ids = steps[1::2]
            paths.append(
                Path(
                    nodes=[nodes_by_id[i] for i in node_ids],
                    edges=[edges_by_id[i] for i in edge_ids],
                    length=len(edge_ids),
                )
            )
        return paths

    def _check_conditions(self, pattern: PatternQuery) -> None:
        """ADR-121: a condition the applied ontology refuses (an unindexed or `sensitivity: high`
        property, an unknown one) raises `PatternConditionRefused`, by name, before anything is
        compiled: the route checks first to tell the analyst, and this holds for every other caller
        of the port (a monitor, a typology rule) all the same."""
        if any(node.where for node in pattern.nodes):
            check_pattern_conditions(pattern, self._require_schema())

    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph:
        self._check_conditions(pattern)
        query = MatchBuilder(pattern).render_gremlin(self._access, principal)
        results = await self._client.gremlin(query)
        # One element map per node, each once (`MatchBuilder._nodes_tail`).
        nodes = {node.id: node for node in (node_from_element_map(r, principal) for r in results)}
        return Subgraph(nodes=list(nodes.values()), edges=[])

    async def match_count(
        self, pattern: PatternQuery, principal: Principal, *, ceiling: int
    ) -> int:
        self._check_conditions(pattern)
        query = MatchBuilder(pattern).render_count_gremlin(self._access, principal, ceiling=ceiling)
        results = await self._client.gremlin(query)
        if not results:
            return 0
        return int(results[0].get("result") or 0)

    async def neighbourhood_stats(
        self, node_id: NodeId, principal: Principal
    ) -> NeighbourhoodStats:
        query = NeighbourhoodStatsBuilder(node_id).render_gremlin(self._access, principal)
        results = await self._client.gremlin(query)
        raw_degree_by_type: dict[str, int] = results[0] if results else {}
        degree_by_type = {
            logical_type_name(label): count for label, count in raw_degree_by_type.items()
        }
        return NeighbourhoodStats(
            node_id=node_id,
            degree=sum(degree_by_type.values()),
            degree_by_type=degree_by_type,
        )

    async def type_counts(self, principal: Principal) -> TypeCounts:
        nodes_query, edges_query = render_type_counts_gremlin(self._access, principal)
        return TypeCounts(
            nodes=_logical_counts(await self._client.gremlin(nodes_query)),
            edges=_logical_counts(await self._client.gremlin(edges_query)),
        )

    async def most_connected(
        self,
        principal: Principal,
        *,
        entity_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> RankedNodes:
        builder = MostConnectedBuilder(entity_type, limit, offset)
        totals = await self._client.gremlin(builder.render_total_gremlin(self._access, principal))
        rows = await self._client.gremlin(builder.render_page_gremlin(self._access, principal))
        return RankedNodes(
            nodes=[
                RankedNode(
                    node=node_from_element_map(r["node"], principal), degree=int(r["degree"])
                )
                for r in rows
            ],
            total=int(totals[0].get("result") or 0),
            offset=offset,
        )

    async def busiest_links(
        self,
        principal: Principal,
        *,
        edge_type: str | None = None,
        limit: int = 10,
        offset: int = 0,
        node_id: str | None = None,
    ) -> RankedLinks:
        builder = BusiestLinksBuilder(edge_type, limit, offset, node_id)
        totals = await self._client.gremlin(builder.render_total_gremlin(self._access, principal))
        rows = await self._client.gremlin(builder.render_page_gremlin(self._access, principal))
        return RankedLinks(
            links=[
                RankedLink(
                    edge=edge_from_element_map(r["edge"], principal),
                    source=node_from_element_map(r["source"], principal),
                    target=node_from_element_map(r["target"], principal),
                )
                for r in rows
            ],
            total=int(totals[0].get("result") or 0),
            offset=offset,
        )

    def _merge_handling(self, existing: dict[str, Any], incoming: Handling) -> Handling:
        """ADR-102: a write onto an element already stored never lowers its handling."""
        return merge_handling(Handling.model_validate(existing["handling"]), incoming, self._scheme)

    async def recent_loads(self, principal: Principal, *, limit: int = 10) -> RecentLoads:
        nodes_query, links_query = render_recent_loads_gremlin(self._access, principal)
        merged: dict[str, dict[str, Any]] = {}
        for kind, query in (("nodes", nodes_query), ("links", links_query)):
            rows = await self._client.gremlin(query)
            for load, held in (rows[0] if rows else {}).items():
                into = merged.setdefault(
                    load, {"nodes": 0, "links": 0, "latest": None, "recipe": "", "version": -1}
                )
                into[kind] = int(held["n"])
                latest = datetime.fromisoformat(str(held["latest"]))
                if into["latest"] is None or latest > into["latest"]:
                    into["latest"] = latest
                into["recipe"] = into["recipe"] or held.get("recipe") or ""
                if into["version"] in (None, -1):
                    into["version"] = held.get("version")
        loads = [
            LoadSummary(
                load_id=load or None,
                recipe_id=held["recipe"] or None,
                recipe_version=None if held["version"] in (None, -1) else int(held["version"]),
                nodes=held["nodes"],
                links=held["links"],
                latest=held["latest"],
            )
            for load, held in merged.items()
        ]
        loads.sort(key=lambda s: (-s.latest.timestamp(), s.load_id or ""))
        return RecentLoads(loads=loads[:limit], total=len(loads))

    async def recently_confirmed(
        self, principal: Principal, *, limit: int = 10
    ) -> RecentlyConfirmed:
        count_query, page_query = render_recently_confirmed_gremlin(
            self._access, principal, limit=limit
        )
        (counted,) = await self._client.gremlin(count_query)
        return RecentlyConfirmed(
            nodes=[
                ConfirmedNode(
                    node=node_from_element_map(r["node"], principal),
                    confirmed_at=datetime.fromisoformat(str(r["at"])),
                    confirmed_by=str(r["by"]),
                )
                for r in await self._client.gremlin(page_query)
            ],
            total=int(counted.get("result") or 0),
        )

    async def shared_contacts(
        self,
        node_id: NodeId,
        principal: Principal,
        *,
        edge_type: str,
        min_shared: int = 2,
        limit: int = 10,
    ) -> SharedContacts:
        count_query, page_query = render_shared_contacts_gremlin(
            self._access,
            principal,
            node_id,
            edge_type=edge_type,
            min_shared=min_shared,
            limit=limit,
        )
        (counted,) = await self._client.gremlin(count_query)
        page = await self._client.gremlin(page_query)
        shared = {str(r["id"]): int(r["n"]) for r in page}
        contact_records = (
            await self._client.gremlin(
                f'g.V().has("id",within({groovy_string_list_literal(list(shared))}))'
                f".{self._access.gremlin_has_step(principal)}.elementMap()"
            )
            if shared
            else []
        )
        nodes = {
            node.id: node for node in (node_from_element_map(r, principal) for r in contact_records)
        }
        return SharedContacts(
            contacts=[
                SharedContact(node=nodes[i], shared=n) for i, n in shared.items() if i in nodes
            ],
            total=int(counted.get("result") or 0),
        )

    async def link_structure(
        self, principal: Principal, *, max_nodes: int, max_edges: int
    ) -> LinkStructure:
        queries = render_link_structure_gremlin(self._access, principal)
        (counted,) = await self._client.gremlin(queries["node_count"])
        nodes = int(counted.get("result") or 0)
        if nodes > max_nodes:
            raise SubgraphTooLarge(nodes=nodes, edges=None)
        (counted,) = await self._client.gremlin(queries["edge_count"])
        edges = int(counted.get("result") or 0)
        if edges > max_edges:
            raise SubgraphTooLarge(nodes=nodes, edges=edges)
        return LinkStructure(
            nodes=[
                StructureNode(id=str(r["id"]), type=logical_type_name(str(r["type"])))
                for r in await self._client.gremlin(queries["nodes"])
            ],
            edges=[
                StructureEdge(
                    id=str(r["id"]), source=str(r["s"]), target=str(r["t"]), weight=float(r["w"])
                )
                for r in await self._client.gremlin(queries["edges"])
            ],
        )

    # --- schema ------------------------------------------------------------

    async def apply_schema(self, schema: OntologySchema) -> SchemaReport:
        report = await _apply_schema_ddl(self._client, schema)
        self.use_schema(schema)
        return report

    def use_schema(self, schema: OntologySchema) -> None:
        """Takes `schema` in memory only, as `apply_schema` leaves the adapter, and sends the store
        nothing: no DDL, no backfill. For a read-only caller (the seed's `--check`) that needs to
        read a type and resolve a link's stored name without writing to the deployment."""
        # ADR-090 Amendment 1: the old names a type answers to, and each proposal's own storage
        # label (its links read as the name it is an alias of).
        aliases: dict[str, list[str]] = {t.name: list(t.aliases) for t in schema.edge_types}
        for storage, logical in schema.storage_aliases.items():
            aliases.setdefault(logical, []).append(storage)
        set_edge_aliases(aliases)
        self._schema = schema
        self._schema_history[schema.version] = schema

    async def revert_schema(self, to_version: int) -> SchemaReport:
        target = self._schema_history.get(to_version)
        if target is None:
            raise OntologyError(
                f"cannot revert to version {to_version}: no schema at that version has been "
                "applied in this adapter's lifetime"
            )
        current = self._require_schema()
        stale_entities = {e.name for e in current.entity_types} - {
            e.name for e in target.entity_types
        }
        stale_edges = {e.name for e in current.edge_types} - {e.name for e in target.edge_types}
        if stale_entities or stale_edges:
            partial = OntologySchema(
                version=current.version,
                entity_types=[e for e in current.entity_types if e.name in stale_entities],
                edge_types=[e for e in current.edge_types if e.name in stale_edges],
            )
            await _drop_schema_ddl(self._client, partial)

        report = await _apply_schema_ddl(self._client, target)
        self._schema = target
        return report

    # --- revert ------------------------------------------------------------

    async def revert_elements(
        self, node_ids: Sequence[NodeId], edge_ids: Sequence[EdgeId], tx: TxId
    ) -> None:
        # Resolved first, written after: an id two types of one kind hold cannot be told apart (a
        # load's record keeps no types), and the call is refused before any of it is written.
        # Nodes are looked up among the vertex types only and links among the edge types only, so
        # a node id that is also a link's id reverts the node alone. Each id is found through its
        # type's unique `id` index and set by SQL on that type, in chunks (`has("id", within(...))`
        # scans the store, and `g.E()` matches a link of any type). Setting the flag again on an
        # element is harmless, which is what lets a rerun repeat a chunk.
        plan = [
            *[("node", t, ids) for t, ids in await self._holders("vertex", node_ids, tx)],
            *[("link", t, ids) for t, ids in await self._holders("edge", edge_ids, tx)],
        ]
        for _, type_name, ids in plan:
            await self._client.sql(
                f"UPDATE `{groovy_identifier(type_name)}` SET reverted = true WHERE id IN :ids",
                params={"ids": ids},
                session_id=tx,
            )

    async def _holders(
        self, kind: str, ids: Sequence[str], tx: TxId | None = None
    ) -> list[tuple[str, list[str]]]:
        """For `ids`, the stored types of `kind` ("vertex" or "edge") that hold them, as (type, ids)
        in chunks of the adapter's size, each type's ids found from its unique `id` index. An id
        held by two types raises `AmbiguousElementId`, naming how many, never which."""
        chunks = _id_chunks(ids)
        if not chunks:
            return []
        types = await self._types_with_unique_id(kind)
        held: dict[str, list[str]] = {}
        owner: dict[str, str] = {}
        ambiguous: set[str] = set()
        for chunk in chunks:
            found = await asyncio.gather(
                *(
                    self._client.sql(
                        render_existing_ids_sql(t), params={"ids": chunk}, session_id=tx
                    )
                    for t in types
                )
            )
            for type_name, rows in zip(types, found, strict=True):
                for row in rows:
                    node_id = str(row["id"])
                    if node_id in owner and owner[node_id] != type_name:
                        ambiguous.add(node_id)
                    owner[node_id] = type_name
                    held.setdefault(type_name, []).append(node_id)
        if ambiguous:
            raise AmbiguousElementId("node" if kind == "vertex" else "link", len(ambiguous))
        return [
            (type_name, chunk)
            for type_name, found_ids in held.items()
            for chunk in _id_chunks(found_ids)
        ]

    async def live_edges_touching(self, node_ids: Sequence[NodeId]) -> set[EdgeId]:
        found: set[EdgeId] = set()
        types = None
        for chunk in _id_chunks(node_ids):
            types = types if types is not None else await self._types_with_unique_id("vertex")
            rids = await self._record_ids(types, chunk)
            if not rids:
                continue
            # By record id, not by `has("id", ...)`: the node is read from its index, and only its
            # own links are walked. Live links only: neither reverted nor superseded, as every read.
            ids_literal = groovy_string_list_literal(rids)
            rows = await self._client.gremlin(
                f'g.V({ids_literal}).bothE().has("reverted",false).hasNot("superseded_by").values("id")'
            )
            found.update(str(row["result"]) for row in rows)
        return found

    async def live_nodes_naming_geometry(
        self, geometry_refs: Sequence[str]
    ) -> dict[str, set[NodeId]]:
        named: dict[str, set[NodeId]] = {}
        chunks = _id_chunks(geometry_refs)
        types = await self._types_with_unique_id("vertex") if chunks else []
        for chunk in chunks:
            # `geometry_ref` is an unindexed property, held in the node's `properties` map, so this
            # reads each vertex type's own rows: an operator's lookup at revert, not a read path.
            results = await asyncio.gather(
                *(
                    self._client.sql(
                        f"SELECT id, properties.geometry_ref AS ref "
                        f"FROM `{groovy_identifier(t)}` WHERE properties.geometry_ref IN :refs "
                        "AND (reverted = false OR reverted IS NULL) AND superseded_by IS NULL",
                        params={"refs": chunk},
                    )
                    for t in types
                )
            )
            for rows in results:
                for row in rows:
                    named.setdefault(str(row["ref"]), set()).add(str(row["id"]))
        return named

    async def stored_writes(self, node_ids: Sequence[NodeId]) -> dict[NodeId, StoredNode]:
        found: dict[NodeId, StoredNode] = {}
        chunks = _id_chunks(node_ids)
        types = await self._types_with_unique_id("vertex") if chunks else []
        for chunk in chunks:
            results = await asyncio.gather(
                *(
                    self._client.sql(
                        f"SELECT id, audit.load_id AS load_id, reverted, superseded_by "
                        f"FROM `{groovy_identifier(t)}` WHERE id IN :ids",
                        params={"ids": chunk},
                    )
                    for t in types
                )
            )
            for rows in results:
                for row in rows:
                    load_id = row.get("load_id")
                    found[str(row["id"])] = StoredNode(
                        load_id=None if load_id is None else str(load_id),
                        reverted=row.get("reverted") is True,
                        superseded=row.get("superseded_by") is not None,
                    )
        return found

    async def stored_link_states(self, edge_ids: Sequence[EdgeId]) -> dict[EdgeId, StoredLink]:
        gathered: dict[EdgeId, list[tuple[bool, bool]]] = {}
        chunks = _id_chunks(edge_ids)
        types = await self._types_with_unique_id("edge") if chunks else []
        for chunk in chunks:
            results = await asyncio.gather(
                *(
                    self._client.sql(
                        f"SELECT id, reverted, superseded_by "
                        f"FROM `{groovy_identifier(t)}` WHERE id IN :ids",
                        params={"ids": chunk},
                    )
                    for t in types
                )
            )
            for rows in results:
                for row in rows:
                    gathered.setdefault(str(row["id"]), []).append(
                        (row.get("reverted") is True, row.get("superseded_by") is not None)
                    )
        # An id two types hold is read as the worst of them: superseded if either copy is,
        # reverted only if both are, so the revert refuses when in doubt.
        return {
            edge_id: StoredLink(
                reverted=all(r for r, _ in states), superseded=any(sup for _, sup in states)
            )
            for edge_id, states in gathered.items()
        }

    # --- one-off provenance rewrite -------------------------------------------

    async def strip_provenance_references(self, prefix: str) -> int:
        """ADR-124 decision 11: a scan of every link type in the store, by `id` in index order and
        in pages, with no access step and no superseded or reverted filter (this is not a read for
        a reader). A link changes only if one of its provenance entries has a `document_id` that
        starts with `prefix`; the entries are removed from the stored `provenance` and nothing else
        is written. Each page is read from the id after the last one seen, so a rewrite never moves
        a record under the cursor."""
        changed = 0
        types = await self._types_with_unique_id("edge")
        for type_name in types:
            quoted = groovy_identifier(type_name)
            after = ""
            rewritten: set[str] = set()
            while True:
                rows = await self._client.sql(
                    f"SELECT id, provenance FROM `{quoted}` WHERE id > :after_id "
                    f"ORDER BY id LIMIT {_STRIP_PAGE}",
                    params={"after_id": after},
                )
                if not rows:
                    break
                for row in rows:
                    stripped = _without_references(row.get("provenance"), prefix)
                    if stripped is not None and row["id"] not in rewritten:
                        rewritten.add(row["id"])
                        await self._client.sql(
                            f"UPDATE `{quoted}` SET provenance = :provenance WHERE id = :id",
                            params={"provenance": stripped, "id": row["id"]},
                        )
                        changed += 1
                after = rows[-1]["id"]
                if len(rows) < _STRIP_PAGE:
                    break
        return changed

    # --- supersession --------------------------------------------------------

    async def supersede_node(self, node_id: NodeId, replacement: NodeWrite, tx: TxId) -> NodeId:
        schema = self._require_schema()
        entity_type = schema.entity_type(replacement.type)
        if entity_type is None:
            raise OntologyError(f"{replacement.type!r} is not a type in the active ontology")
        validate_properties(entity_type, replacement.properties)

        node_lit = groovy_string_literal(node_id)
        # Unfiltered by design — an internal lookup during a trusted write,
        # the same as `_node_type`'s, not a principal-scoped read. It must
        # also find a node that is itself already superseded (the caller's
        # business whether that is sensible), so it never applies the
        # access filter's `hasNot("superseded_by")` step.
        existing_results = await self._client.gremlin(
            f'g.V().has("id",{node_lit}).elementMap()', session_id=tx
        )
        if not existing_results:
            raise OntologyError(f"cannot supersede {node_id!r}: no such node")
        existing_audit = AuditStub.model_validate(existing_results[0]["audit"])
        # ADR-099: a correction is the same element, so it keeps every dataset the old revision
        # was in, and any the replacement names besides.
        replacement = replacement.model_copy(
            update={
                "datasets": merge_datasets(
                    existing_results[0].get("datasets"), replacement.datasets
                )
            }
        )

        new_node_id = replacement.id
        new_audit = AuditStub(
            created_at=replacement.created_at,
            created_by=replacement.created_by,
            revision=existing_audit.revision + 1,
            load_id=replacement.load_id,
            recipe_id=replacement.recipe_id,
            recipe_version=replacement.recipe_version,
        )
        props = node_write_to_properties(
            replacement, node_id=new_node_id, audit=new_audit, entity_type=entity_type
        )
        type_name = groovy_identifier(physical_type_name(replacement.type))
        set_clause = ", ".join(f"{key} = :{key}" for key in props)
        await self._client.sql(
            f"INSERT INTO {type_name} SET {set_clause}", params=props, session_id=tx
        )

        new_id_lit = groovy_string_literal(new_node_id)
        await self._client.gremlin(
            f'g.V().has("id",{node_lit}).property("superseded_by", {new_id_lit})',
            session_id=tx,
        )

        await self._repoint_incident_edges(
            node_id, new_node_id, created_by=replacement.created_by, tx=tx
        )
        return new_node_id

    async def _repoint_incident_edges(
        self, old_node_id: NodeId, new_node_id: NodeId, *, created_by: str, tx: TxId
    ) -> None:
        """`superseded_by` only marks the old node invisible by default —
        it does nothing to the edges still recorded against it, and a
        correction must not silently disconnect the corrected node from
        its own network. An edge's endpoints are fixed at creation in
        ArcadeDB (confirmed empirically: `UPDATE ... SET out = ...`
        reports success but leaves `@out`/`@in` unchanged), so "re-point"
        means clone each incident edge onto the new node, with the same
        type, properties, occurrences, weight and provenance, and mark the
        original reverted — the same flag `revert_elements` uses, for the
        same reason: excluded from ordinary reads and from corpus-wide
        weight statistics, never deleted."""
        old_lit = groovy_string_literal(old_node_id)
        now = now_utc()

        out_edges = await self._client.gremlin(
            f'g.V().has("id",{old_lit}).outE().has("reverted",false).elementMap()',
            session_id=tx,
        )
        for edge_record in out_edges:
            await self._clone_edge_onto(
                edge_record,
                source=new_node_id,
                target=edge_record["target"],
                created_by=created_by,
                now=now,
                tx=tx,
            )

        in_edges = await self._client.gremlin(
            f'g.V().has("id",{old_lit}).inE().has("reverted",false).elementMap()',
            session_id=tx,
        )
        for edge_record in in_edges:
            await self._clone_edge_onto(
                edge_record,
                source=edge_record["source"],
                target=new_node_id,
                created_by=created_by,
                now=now,
                tx=tx,
            )

        if out_edges or in_edges:
            await self._client.gremlin(
                f'g.V().has("id",{old_lit}).bothE().has("reverted",false)'
                '.property("reverted", true)',
                session_id=tx,
            )

    async def _clone_edge_onto(
        self,
        edge_record: dict[str, Any],
        *,
        source: NodeId,
        target: NodeId,
        created_by: str,
        now: datetime,
        tx: TxId,
    ) -> EdgeId:
        edge_type_name = logical_type_name(edge_record["label"])
        edge_type = self._require_schema().edge_type(edge_type_name)
        if edge_type is None:  # pragma: no cover — the old edge already proves this type is valid
            raise OntologyError(f"{edge_type_name!r} is not a type in the active ontology")

        interval = None
        if edge_record.get("interval"):
            interval = Interval.model_validate(edge_record["interval"])
        # Cloned-edge ids are minted here, not supplied by `supersede_node`'s
        # caller: the Conduit provides one `replacement` for the node being
        # corrected, but has no way to know in advance how many edges are
        # incident to it or what their new ids should be — that set is
        # discovered only once this adapter reads the node's current
        # neighbourhood, mid-transaction. Still routed through the shared
        # generator (`conduit_common.identity`) rather than a bare `ULID()`
        # call, so there is exactly one place that mints identifiers.
        cloned_edge_id = new_edge_id()
        write = EdgeWrite(
            id=cloned_edge_id,
            type=edge_type_name,
            source=source,
            target=target,
            properties=edge_record.get("properties") or {},
            interval=interval,
            occurrences=edge_record.get("occurrences", 1),
            # ADR-081 step B: a correction to the node does not change what stood behind the link.
            basis=edge_record.get("basis"),
            provenance=Provenance.model_validate(edge_record["provenance"]),
            handling=Handling.model_validate(edge_record["handling"]),
            created_by=created_by,
            created_at=now,
            datasets=list(edge_record.get("datasets") or []),
        )
        audit = AuditStub(created_at=now, created_by=created_by, revision=1)
        weight_components = WeightComponents.model_validate(edge_record["weight_components"])
        props = edge_write_to_properties(
            write,
            edge_id=cloned_edge_id,
            audit=audit,
            edge_type=edge_type,
            weight=edge_record.get("weight", 0.0),
            weight_components=weight_components,
        )
        type_name = groovy_identifier(physical_type_name(edge_type_name))
        bound_params = {f"prop_{key}": value for key, value in props.items()}
        date_keys = {"valid_from", "valid_to"}
        property_steps = "".join(
            f".property({key!r}, new Date(prop_{key}))"
            if key in date_keys
            else f".property({key!r}, prop_{key})"
            for key in props
        )
        command = (
            f'g.V().has("id", src).as("__src")'
            f'.V().has("id", tgt)'
            f'.addE("{type_name}").from("__src"){property_steps}'
        )
        await self._client.gremlin(
            command, params={"src": source, "tgt": target, **bound_params}, session_id=tx
        )
        return cloned_edge_id

    async def supersede_edge(self, edge_id: EdgeId, replacement: EdgeWrite, tx: TxId) -> EdgeId:
        """Unlike `supersede_node`, nothing needs repointing: nothing in
        this domain model references an edge by id except an assessment's
        evidence list (`01_DOMAIN_MODEL.md` §5), which is expected to
        follow `superseded_by`, not be silently kept pointing at stale
        content."""
        if replacement.writes != 1:
            # Only `upsert_edges` folds writes (ADR-127 Amendment 19): a replacement's revision is
            # its predecessor's plus one, so a count it could not honour is refused, not ignored.
            raise OntologyError(
                f"a replacement edge stands for one write, not {replacement.writes}"
            )
        schema = self._require_schema()
        edge_type = schema.edge_type(replacement.type)
        if edge_type is None:
            raise OntologyError(f"{replacement.type!r} is not a type in the active ontology")
        validate_properties(edge_type, replacement.properties)

        edge_lit = groovy_string_literal(edge_id)
        existing_results = await self._client.gremlin(
            f'g.E().has("id",{edge_lit}).elementMap()', session_id=tx
        )
        if not existing_results:
            raise OntologyError(f"cannot supersede {edge_id!r}: no such edge")
        existing_audit = AuditStub.model_validate(existing_results[0]["audit"])

        now = now_utc()
        # ADR-099: as for a node, the changed link keeps its datasets.
        replacement = replacement.model_copy(
            update={
                "datasets": merge_datasets(
                    existing_results[0].get("datasets"), replacement.datasets
                )
            }
        )
        replacement_edge_id = replacement.id
        new_audit = AuditStub(
            created_at=replacement.created_at,
            created_by=replacement.created_by,
            revision=existing_audit.revision + 1,
            load_id=replacement.load_id,
            recipe_id=replacement.recipe_id,
            recipe_version=replacement.recipe_version,
        )
        # The old link is marked first, so the replacement is weighed against counts that leave it
        # out: its occurrences live on in the replacement (ADR-120 Amendment 5).
        new_id_lit = groovy_string_literal(replacement_edge_id)
        await self._client.gremlin(
            f'g.E().has("id",{edge_lit}).property("superseded_by", {new_id_lit})',
            session_id=tx,
        )
        type_name = groovy_identifier(physical_type_name(replacement.type))
        weight, components = await self._weigh_edge(
            type_name,
            replacement,
            merged_occurrences=replacement.occurrences,
            merged_interval=replacement.interval,
            now=now,
            session_id=tx,
        )
        props = edge_write_to_properties(
            replacement,
            edge_id=replacement_edge_id,
            audit=new_audit,
            edge_type=edge_type,
            weight=weight,
            weight_components=components,
        )
        bound_params = {f"prop_{key}": value for key, value in props.items()}
        date_keys = {"valid_from", "valid_to"}
        property_steps = "".join(
            f".property({key!r}, new Date(prop_{key}))"
            if key in date_keys
            else f".property({key!r}, prop_{key})"
            for key in props
        )
        command = (
            f'g.V().has("id", src).as("__src")'
            f'.V().has("id", tgt)'
            f'.addE("{type_name}").from("__src"){property_steps}'
        )
        await self._client.gremlin(
            command,
            params={"src": replacement.source, "tgt": replacement.target, **bound_params},
            session_id=tx,
        )

        return replacement_edge_id


def _logical_counts(results: list[Any]) -> dict[str, int]:
    """A `groupCount().by(label())` by logical type name. Two storage labels of one type (an alias,
    ADR-090 Amendment 1) are one count."""
    counts: dict[str, int] = {}
    for label, count in (results[0] if results else {}).items():
        name = logical_type_name(label)
        counts[name] = counts.get(name, 0) + int(count)
    return counts
