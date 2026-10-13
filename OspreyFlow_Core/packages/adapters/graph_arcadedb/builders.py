"""Dialect-agnostic query builders — `spec/06_DECISIONS.md` ADR-003 amendment.

Each builder describes intent (expand, path, match, neighbourhood stats) and
renders it for one dialect. Only `render_gremlin` exists in Phase 1
(`dialects = {"gremlin"}`); a second dialect is a `render_<dialect>` method
added later, with no change to the callers in `adapter.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from schemas.domain import (
    ExpandRequest,
    OntologySchema,
    PathRequest,
    PatternEdge,
    PatternNode,
    PatternQuery,
    Principal,
    PropertyType,
)

from .access_filter import AccessFilter
from .gremlin_literals import (
    groovy_args_literal,
    groovy_string_list_literal,
    groovy_string_literal,
)
from .naming import physical_edge_labels, physical_type_name

_EDGE_STEP = {"out": "outE", "in": "inE", "both": "bothE"}
_OTHER_VERTEX_STEP = {"out": "inV", "in": "outV", "both": "otherV"}


@dataclass(frozen=True)
class GetNodeBuilder:
    node_id: str
    include_superseded: bool = False

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal, include_superseded=self.include_superseded)
        node_lit = groovy_string_literal(self.node_id)
        return f'g.V().has("id",{node_lit}).{has_access}.elementMap()'


@dataclass(frozen=True)
class FindByIdentifierBuilder:
    entity_type: str
    identifier_field: str
    value: str

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        type_lit = groovy_string_literal(physical_type_name(self.entity_type))
        field_lit = groovy_string_literal(self.identifier_field)
        value_lit = groovy_string_literal(self.value)
        return (
            f"g.V().hasLabel({type_lit}).has({field_lit},{value_lit})"
            f".{has_access}.limit(1).elementMap()"
        )


@dataclass(frozen=True)
class SearchNodesBuilder:
    """`GraphPort.search_nodes` — exact match against `identifier_fields`
    (every distinct property name any entity type in the applied ontology
    declares as an `identifiers` entry), regardless of which type actually
    carries it: `has(field,value)` alone, with no `hasLabel` restriction,
    matches any vertex carrying that property — the same reasoning
    `FindByIdentifierBuilder` uses for one named field, generalised across
    the whole declared set with `or()` rather than one query per field."""

    identifier_fields: tuple[str, ...]
    query: str
    limit: int = 20

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        value_lit = groovy_string_literal(self.query)
        clauses = ",".join(
            f"__.has({groovy_string_literal(field)},{value_lit})"
            for field in self.identifier_fields
        )
        return f"g.V().or({clauses}).{has_access}.dedup().limit({self.limit}).elementMap()"


@dataclass(frozen=True)
class ListNodesBuilder:
    """`GraphPort.list_nodes` — `06_DECISIONS.md` ADR-025. Keyset pagination
    on `id` (a ULID, lexicographically sortable and fixed at creation): a
    page is `id > cursor` (or unfiltered on the first page), ordered by
    `id`, so a page boundary is stable regardless of what else is written
    concurrently — see the port method's own docstring for the full
    consistency argument this relies on."""

    entity_type: str
    cursor: str | None
    limit: int

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        type_lit = groovy_string_literal(physical_type_name(self.entity_type))
        cursor_step = ""
        if self.cursor is not None:
            cursor_lit = groovy_string_literal(self.cursor)
            cursor_step = f'.has("id",gt({cursor_lit}))'
        return (
            f"g.V().hasLabel({type_lit}){cursor_step}.{has_access}"
            f'.order().by("id").limit({self.limit}).elementMap()'
        )


@dataclass(frozen=True)
class SuggestLocationsBuilder:
    """`GraphPort.suggest_locations` — the geocoder's own candidate
    retrieval (a disclosed gap), scoped to `Location.name`
    only. Uses TinkerPop's `TextP.containing` predicate — confirmed
    live against a real ArcadeDB instance to work over its Gremlin command
    endpoint (`SearchNodesBuilder`'s own docstring had flagged this as
    unproven; it is not, for this predicate) — a coarse substring scan,
    not a Lucene/full-text index: no relevance scoring, no tokenisation,
    bounded by `limit` exactly like `SearchNodesBuilder`. Deliberately not
    folded into `SearchNodesBuilder` itself, which stays exact-match-only
    by its own documented contract."""

    name: str
    limit: int = 20

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        name_lit = groovy_string_literal(self.name)
        location_type_lit = groovy_string_literal(physical_type_name("Location"))
        return (
            f"g.V().hasLabel({location_type_lit})"
            f".has('name',TextP.containing({name_lit})).{has_access}"
            f".dedup().limit({self.limit}).elementMap()"
        )


def suggestion_scope(
    schema: OntologySchema, types: tuple[str, ...] | None = None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The physical types and the property names a suggestion looks at: each entity type's
    declared identifiers plus its indexed properties, as `search_nodes` does, but only string
    ones (a prefix of a number or a flag means nothing) and only on types that carry one, so the
    scan is label-first and as narrow as the ontology allows. `types` narrows it to the named
    entity types; a name the ontology does not have is a `ValueError`."""
    if types is not None:
        known = {e.name for e in schema.entity_types}
        unknown = sorted(set(types) - known)
        if unknown:
            raise ValueError(f"unknown entity type(s): {', '.join(unknown)}")
    labels: list[str] = []
    fields: set[str] = set()
    for entity in schema.entity_types:
        if types is not None and entity.name not in types:
            continue
        declared = {p.name: p.type for p in entity.properties}
        carried = {
            f
            for f in entity.identifiers
            if declared.get(f, PropertyType.STRING) is PropertyType.STRING
        }
        carried |= {
            p.name for p in entity.properties if p.indexed and p.type is PropertyType.STRING
        }
        if carried:
            labels.append(physical_type_name(entity.name))
            fields |= carried
    return tuple(labels), tuple(sorted(fields))


