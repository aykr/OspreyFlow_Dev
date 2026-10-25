"""Bulk edge loading for the ArcadeDB adapter (`ports.graph.BulkGraphLoader`, ADR-058).

`GraphArcadeDBAdapter.upsert_edges` costs about six store round trips per edge, each a separate
Groovy script (ADR-056 Amendments 22 to 24). This path does the same job for a *set* of edges that
arrives together: it validates everything first, aggregates repeated pairs by the one shared merge
rule, looks up what it needs in a few batched queries (never one per edge), computes every weight
against the corpus as it stands at the end of the load, and writes in chunks, each chunk in one
transaction through one script whose text never changes (the data travels as parameters, so the
server compiles it once, not once per edge).

**The logic and the transport are separate on purpose.** `BulkEdgeLoader` holds everything the
contract promises (validation, aggregation, collisions, weights, chunking) and talks to the store
only through `BulkTransport`. The tests drive the loader against an in-memory transport that
refuses what the real store refuses (an unknown label, an unvalidated edge); `GremlinBulkTransport`
is the one place that writes Gremlin, and the shapes it sends are **unproven against a real
ArcadeDB until `scripts/spike_bulk_transport.py` has run on an idle store** (ADR-058 D10): a double
cannot prove that a Groovy script runs. The spike sends exactly these shapes, from this module.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from conduit_common.identity import new_edge_id, now_utc
from ontology.errors import OntologyError
from ontology.handling import HandlingScheme, audience_of, audience_parts, merge_handling
from ontology.validation import validate_edge_endpoints, validate_properties
from ontology.weights import WeightRules, load_weight_rules
from ports.graph import BulkEdgeResult
from schemas.domain import AuditStub, EdgeWrite, OntologySchema, WeightComponents
from schemas.merge import AggregatedEdge, aggregate_edge_writes

from .builders import render_existing_ids_sql
from .client import ArcadeDBClient
from .gremlin_literals import groovy_identifier
from .naming import logical_type_name, physical_type_name
from .serialization import edge_write_to_properties
from .weight import compute_weight

#: How many ids go into one batched lookup. Bounded so a script's parameter list stays small.
LOOKUP_BATCH = 500


@dataclass(frozen=True)
class StoredLink:
    """A link already in the store, as far as the loader needs it: its ends and every part of its
    marking the access step reads, so the loader can tell whether a write has its audience."""

    source: str
    target: str
    classification: str
    handling_code: str
    originator: str
    owning_unit: str
    datasets: tuple[str, ...]


class BulkTransport(Protocol):
    """Everything the loader needs from the store, and nothing else. Every method takes a
    sequence of ids or rows, never one element: a per-element method would bring back the cost this
    path exists to remove."""

    async def vertex_labels(self, ids: Sequence[str]) -> dict[str, str]:
        """Physical label of each id that exists; an id with no vertex is absent."""
        ...

    async def edge_type_is_empty(self, label: str) -> bool: ...

    async def stored_links(
        self, label: str, pairs: Sequence[tuple[str, str]], *, directed: bool
    ) -> list[StoredLink]:
        """The live (not reverted) edges of `label` between any of `pairs`, as stored (source,
        target), each with what decides who may see it (ADR-102 Amendment 3). An undirected type's
        edge may be stored either way round, so it is looked for from either end, as
        `upsert_edges` does."""
        ...

    async def taken_edge_ids(self, label: str, ids: Sequence[str]) -> set[str]:
        """Which of `ids` an edge of `label` already holds, whatever its state (reverted or
        superseded included): edge `id` is UNIQUE per type, and an edge keeps its id for good."""
        ...

    async def corpus_total(self, label: str) -> int:
        """Total occurrences over every live edge of `label` (neither reverted nor superseded, as
        every read leaves them out; ADR-120 Amendment 5), reached as a traversal."""
        ...

    async def degrees(self, label: str, ids: Sequence[str]) -> dict[str, int]:
        """Weighted degree (occurrences over live edges of `label`, either end, neither reverted nor
        superseded; ADR-120 Amendment 5) of each id."""
        ...

    async def begin(self) -> str: ...

    async def commit(self, tx: str) -> None: ...

    async def rollback(self, tx: str) -> None: ...

    async def write_chunk(self, label: str, rows: Sequence[Mapping[str, Any]], tx: str) -> None:
        """Create one edge per row (`s`, `t`, `p`: source id, target id, properties)."""
        ...


@dataclass
class _Planned:
    aggregated: AggregatedEdge
    label: str
    directed: bool


class BulkEdgeLoader:
    def __init__(
        self,
        transport: BulkTransport,
        weight_rules: WeightRules | None = None,
        *,
        handling_scheme: HandlingScheme,
    ) -> None:
        self._transport = transport
        self._weight_rules = weight_rules or load_weight_rules()
        # ADR-102: a pair written twice in one load keeps the higher handling of the two.
        self._scheme = handling_scheme

    async def load(
        self,
        schema: OntologySchema,
        edges: Sequence[EdgeWrite],
        *,
        chunk_size: int = 500,
        progress: Callable[[int, int], None] | None = None,
    ) -> BulkEdgeResult:
        if chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")
        if not edges:
            return BulkEdgeResult()

        # 1. Everything that needs only the ontology, for every edge, before any read or write.
        directed_by_type: dict[str, bool] = {}
        for write in edges:
            edge_type = schema.edge_type(write.type)
            if edge_type is None:
                raise OntologyError(f"{write.type!r} is not a type in the active ontology")
            validate_properties(edge_type, write.properties)
            directed_by_type[write.type] = edge_type.directed

        # 2. Repeated pairs collapse by the shared merge rule.
        aggregated = aggregate_edge_writes(
            edges,
            directed=lambda t: directed_by_type[t],
            handling=lambda old, new: merge_handling(old, new, self._scheme),
            audience=lambda w: audience_of(w.handling, w.datasets, self._scheme),
        )

        # 3. Endpoints exist and fit the type, checked in batches before anything is written.
        await self._check_endpoints(schema, aggregated)

        planned = [
            _Planned(
                aggregated=a,
                label=groovy_identifier(physical_type_name(a.write.type)),
                directed=directed_by_type[a.write.type],
            )
            for a in aggregated
        ]

        # 4. A pair already stored is handed back, not written. An empty type has none to find.
        by_label: dict[str, list[_Planned]] = {}
        for item in planned:
            by_label.setdefault(item.label, []).append(item)
        collisions: list[EdgeWrite] = []
        to_write: dict[str, list[_Planned]] = {}
        baseline_total: dict[str, int] = {}
        for label, items in by_label.items():
            if await self._transport.edge_type_is_empty(label):
                to_write[label] = items
                baseline_total[label] = 0
                continue
            baseline_total[label] = await self._transport.corpus_total(label)
            stored = await self._stored_links(label, items, directed=items[0].directed)
            keep: list[_Planned] = []
            for item in items:
                if self._pair_stored(item, stored):
                    collisions.append(item.aggregated.write)
                else:
                    keep.append(item)
            to_write[label] = keep

        # 4b. Edge `id` is UNIQUE per type. A writer that fixes its ids (`HOLDS`, a mention, a
        # seeder's pair id) sends one id for each audience of a pair, and a link of another audience
        # may already hold it: each such write is a link of its own under a new id, so the store
        # never refuses a row, and `written` names the ids as stored (ADR-102 Amendment 3).
        for label, items in to_write.items():
            await self._mint_ids_where_taken(label, items)

        # 5. Weights against the corpus at the end of the load: what was stored plus this call.
        now = now_utc()
        rows_by_label: dict[str, list[dict[str, Any]]] = {}
        for label, items in to_write.items():
            if not items:
                continue
            rows_by_label[label] = await self._rows_for(
                schema, label, items, baseline_total[label], now
            )

        # 6. Write, a chunk per transaction. A failure leaves earlier chunks committed; the caller
        # reverts by load_id and reruns (ADR-058 D6).
        total = sum(len(rows) for rows in rows_by_label.values())
        written: list[str] = []
        chunks = 0
        for label, rows in rows_by_label.items():
            for start in range(0, len(rows), chunk_size):
                chunk = rows[start : start + chunk_size]
                tx = await self._transport.begin()
                try:
                    await self._transport.write_chunk(label, chunk, tx)
                    await self._transport.commit(tx)
                except BaseException:
                    await self._transport.rollback(tx)
                    raise
                chunks += 1
                written.extend(str(r["p"]["id"]) for r in chunk)
                if progress is not None:
                    progress(len(written), total)
        return BulkEdgeResult(
            written=written, collisions=collisions, received=len(edges), chunks=chunks
        )

    async def _mint_ids_where_taken(self, label: str, items: list[_Planned]) -> None:
        ids = [i.aggregated.write.id for i in items]
        taken: set[str] = set()
        for start in range(0, len(ids), LOOKUP_BATCH):
            taken |= await self._transport.taken_edge_ids(label, ids[start : start + LOOKUP_BATCH])
        used: set[str] = set()
        for item in items:
            write = item.aggregated.write
            if write.id in taken or write.id in used:
                item.aggregated = AggregatedEdge(
                    write=write.model_copy(update={"id": new_edge_id()}),
                    writes=item.aggregated.writes,
                )
            used.add(item.aggregated.write.id)

    async def _check_endpoints(
        self, schema: OntologySchema, aggregated: Sequence[AggregatedEdge]
    ) -> None:
        ids = sorted({a.write.source for a in aggregated} | {a.write.target for a in aggregated})
        labels: dict[str, str] = {}
        for start in range(0, len(ids), LOOKUP_BATCH):
            labels.update(await self._transport.vertex_labels(ids[start : start + LOOKUP_BATCH]))
        for item in aggregated:
            write = item.write
            for role, node_id in (("source", write.source), ("target", write.target)):
                if node_id not in labels:
                    raise OntologyError(f"edge {role} {node_id!r} does not exist")
            edge_type = schema.edge_type(write.type)
            assert edge_type is not None  # checked in step 1
            validate_edge_endpoints(
                edge_type,
                source_type=logical_type_name(labels[write.source]),
                target_type=logical_type_name(labels[write.target]),
            )

    async def _stored_links(
        self, label: str, items: Sequence[_Planned], *, directed: bool
    ) -> dict[tuple[str, str], set[Hashable]]:
        """The audiences of the links stored for these pairs, by pair as stored."""
        found: dict[tuple[str, str], set[Hashable]] = {}
        pairs = [(i.aggregated.write.source, i.aggregated.write.target) for i in items]
        for start in range(0, len(pairs), LOOKUP_BATCH):
            for link in await self._transport.stored_links(
                label, pairs[start : start + LOOKUP_BATCH], directed=directed
            ):
                audience = audience_parts(
                    link.classification,
                    link.handling_code,
                    link.datasets,
                    link.originator,
                    link.owning_unit,
                    self._scheme,
                )
                found.setdefault((link.source, link.target), set()).add(audience)
        return found

    def _pair_stored(self, item: _Planned, stored: dict[tuple[str, str], set[Hashable]]) -> bool:
        """Whether a link of the write's own audience is stored for its pair (ADR-102 Amendment 3):
        a stored link of another audience is not the write's to merge into, so it is no collision
        and the write is a link of its own."""
        write = item.aggregated.write
        audience = audience_of(write.handling, write.datasets, self._scheme)
        pair = (write.source, write.target)
        if audience in stored.get(pair, ()):
            return True
        return not item.directed and audience in stored.get((pair[1], pair[0]), ())

    async def _rows_for(
        self,
        schema: OntologySchema,
        label: str,
        items: Sequence[_Planned],
        baseline_total: int,
        now: datetime,
    ) -> list[dict[str, Any]]:
        load_degree: dict[str, int] = {}
        load_total = 0
        for item in items:
            occurrences = item.aggregated.write.occurrences
            load_total += occurrences
            for node in (item.aggregated.write.source, item.aggregated.write.target):
                load_degree[node] = load_degree.get(node, 0) + occurrences
        baseline_degree: dict[str, int] = {}
        if baseline_total:  # an empty type has no degree to add
            nodes = sorted(load_degree)
            for start in range(0, len(nodes), LOOKUP_BATCH):
                baseline_degree.update(
                    await self._transport.degrees(label, nodes[start : start + LOOKUP_BATCH])
                )

        rows: list[dict[str, Any]] = []
        for item in items:
            write = item.aggregated.write
            edge_type = schema.edge_type(write.type)
            assert edge_type is not None
            components = WeightComponents(
                occurrences=write.occurrences,
                corpus_pair_count=write.occurrences,
                corpus_source_degree=baseline_degree.get(write.source, 0)
                + load_degree[write.source],
                corpus_target_degree=baseline_degree.get(write.target, 0)
                + load_degree[write.target],
                corpus_total_occurrences=baseline_total + load_total,
                computed_at=now,
                parameter_set=self._weight_rules.parameter_set(write.type),
            )
            weight = compute_weight(
                components,
                edge_type=write.type,
                valid_to=write.interval.valid_to if write.interval else None,
                now=now,
                rules=self._weight_rules,
                self_loop=write.source == write.target,
            )
            audit = AuditStub(
                created_at=write.created_at,
                created_by=write.created_by,
                revision=item.aggregated.writes,
                load_id=write.load_id,
                recipe_id=write.recipe_id,
                recipe_version=write.recipe_version,
            )
            props = edge_write_to_properties(
                write,
                edge_id=write.id,
                audit=audit,
                edge_type=edge_type,
                weight=weight,
                weight_components=components,
            )
            rows.append({"s": write.source, "t": write.target, "p": props})
        return rows


class GremlinBulkTransport:
    """Gremlin over ArcadeDB's HTTP command endpoint. Every value travels as a parameter; the only
    text spliced into a script is the edge label, an identifier already validated by
    `groovy_identifier`, so a script's text is the same for every chunk and compiles once.

    **Unproven shapes** (see the module note): `within`, `project`/`by`, `coalesce`, and a
    closure that builds a traversal per row are standard Gremlin-Groovy, but whether this
    ArcadeDB runs each is what the spike establishes."""

    #: Epoch-millisecond properties that must reach the store as `Date`s, as in `upsert_edges`.
    _DATE_KEYS = ("valid_from", "valid_to")

    def __init__(self, client: ArcadeDBClient) -> None:
        self._client = client

    async def vertex_labels(self, ids: Sequence[str]) -> dict[str, str]:
        rows = await self._client.gremlin(
            'g.V().has("id", within(ids)).project("id","label").by(values("id")).by(label())',
            params={"ids": list(ids)},
        )
        return {str(r["id"]): str(r["label"]) for r in rows}

    async def edge_type_is_empty(self, label: str) -> bool:
        rows = await self._client.gremlin(f'g.E().hasLabel("{label}").limit(1).count()')
        return not rows or int(rows[0].get("result") or 0) == 0

    async def stored_links(
        self, label: str, pairs: Sequence[tuple[str, str]], *, directed: bool
    ) -> list[StoredLink]:
        sources = sorted({s for s, _ in pairs})
        targets = sorted({t for _, t in pairs})
        # A directed edge is looked for from its source; an undirected one may have been stored
        # either way round, so it is looked for from either end (`bothE`, `otherV`). A superseded
        # link is left out, as `_find_existing_edge` leaves it out: its replacement is the pair's
        # link. Each link comes back with what decides who may see it (ADR-102 Amendment 3); one
        # with no `datasets` property reads as having none, and does not drop out of the answer.
        step, other = ("outE", "inV") if directed else ("bothE", "otherV")
        rows = await self._client.gremlin(
            f'g.V().has("id", within(sources)).{step}("{label}").has("reverted", false)'
            '.hasNot("superseded_by")'
            f'.where({other}().has("id", within(targets)))'
            '.project("s","t","c","h","o","u","d")'
            '.by(outV().values("id")).by(inV().values("id"))'
            '.by(values("handling_classification")).by(values("handling_code"))'
            '.by(values("originator")).by(values("owning_unit"))'
            '.by(coalesce(values("datasets"), constant("")))',
            params={"sources": sources, "targets": targets},
        )
        wanted = set(pairs)
        allowed = wanted if directed else wanted | {(t, s) for s, t in wanted}
        links = []
        for r in rows:
            if (str(r["s"]), str(r["t"])) not in allowed:
                continue
            datasets = r["d"]
            links.append(
                StoredLink(
                    source=str(r["s"]),
                    target=str(r["t"]),
                    classification=str(r["c"]),
                    handling_code=str(r["h"]),
                    originator=str(r["o"]),
                    owning_unit=str(r["u"]),
                    datasets=tuple(
                        str(d) for d in ([datasets] if isinstance(datasets, str) else datasets) if d
                    ),
                )
            )
        return links

    async def taken_edge_ids(self, label: str, ids: Sequence[str]) -> set[str]:
        # Every edge of the type ever written holds its id for good: no `reverted` or
        # `superseded_by` question, since the unique index asks none. SQL against that index (as
        # the by-id reads are), not a traversal that may scan the type.
        rows = await self._client.sql(render_existing_ids_sql(label), params={"ids": list(ids)})
        return {str(r["id"]) for r in rows}

    async def corpus_total(self, label: str) -> int:
        rows = await self._client.gremlin(
            f'g.V().outE("{label}").has("reverted", false).hasNot("superseded_by")'
            '.values("occurrences").sum()'
        )
        return int(rows[0].get("result") or 0) if rows else 0

    async def degrees(self, label: str, ids: Sequence[str]) -> dict[str, int]:
        rows = await self._client.gremlin(
            'g.V().has("id", within(ids)).project("id","d").by(values("id"))'
            '.by(coalesce(bothE("' + label + '").has("reverted", false)'
            '.hasNot("superseded_by").values("occurrences").sum(), constant(0)))',
            params={"ids": list(ids)},
        )
        return {str(r["id"]): int(r["d"]) for r in rows}

    async def begin(self) -> str:
        return await self._client.begin_transaction()

    async def commit(self, tx: str) -> None:
        await self._client.commit_transaction(tx)

    async def rollback(self, tx: str) -> None:
        await self._client.rollback_transaction(tx)

    async def write_chunk(self, label: str, rows: Sequence[Mapping[str, Any]], tx: str) -> None:
        script = (
            "rows.each { r ->"
            ' def t = g.V().has("id", r.s).as("a").V().has("id", r.t).addE("' + label + '")'
            '.from("a");'
            " r.p.each { k, v -> t = t.property(k, dates.contains(k) ? new Date(v) : v) };"
            " t.iterate() }"
        )
        await self._client.gremlin(
            script, params={"rows": list(rows), "dates": list(self._DATE_KEYS)}, session_id=tx
        )