def java_regex_quote(text: str) -> str:
    """`java.util.regex.Pattern.quote`: typed text is matched as text, never as a pattern."""
    if "\\E" not in text:
        return f"\\Q{text}\\E"
    return "\\Q" + text.replace("\\E", "\\E\\\\E\\Q") + "\\E"


@dataclass(frozen=True)
class SuggestNodesBuilder:
    """`GraphPort.suggest_nodes` — a label-first prefix scan (`TextP.startingWith`, the same
    predicate family `SuggestLocationsBuilder` proved live). Asks for `limit + 1` so the adapter
    can say whether more matched without a second query; the extra row is counted after the
    access step, so it cannot reveal a hidden node."""

    labels: tuple[str, ...]
    fields: tuple[str, ...]
    prefix: str
    limit: int = 10
    mode: str = "starts_with"
    ignore_case: bool = False

    def _predicate(self) -> str:
        """Case-sensitive forms use TinkerPop's own text predicates (proven live for `startingWith`
        and `containing`). Ignoring case has no such predicate, so it is a regular expression with
        the `(?iu)` flag over quoted text; **that form is not yet proven on ArcadeDB's Gremlin
        engine** (ADR-061), and neither it nor `contains` can use an index."""
        if self.ignore_case:
            quoted = java_regex_quote(self.prefix)
            pattern = {
                "starts_with": f"(?iu)^{quoted}",
                "contains": f"(?iu){quoted}",
                "exact": f"(?iu)^{quoted}$",
            }[self.mode]
            return f"TextP.regex({groovy_string_literal(pattern)})"
        lit = groovy_string_literal(self.prefix)
        return {
            "starts_with": f"TextP.startingWith({lit})",
            "contains": f"TextP.containing({lit})",
            "exact": f"P.eq({lit})",
        }[self.mode]

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        predicate = self._predicate()
        labels = ",".join(groovy_string_literal(label) for label in self.labels)
        clauses = ",".join(
            f"__.has({groovy_string_literal(field)},{predicate})" for field in self.fields
        )
        return (
            f"g.V().hasLabel({labels}).or({clauses}).{has_access}"
            f".dedup().limit({self.limit + 1}).elementMap()"
        )


def _local_date_time(moment: datetime) -> str:
    """A Groovy `java.time.LocalDateTime` literal for an aware datetime, normalised to UTC and
    rendered naive — see `_temporal_filter` for why the millis forms cannot be used on ArcadeDB
    25.5.1."""
    utc_naive = moment.astimezone(UTC).replace(tzinfo=None)
    return f'java.time.LocalDateTime.parse("{utc_naive.isoformat(timespec="milliseconds")}")'


def render_edges_among_gremlin(
    node_ids: Sequence[str],
    access: AccessFilter,
    principal: Principal,
    edge_types: list[str] | None = None,
) -> str:
    """Every edge with both ends in `node_ids` (ADR-098 decision 1), each once: from each node in
    the set, its outgoing edges, kept when their head is in the set too. The access step is on the
    tail, the edge and the head, so a hidden edge, or an edge to a hidden node, leaves no trace."""
    has_access = access.gremlin_has_step(principal)
    ids = groovy_string_list_literal(list(node_ids))
    label_filter = ""
    if edge_types:
        physical = [label for t in edge_types for label in physical_edge_labels(t)]
        label_filter = f".hasLabel({groovy_args_literal(physical)})"
    return (
        f'g.V().has("id",within({ids})).{has_access}'
        f".outE(){label_filter}.{has_access}"
        f'.where(inV().has("id",within({ids})).{has_access})'
        ".dedup().elementMap()"
    )


@dataclass(frozen=True)
class ExpandBuilder:
    request: ExpandRequest

    def _edge_label_filter(self) -> str:
        if not self.request.edge_types:
            return ""
        physical = [label for t in self.request.edge_types for label in physical_edge_labels(t)]
        # `hasLabel(...)` is a varargs step (`hasLabel('a','b')`), not a
        # list-argument one — `.hasLabel(['a'])` (a single Groovy List)
        # fails against ArcadeDB's Gremlin engine with a bare
        # `CommandExecutionException` and no further detail (confirmed
        # empirically: `tests/conformance/graph_port/test_suite.py`'s
        # `test_expand_edge_types_filters_to_the_declared_type`, added
        # once this was found — no existing test had ever exercised
        # `edge_types` filtering on `expand`/`paths` before Phase 5's HMP
        # fixture work tripped over it). `groovy_args_literal` renders the
        # comma-separated varargs form already used correctly elsewhere in
        # this module (`select(...)`, below).
        return f".hasLabel({groovy_args_literal(physical)})"

    def _temporal_filter(self) -> str:
        """Exercises the vertex-centric `(edge_type, interval.from)` index
        (`04_VAULT_BACKEND.md` §1.4) rather than scanning the adjacency
        list — every temporal edge type carries a flattened, indexed
        `valid_from` (`schema.py`)."""
        window = self.request.temporal_window
        if window is None:
            return ""
        # **`LocalDateTime`, not `new Date(millis)` — changed with the ArcadeDB 25.5.1 pin
        # (round 13bb, 27 September 2026), and it is a silent-wrong-answer change, not a syntax
        # one.** On 24.11.1 a `gte`/`lte` predicate against a DATETIME property needed an actual
        # `Date` built from epoch millis. On 25.5.1 every millis-based form still *parses and
        # runs* and simply matches nothing: measured against the adapter's own stored shape, with
        # one edge genuinely inside the window, `gte(new Date(ms))` -> 0, `gte(<long>)` -> 0,
        # `between(lo,hi)` -> 0, `Instant.ofEpochMilli` -> 0, no filter at all -> 1, and
        # `LocalDateTime.parse(...)` -> 1. A temporal expansion would have returned an empty
        # neighbourhood rather than an error.
        #
        # `test_expand_temporal_window_filters_edges_by_valid_from` is the case that caught it and
        # is the case that fails if this regresses — the only red in the whole suite under the new
        # pin, which is the entire argument for the conformance suite existing.
        #
        # The stored value reads back UTC-naive (`SELECT valid_from` -> `2026-09-27 14:11:03`
        # for an edge written at 14:11 UTC), so the bound is rendered UTC-naive too; milliseconds
        # are kept because the stored value carries them even though the default display truncates
        # to seconds, and a truncated bound would misjudge an edge inside the same second.
        clause = f'.has("valid_from",gte({_local_date_time(window.valid_from)}))'
        if window.valid_to is not None:
            clause += f'.has("valid_from",lte({_local_date_time(window.valid_to)}))'
        return clause

    def _repeat_clause(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        edge_step = _EDGE_STEP[self.request.direction]
        other_step = _OTHER_VERTEX_STEP[self.request.direction]
        edge_filter = self._edge_label_filter()
        temporal_filter = self._temporal_filter()
        return (
            f"repeat({edge_step}(){edge_filter}.{has_access}{temporal_filter}.as('e')"
            f".{other_step}().{has_access}.simplePath())"
            f".times({self.request.depth}).emit()"
        )

    def render_seed_nodes_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        """The seed nodes themselves — `emit()` inside `repeat()` (used for
        the reached nodes below) never surfaces the pre-loop starting
        vertices, so `expand` fetches them separately and the adapter
        unions the two result sets."""
        has_access = access.gremlin_has_step(principal)
        seeds = groovy_string_list_literal(self.request.node_ids)
        return f'g.V().has("id",within({seeds})).{has_access}.elementMap()'

    def render_nodes_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        seeds = groovy_string_list_literal(self.request.node_ids)
        return (
            f'g.V().has("id",within({seeds})).{has_access}'
            f".{self._repeat_clause(access, principal)}.dedup().elementMap()"
        )

    def render_edges_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        seeds = groovy_string_list_literal(self.request.node_ids)
        return (
            f'g.V().has("id",within({seeds})).{has_access}'
            f".{self._repeat_clause(access, principal)}.select('e').dedup().elementMap()"
        )

    def render_candidate_count_gremlin(self, structural_step: str) -> str:
        """The unfiltered half of `Subgraph.filtered_count`'s comparison
        (`01_DOMAIN_MODEL.md` §8.2): the same seed set, depth, edge-type
        and temporal scope as `render_nodes_gremlin`, but with neither
        access axis applied — only `structural_step`
        (`AccessFilter.gremlin_structural_step`) carries over, since
        reverted/superseded exclusion isn't principal-dependent and a
        reverted or superseded element was never real data to begin with,
        not a handling-filtered one. `union(identity(), repeat(...))`
        mirrors `expand`'s own seeds-plus-reached union (`adapter.py`
        currently does that union in Python across two separate queries)
        in one traversal, since this method returns a bare count, not
        elements to union in the caller."""
        seeds = groovy_string_list_literal(self.request.node_ids)
        edge_step = _EDGE_STEP[self.request.direction]
        other_step = _OTHER_VERTEX_STEP[self.request.direction]
        edge_filter = self._edge_label_filter()
        temporal_filter = self._temporal_filter()
        repeat = (
            f"repeat({edge_step}(){edge_filter}.{structural_step}{temporal_filter}.as('e')"
            f".{other_step}().{structural_step}.simplePath())"
            f".times({self.request.depth}).emit()"
        )
        return (
            f'g.V().has("id",within({seeds})).{structural_step}'
            f".union(identity(),{repeat}).dedup().count()"
        )


def _route_step_filter(edge_types: tuple[str, ...] | list[str] | None) -> str | None:
    """The label filter on each link a route may take, or `None` when no type asked for may be
    walked. A `NOT_SAME_AS` link is never a step (ADR-116 Amendment 1, the owner's ruling): it is an
    analyst's judgement that two records are different, not a connection between them."""
    never = physical_type_name("NOT_SAME_AS")
    if edge_types is None:
        return f'.not(hasLabel("{never}"))'
    physical = [label for t in edge_types for label in physical_edge_labels(t) if label != never]
    if not physical:
        return None
    # See `ExpandBuilder._edge_label_filter`'s comment — the varargs-not-list bug, same fix.
    return f".hasLabel({groovy_args_literal(physical)})"


@dataclass(frozen=True)
class PathBuilder:
    """Compiles a `PathRequest` into a `has_access`-filtered `repeat()`/`until()` traversal —
    `01_DOMAIN_MODEL.md` §6.3's own implementation note: the access predicate is injected at the
    source vertex, every candidate edge, and every intermediate vertex, so a path that would have
    to pass through a node the principal cannot see is never found at all, not found and then
    discarded. `test_unauthorised_path_length_matches_a_graph_without_the_hidden_hop`
    (`tests/conformance/graph_port/test_suite.py`) is the standing proof this must never regress.

    **`render_gremlin` stays `.by("id").by("id")` — confirmed empirically, not assumed, that
    `.by(elementMap())` inside a `path()` step fails on this adapter** (Phase 7 Stage 5,
    `06_DECISIONS.md` ADR-033): ArcadeDB's own Gremlin engine raises a server-side
    `ClassCastException` ("`T$2` cannot be cast to `String`") the moment an `elementMap()`
    modulator is cycled through `path()`'s own interleaved steps — a live-instance finding, the
    same "checked directly against ArcadeDB, not the TinkerPop spec" discipline ADR-030's own
    `match()` finding already established for a different step. `render_hydrate_nodes_gremlin`/
    `render_hydrate_edges_gremlin` below hydrate the resulting ids in two separate, already
    -proven-safe follow-up queries instead — the same "separate query per element type" shape
    `ExpandBuilder.render_nodes_gremlin`/`render_edges_gremlin` already use — rather than fighting
    the broken combination."""

    request: PathRequest

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str | None:
        """The traversal, or `None` when it could find nothing (no walkable link type asked)."""
        has_access = access.gremlin_has_step(principal)
        source_lit = groovy_string_literal(self.request.source)
        target_lit = groovy_string_literal(self.request.target)
        edge_filter = _route_step_filter(self.request.edge_types or None)
        if edge_filter is None:
            return None
        return (
            f'g.V().has("id",{source_lit}).{has_access}'
            f".repeat(bothE(){edge_filter}.{has_access}.as('e').otherV().{has_access}.simplePath())"
            f'.until(has("id",{target_lit}).or().loops().is(gte({self.request.max_hops})))'
            f'.has("id",{target_lit})'
            f'.limit({self.request.k}).path().by("id").by("id")'
        )

    @staticmethod
    def render_hydrate_nodes_gremlin(
        node_ids: list[str], access: AccessFilter, principal: Principal
    ) -> str:
        has_access = access.gremlin_has_step(principal)
        ids_literal = groovy_string_list_literal(node_ids)
        return f'g.V().has("id",within({ids_literal})).{has_access}.elementMap()'

    @staticmethod
    def render_hydrate_edges_gremlin(
        node_ids: list[str], edge_ids: list[str], access: AccessFilter, principal: Principal
    ) -> str:
        """Anchored at the path's own (already access-proven) node ids, not `g.E()` — this
        codebase has no existing, proven-safe edge-first traversal start to build on, and every
        other builder here starts from `g.V()`; re-checking `has_access` on the edge step itself
        is defence in depth, not a correctness requirement (these ids already passed the original
        path traversal's own filter)."""
        has_access = access.gremlin_has_step(principal)
        node_ids_literal = groovy_string_list_literal(node_ids)
        edge_ids_literal = groovy_string_list_literal(edge_ids)
        return (
            f'g.V().has("id",within({node_ids_literal})).{has_access}'
            f'.bothE().has("id",within({edge_ids_literal})).{has_access}.dedup().elementMap()'
        )


@dataclass(frozen=True)
class RoutesAtLengthBuilder:
    """ADR-116 decision 5: `PathBuilder`'s traversal held to exactly `length` links — `times()`
    where `PathBuilder` has `until()` — with the access predicate at the source, every link and
    every node walked onto, so a route through anything the principal cannot see is never found.
    `simplePath()` keeps a route from coming back to a node, the target included, so a route that
    ends at the target after `length` links never passed it sooner. One more than `limit` is asked
    for, so the caller can say that more exist (rule 2). A `NOT_SAME_AS` link is never a step: it is
    an analyst's judgement that two records are different, not a connection."""

    source: str
    target: str
    length: int
    limit: int
    edge_types: tuple[str, ...] | None = None

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str | None:
        """The traversal, or `None` when it could find nothing (no walkable link type asked)."""
        edge_filter = _route_step_filter(self.edge_types)
        if edge_filter is None:
            return None
        has_access = access.gremlin_has_step(principal)
        source_lit = groovy_string_literal(self.source)
        target_lit = groovy_string_literal(self.target)
        return (
            f'g.V().has("id",{source_lit}).{has_access}'
            f".repeat(bothE(){edge_filter}.{has_access}.otherV().{has_access}.simplePath())"
            f".times({self.length})"
            f'.has("id",{target_lit})'
            f'.limit({self.limit + 1}).path().by("id").by("id")'
        )


@dataclass(frozen=True)
class NeighbourhoodStatsBuilder:
    node_id: str

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        node_lit = groovy_string_literal(self.node_id)
        return (
            f'g.V().has("id",{node_lit}).{has_access}.bothE().{has_access}'
            f".where(otherV().{has_access}).groupCount().by(label())"
        )


def _pin(node: PatternNode) -> str:
    """A pinned variable binds that one node: the analyst's "this node", not its type."""
    return f'.has("id",{groovy_string_literal(node.node_id)})' if node.node_id else ""


def _could_be_one(a: PatternNode | None, b: PatternNode | None) -> bool:
    """Whether two variables could bind the same node, and so need telling apart: not when both
    name a type and the types differ, which keeps a chain across types exactly as it compiled."""
    if a is None or b is None or not a.entity_type or not b.entity_type:
        return True
    return a.entity_type == b.entity_type


@dataclass(frozen=True)
class MatchBuilder:
    """Compiles a bounded `PatternQuery` into Gremlin — `01_DOMAIN_MODEL.md` §8.1, widened in
    Phase 7 Stage 4 (`06_DECISIONS.md` ADR-030). A pattern that linearises into a single
    chain from one
    root (every edge's `from_var` already bound when it's declared) compiles via
    `_render_single_chain` — byte-identical to the pre-widening compiler
    (`test_match_single_chain_pattern_compiles_to_the_same_gremlin_as_before`'s own no-regression
    proof).

    **A pattern needing more than one root — B19's own "two independent endpoints converging on
    shared contacts" shape — falls back to `_render_matched`, which does *not* use Gremlin's
    `match()` step.** That was the first design tried; confirmed empirically against a live
    ArcadeDB instance, not assumed from the TinkerPop docs, that ArcadeDB's own `match()`
    implementation cannot introduce a second, genuinely independent enumeration inside a fragment
    (`__.V()...` as a *root* fragment) — every attempt failed with a bare
    `CommandExecutionException`, including the simplest possible case with no filters at all.
    `_render_matched` instead compiles
    a *pinned-root reachability check*: every root beyond the primary one must carry `PatternNode.
    node_id` (a concrete, already-known node — B19's own "two principal endpoints" are nodes the
    analyst already selected, not an open type to search for), and the fragment reaching the
    convergence point is walked forward once for the primary chain, then reversed and asserted as
    a `.where()` reachability check from each secondary root's own known id. An open (unpinned)
    second root remains unsupported — there is no general join to fall back to on this adapter.
    Every step in both paths is still built exclusively by this compiler, one hop at a time, with
    `has_access` injected at every `.outE()`/`.inV()`/`.inE()`/`.outV()` exactly as before — the
    access-filtering guarantee is that the compiler owns every step, not that the overall shape
    stays one chain, so widening changes what must be *proven*
    (`test_match_intersection_never_leaks_a_hidden_common_endpoint`), not who constructs a step."""

    pattern: PatternQuery

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        if not self.pattern.nodes:
            raise ValueError("PatternQuery must declare at least one node")
        single_chain = self._render_single_chain(access, principal)
        if single_chain is not None:
            return single_chain
        return self._render_matched(access, principal)

    def render_count_gremlin(
        self, access: AccessFilter, principal: Principal, *, ceiling: int
    ) -> str:
        """`GraphPort.match_count`'s compiler — `01_DOMAIN_MODEL.md` §8.1, Phase 7 Stage 4's
        query-builder surface. Deliberately routed through `_render_single_chain`/
        `_render_matched` with `count_only=True` rather than a separate step-building method:
        the whole point (access control lives in the adapter, and the Glass never sees an
        unfiltered count — an estimate must be filtered exactly like the
        real result) is that this can never drift from `render_gremlin`'s own access-filtered
        steps, which duplicating the walk logic here would risk the moment one of the two copies
        was edited and the other wasn't. Only the tail differs: `.dedup().limit(ceiling).count()`
        in place of `.select(...).by(elementMap()).dedup().limit(pattern.limit)` — no property
        hydration, and `ceiling` (not `pattern.limit`) bounds the cost, since a caller deciding
        whether a match needs the job hand-off needs to see how far past `pattern.limit` the true
        count goes, not the query's own display cap."""
        if not self.pattern.nodes:
            raise ValueError("PatternQuery must declare at least one node")
        single_chain = self._render_single_chain(
            access, principal, count_only=True, ceiling=ceiling
        )
        if single_chain is not None:
            return single_chain
        return self._render_matched(access, principal, count_only=True, ceiling=ceiling)

    def _render_single_chain(
        self,
        access: AccessFilter,
        principal: Principal,
        *,
        count_only: bool = False,
        ceiling: int | None = None,
    ) -> str | None:
        """The original compiler, unchanged in every step it emits — returns `None` (never
        raises) the moment the pattern cannot be linearised from `nodes[0]` alone, so
        `render_gremlin` can fall back to `_render_matched` rather than the caller having to
        pre-classify the pattern's own shape first."""
        has_access = access.gremlin_has_step(principal)
        node_by_var = {n.var: n for n in self.pattern.nodes}

        first = self.pattern.nodes[0]
        steps = ["g.V()"]
        if first.entity_type:
            physical_first = physical_type_name(first.entity_type)
            steps.append(f".hasLabel({groovy_string_literal(physical_first)})")
        steps.append(_pin(first))
        steps.append(f".{has_access}")
        steps.append(f".as({groovy_string_literal(first.var)})")

        # In order, as each variable is bound: a later one never binds a node an earlier one of a
        # type it could share has bound (ADR-100 Amendment 7).
        bound = [first.var]

        def arrive(var: str) -> None:
            node = node_by_var.get(var)
            if node and node.entity_type:
                steps.append(
                    f".hasLabel({groovy_string_literal(physical_type_name(node.entity_type))})"
                )
            if node:
                steps.append(_pin(node))
            steps.extend(
                f".where(neq({groovy_string_literal(earlier)}))"
                for earlier in bound
                if _could_be_one(node_by_var.get(earlier), node)
            )
            steps.append(f".as({groovy_string_literal(var)})")
            bound.append(var)

        def walkable(edge: PatternEdge) -> bool:
            # Backwards only to an unpinned variable: a pinned one stays with `_render_matched`,
            # B19's own path, so that shape compiles as it always has.
            from_node = node_by_var.get(edge.from_var)
            return edge.from_var in bound or (
                edge.to_var in bound and (from_node is None or from_node.node_id is None)
            )

        # The next link touching what is already reached, in whatever order they were drawn.
        pending = list(self.pattern.edges)
        while pending:
            edge = next((e for e in pending if walkable(e)), None)
            if edge is None:
                return None
            pending.remove(edge)
            edge_labels = physical_edge_labels(edge.edge_type)
            if edge.from_var in bound and edge.to_var in bound:
                # A join (ADR-100 Amendment 7): the two already-bound nodes are linked.
                steps.append(
                    f".where(select({groovy_string_literal(edge.from_var)})"
                    f".outE({groovy_args_literal(edge_labels)}).{has_access}"
                    f".inV().{has_access}.where(eq({groovy_string_literal(edge.to_var)})))"
                )
            elif edge.from_var in bound:
                steps.append(f".select({groovy_string_literal(edge.from_var)})")
                steps.append(f".outE({groovy_args_literal(edge_labels)})")
                steps.append(f".{has_access}")
                steps.append(".inV()")
                steps.append(f".{has_access}")
                arrive(edge.to_var)
            else:
                # Walked backwards to a new variable (ADR-100 Amendment 7).
                steps.append(f".select({groovy_string_literal(edge.to_var)})")
                steps.append(f".inE({groovy_args_literal(edge_labels)})")
                steps.append(f".{has_access}")
                steps.append(".outV()")
                steps.append(f".{has_access}")
                arrive(edge.from_var)

        # Every declared node must actually be bound by the walk above — a pattern with more
        # than one fully-disconnected root (no edge ever references the second one at all) would
        # otherwise emit a `.select()` naming a step label nothing ever produced.
        if set(bound) != {n.var for n in self.pattern.nodes}:
            return None

        if count_only:
            assert ceiling is not None  # always passed together — see `render_count_gremlin`
            steps.append(self._count_tail(sorted(n.var for n in self.pattern.nodes), ceiling))
            return "".join(steps)

        # The nodes, each once, as `_count_tail` counts them (rule 2): `limit` bounds nodes, not the
        # ways of matching. A row per binding with `limit` on the rows once returned seven of eight
        # counted nodes for four people sharing four phones, sixteen ways (ADR-100 Amendment 7).
        steps.append(
            self._nodes_tail(sorted(n.var for n in self.pattern.nodes), self.pattern.limit)
        )
        return "".join(steps)

    @staticmethod
    def _nodes_tail(labelled_vars: list[str], limit: int) -> str:
        """Every node a match binds, each once, up to `limit`, as element maps: the same union
        and dedup as `_count_tail`, so `match` returns exactly what `match_count` counted."""
        if len(labelled_vars) > 1:
            branches = ",".join(f"select({groovy_string_literal(v)})" for v in labelled_vars)
            return f".union({branches}).dedup().limit({limit}).elementMap()"
        return f".dedup().limit({limit}).elementMap()"

    @staticmethod
    def _count_tail(labelled_vars: list[str], ceiling: int) -> str:
        """The count-only tail shared by both compilation paths — counts the distinct-by-id union
        of every `.as()`-labelled variable a match binds, the same set `match()`'s own adapter
        code builds in Python (`{node.id: node for record in results for value in
        record.values()}`), so `match_count` and `len(match().nodes)` can never disagree about
        *what* is being counted, only about whether `ceiling` cut it short. `union(select(v), ...)`
        re-selects each already-bound label off the current traverser's own path history — the
        same mid-chain re-`select()` the walk above already relies on — rather than
        `select(v1,...).by(id())` plus a Python-side flatten, so the count stays one real
        server-side aggregate with no extra network round trip for however many rows `ceiling`
        might otherwise allow through. A single-variable pattern skips `union()` entirely: with
        nothing to union, the current stream position already *is* that one variable's own
        vertices, and `union()`'s own single-argument form is unnecessary indirection, not a
        different result."""
        if len(labelled_vars) > 1:
            branches = ",".join(f"select({groovy_string_literal(v)})" for v in labelled_vars)
            return f".union({branches}).dedup().limit({ceiling}).count()"
        return f".dedup().limit({ceiling}).count()"

    def _render_matched(
        self,
        access: AccessFilter,
        principal: Principal,
        *,
        count_only: bool = False,
        ceiling: int | None = None,
    ) -> str:
        """The pinned-root reachability compiler — see the class docstring for why this exists
        instead of Gremlin's own `match()` step. One root drives the primary traversal exactly
        like `_render_single_chain`; every other root must be pinned to a known `node_id` and
        converge, via its own edge chain, on a variable the primary chain also reaches. Each such
        chain is reversed into a `.where()` step, walked backward with `.inE(edge_type).outV()` in
        reverse order, ending in a check against the pinned id — proving "this known node also
        reaches the same convergence point," without ever needing to enumerate or bind a second,
        independent root at all."""
        has_access = access.gremlin_has_step(principal)
        node_by_var = {n.var: n for n in self.pattern.nodes}
        to_vars = {e.to_var for e in self.pattern.edges}
        roots = [n for n in self.pattern.nodes if n.var not in to_vars]
        if not roots:
            raise ValueError(
                "PatternQuery has no root — every node is only ever named as some edge's own "
                "to_var, which cannot be bound by anything (a cycle with no entry point)"
            )

        primary = next((root for root in roots if root.node_id is None), roots[0])
        secondary_roots = [root for root in roots if root.var != primary.var]
        for root in secondary_roots:
            if root.node_id is None:
                raise ValueError(
                    f"pattern root {root.var!r} is not reachable from another root and carries "
                    "no node_id — an open second root has no general join on this adapter "
                    "(ArcadeDB's own Gremlin match() step cannot introduce an independent second "
                    "enumeration, confirmed empirically); pin it to a known node instead"
                )

        edges_by_from: dict[str, list[PatternEdge]] = {}
        for edge in self.pattern.edges:
            edges_by_from.setdefault(edge.from_var, []).append(edge)

        def chain_from(root_var: str) -> list[PatternEdge]:
            chain: list[PatternEdge] = []
            visited = {root_var}
            frontier = [root_var]
            while frontier:
                var = frontier.pop(0)
                for edge in edges_by_from.get(var, []):
                    if edge.to_var in visited:
                        continue
                    chain.append(edge)
                    visited.add(edge.to_var)
                    frontier.append(edge.to_var)
            return chain

        primary_chain = chain_from(primary.var)
        primary_bound = {primary.var, *(edge.to_var for edge in primary_chain)}

        steps = ["g.V()"]
        if primary.entity_type:
            steps.append(
                f".hasLabel({groovy_string_literal(physical_type_name(primary.entity_type))})"
            )
        if primary.node_id:
            steps.append(f'.has("id",{groovy_string_literal(primary.node_id)})')
        steps.append(f".{has_access}")
        steps.append(f".as({groovy_string_literal(primary.var)})")
        for edge in primary_chain:
            to_node = node_by_var.get(edge.to_var)
            edge_labels = physical_edge_labels(edge.edge_type)
            steps.append(f".select({groovy_string_literal(edge.from_var)})")
            steps.append(f".outE({groovy_args_literal(edge_labels)})")
            steps.append(f".{has_access}")
            steps.append(".inV()")
            steps.append(f".{has_access}")
            if to_node and to_node.entity_type:
                steps.append(
                    f".hasLabel({groovy_string_literal(physical_type_name(to_node.entity_type))})"
                )
            steps.append(f".as({groovy_string_literal(edge.to_var)})")

        for root in secondary_roots:
            secondary_chain = chain_from(root.var)
            if not secondary_chain:
                raise ValueError(
                    f"pattern root {root.var!r} is pinned but has no edge connecting it to the "
                    "rest of the pattern"
                )
            join_var = secondary_chain[-1].to_var
            if join_var not in primary_bound:
                raise ValueError(
                    f"pattern root {root.var!r}'s own chain does not converge on a variable the "
                    "primary chain also reaches — only a direct convergence (a diamond) is "
                    "supported, not an arbitrary disjoint fragment"
                )
            assert root.node_id is not None  # guaranteed by the secondary_roots check above
            reverse_steps = []
            for edge in reversed(secondary_chain):
                # The link as well as the node (rule 3): `.in()` alone stepped over a link the
                # reader cannot see (ADR-100 Amendment 7).
                reverse_steps.append(
                    f".inE({groovy_args_literal(physical_edge_labels(edge.edge_type))})"
                )
                reverse_steps.append(f".{has_access}")
                reverse_steps.append(".outV()")
                reverse_steps.append(f".{has_access}")
            reverse_steps.append(f'.has("id",{groovy_string_literal(root.node_id)})')
            steps.append(f".select({groovy_string_literal(join_var)})")
            steps.append(f".where(__{''.join(reverse_steps)})")

        # Every declared node must be either bound (`.as()`-labelled in the outer traversal) or a
        # pinned secondary root (already fully known to the caller — a real node id, not something
        # this query discovers). A root that is neither is a genuine gap: nothing establishes it.
        all_vars = {n.var for n in self.pattern.nodes}
        pinned_vars = {root.var for root in secondary_roots}
        if primary_bound | pinned_vars != all_vars:
            missing = sorted(all_vars - primary_bound - pinned_vars)
            raise ValueError(f"pattern variable(s) never bound by any root or edge: {missing}")

        # A pinned *secondary* root's own identity is never returned: it is never `.as()`-labelled
        # outside its own nested `.where()` check, so only what the primary chain binds is.
        if count_only:
            assert ceiling is not None  # always passed together — see `render_count_gremlin`
            steps.append(self._count_tail(sorted(primary_bound), ceiling))
            return "".join(steps)

        steps.append(self._nodes_tail(sorted(primary_bound), self.pattern.limit))
        return "".join(steps)


@dataclass(frozen=True)
class MostConnectedBuilder:
    """`GraphPort.most_connected` (ADR-100). The degree is `NeighbourhoodStatsBuilder`'s: links the
    principal can see, to nodes it can see. Ordered in the store, then paged, so the page is the
    principal's own ranking, not a ranking of everything filtered afterwards."""

    entity_type: str | None
    limit: int
    offset: int

    def _base(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        label = (
            ""
            if self.entity_type is None
            else f".hasLabel({groovy_string_literal(physical_type_name(self.entity_type))})"
        )
        return f"g.V(){label}.{has_access}"

    def render_total_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        return f"{self._base(access, principal)}.count()"

    def render_page_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        degree = f"bothE().{has_access}.where(otherV().{has_access}).count()"
        return (
            f'{self._base(access, principal)}.order().by({degree},desc).by("id")'
            f".range({self.offset},{self.offset + self.limit})"
            f'.project("node","degree").by(elementMap()).by({degree})'
        )


def render_type_counts_gremlin(access: AccessFilter, principal: Principal) -> tuple[str, str]:
    """`GraphPort.type_counts` (ADR-100): nodes, then links with both ends visible."""
    has_access = access.gremlin_has_step(principal)
    return (
        f"g.V().{has_access}.groupCount().by(label())",
        f"g.E().{has_access}.where(outV().{has_access}).where(inV().{has_access})"
        ".groupCount().by(label())",
    )


@dataclass(frozen=True)
class BusiestLinksBuilder:
    """`GraphPort.busiest_links` (ADR-100 decision 5): the access step on the link and on each
    end, then ordered and paged in the store."""

    edge_type: str | None
    limit: int
    offset: int
    #: ADR-100 Amendment 9: ranked for one node — only links touching it. The access steps are
    #: identical to the whole-case ranking's, so a hidden link of a busy node never surfaces by
    #: being asked for through its node.
    node_id: str | None = None

    def _base(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        label = ""
        if self.edge_type is not None:
            labels = ",".join(
                groovy_string_literal(x) for x in physical_edge_labels(self.edge_type)
            )
            label = f".hasLabel({labels})"
        of_node = (
            f".where(bothV().has(\"id\",{groovy_string_literal(self.node_id)}))"
            if self.node_id is not None
            else ""
        )
        return (
            f"g.E(){label}{of_node}.{has_access}"
            f".where(outV().{has_access}).where(inV().{has_access})"
        )

    def render_total_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        return f"{self._base(access, principal)}.count()"

    def render_page_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        return (
            f'{self._base(access, principal)}.order().by("occurrences",desc).by("id")'
            f".range({self.offset},{self.offset + self.limit})"
            '.project("edge","source","target")'
            ".by(elementMap()).by(outV().elementMap()).by(inV().elementMap())"
        )


def render_link_structure_gremlin(access: AccessFilter, principal: Principal) -> dict[str, str]:
    """`GraphPort.link_structure` (ADR-100 Amendment 5): counts, then ids and ends only."""
    has_access = access.gremlin_has_step(principal)
    nodes = f"g.V().{has_access}"
    edges = f"g.E().{has_access}.where(outV().{has_access}).where(inV().{has_access})"
    return {
        "node_count": f"{nodes}.count()",
        "edge_count": f"{edges}.count()",
        "nodes": f'{nodes}.project("id","type").by(values("id")).by(label())',
        "edges": (
            f'{edges}.project("id","s","t","w").by(values("id"))'
            '.by(outV().values("id")).by(inV().values("id"))'
            '.by(coalesce(values("weight"),constant(1.0)))'
        ),
    }


#: An element's load (`audit.load_id`), "" when no load wrote it. Read from the stored map: a
#: load is shared by thousands of elements, so a top-level copy indexed by it would be the
#: low-cardinality key that made bulk deletes quadratic (`seed_support.DELETE_BATCH`), and nothing
#: reads it by value.
_LOAD_KEY = 'coalesce(values("audit").select("load_id").is(neq(null)),constant(""))'


def _audit_field(name: str, missing: str) -> str:
    return (
        f'coalesce(unfold().values("audit").select("{name}").is(neq(null)).limit(1),'
        f"constant({missing}))"
    )


def render_recent_loads_gremlin(access: AccessFilter, principal: Principal) -> tuple[str, str]:
    """`GraphPort.recent_loads` (ADR-100 Amendment 6): visible nodes, then visible links with both
    ends visible, each grouped by load with its count, newest `created_at` and recipe. The times are
    the stored ISO strings, all UTC, so their greatest is the latest to within a second (a time
    written without its fraction sorts after one written with it)."""
    has_access = access.gremlin_has_step(principal)
    summary = (
        f".group().by({_LOAD_KEY})"
        '.by(fold().project("n","latest","recipe","version")'
        ".by(count(local))"
        '.by(unfold().values("audit").select("created_at").max())'
        f".by({_audit_field('recipe_id', '""')})"
        f".by({_audit_field('recipe_version', '-1')}))"
    )
    return (
        f"g.V().{has_access}{summary}",
        f"g.E().{has_access}.where(outV().{has_access}).where(inV().{has_access}){summary}",
    )


_CONFIRMED_AT = 'values("provenance").select("last_confirmed").is(neq(null))'


def render_recently_confirmed_gremlin(
    access: AccessFilter, principal: Principal, *, limit: int
) -> tuple[str, str]:
    """`GraphPort.recently_confirmed` (ADR-100 Amendment 6): the count, then the page, latest
    first and ties by id, ordered in the store over the stored ISO strings (as above)."""
    base = f"g.V().{access.gremlin_has_step(principal)}.filter({_CONFIRMED_AT})"
    return (
        f"{base}.count()",
        f'{base}.order().by({_CONFIRMED_AT},desc).by("id").range(0,{limit})'
        '.project("node","at","by").by(elementMap()).by(' + _CONFIRMED_AT + ")"
        '.by(coalesce(values("provenance").select("confirmed_by").is(neq(null)),constant("")))',
    )


def render_shared_contacts_gremlin(
    access: AccessFilter,
    principal: Principal,
    node_id: str,
    *,
    edge_type: str,
    min_shared: int,
    limit: int,
) -> tuple[str, str]:
    """`GraphPort.shared_contacts` (ADR-100 Amendment 7 decision 4): one walk out to the node's
    contacts and back to whoever else links to them, each (contact, other) pair once, counted per
    other node. Measured on Enron: 0.5 s for the busiest address, where the same question as a
    pattern took 73 s. The access step is on every link and node on the way (rule 3)."""
    has_access = access.gremlin_has_step(principal)
    labels = groovy_args_literal(physical_edge_labels(edge_type))
    base = (
        f'g.V().has("id",{groovy_string_literal(node_id)}).{has_access}.as("a")'
        f".outE({labels}).{has_access}.inV().{has_access}"
        '.as("x")'
        f".inE({labels}).{has_access}.outV().{has_access}"
        '.where(neq("a")).as("b").dedup().by(select("x","b").by("id"))'
        '.select("b").groupCount().by("id").unfold()'
        f".where(select(values).is(gte({min_shared})))"
    )
    return (
        f"{base}.count()",
        f"{base}.order().by(values,desc).by(keys).limit({limit})"
        '.project("id","n").by(keys).by(values)',
    )
