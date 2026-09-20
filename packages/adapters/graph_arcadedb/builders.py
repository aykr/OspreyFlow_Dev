"""Dialect-agnostic query builders — `docs/06_DECISIONS.md` ADR-003 amendment.

Each builder describes intent (expand, path, match, neighbourhood stats) and
renders it for one dialect. Only `render_gremlin` exists in Phase 1
(`dialects = {"gremlin"}`); a second dialect is a `render_<dialect>` method
added later, with no change to the callers in `adapter.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from schemas.domain import ExpandRequest, PathRequest, PatternEdge, PatternQuery, Principal

from .access_filter import AccessFilter
from .gremlin_literals import (
    groovy_args_literal,
    groovy_string_list_literal,
    groovy_string_literal,
)
from .naming import physical_type_name

_EDGE_STEP = {"out": "outE", "in": "inE", "both": "bothE"}
_OTHER_VERTEX_STEP = {"out": "inV", "in": "outV", "both": "otherV"}


@dataclass(frozen=True)
class GetNodeBuilder:
    node_id: str
    include_superseded: bool = False

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(
            principal, include_superseded=self.include_superseded
        )
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
            f'__.has({groovy_string_literal(field)},{value_lit})'
            for field in self.identifier_fields
        )
        return (
            f"g.V().or({clauses}).{has_access}"
            f".dedup().limit({self.limit}).elementMap()"
        )


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
    retrieval (`07_BUILD_PLAN.md`'s Phase 5 known-gaps list), scoped to `Location.name`
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


@dataclass(frozen=True)
class ExpandBuilder:
    request: ExpandRequest

    def _edge_label_filter(self) -> str:
        if not self.request.edge_types:
            return ""
        physical = [physical_type_name(t) for t in self.request.edge_types]
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
        # A `gte`/`lte` predicate against a DATETIME property needs an
        # actual `Date` to compare correctly, not a String — see
        # `serialization.py`'s note on `valid_from`/`valid_to`.
        start_millis = int(window.valid_from.timestamp() * 1000)
        clause = f'.has("valid_from",gte(new Date({start_millis}L)))'
        if window.valid_to is not None:
            end_millis = int(window.valid_to.timestamp() * 1000)
            clause += f'.has("valid_from",lte(new Date({end_millis}L)))'
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

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        source_lit = groovy_string_literal(self.request.source)
        target_lit = groovy_string_literal(self.request.target)
        edge_filter = ""
        if self.request.edge_types:
            physical = [physical_type_name(t) for t in self.request.edge_types]
            # See `ExpandBuilder._edge_label_filter`'s comment — the same
            # varargs-not-list bug, same fix.
            edge_filter = f".hasLabel({groovy_args_literal(physical)})"
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
class NeighbourhoodStatsBuilder:
    node_id: str

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        has_access = access.gremlin_has_step(principal)
        node_lit = groovy_string_literal(self.node_id)
        return (
            f'g.V().has("id",{node_lit}).{has_access}.bothE().{has_access}'
            f".where(otherV().{has_access}).groupCount().by(label())"
        )


@dataclass(frozen=True)
class MatchBuilder:
    """Compiles a bounded `PatternQuery` into Gremlin — `01_DOMAIN_MODEL.md` §8.1, widened in
    Phase 7 Stage 4 (`06_DECISIONS.md`). A pattern that linearises into a single chain from one
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
    `has_access` injected at every `.outE()`/`.inV()`/`.in()` exactly as before — the
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
        the whole point (`CLAUDE.md` rule 3/7 — an estimate must be filtered exactly like the
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
        steps.append(f".{has_access}")
        steps.append(f".as({groovy_string_literal(first.var)})")

        bound = {first.var}
        for edge in self.pattern.edges:
            if edge.from_var not in bound:
                return None
            to_node = node_by_var.get(edge.to_var)
            physical_edge_type = physical_type_name(edge.edge_type)
            steps.append(f".select({groovy_string_literal(edge.from_var)})")
            steps.append(f".outE({groovy_string_literal(physical_edge_type)})")
            steps.append(f".{has_access}")
            steps.append(".inV()")
            steps.append(f".{has_access}")
            if to_node and to_node.entity_type:
                physical_to = physical_type_name(to_node.entity_type)
                steps.append(f".hasLabel({groovy_string_literal(physical_to)})")
            steps.append(f".as({groovy_string_literal(edge.to_var)})")
            bound.add(edge.to_var)

        # Every declared node must actually be bound by the walk above — a pattern with more
        # than one fully-disconnected root (no edge ever references the second one at all) would
        # otherwise emit a `.select()` naming a step label nothing ever produced.
        if bound != {n.var for n in self.pattern.nodes}:
            return None

        if count_only:
            assert ceiling is not None  # always passed together — see `render_count_gremlin`
            steps.append(self._count_tail(sorted(n.var for n in self.pattern.nodes), ceiling))
            return "".join(steps)

        select_args = groovy_args_literal(n.var for n in self.pattern.nodes)
        steps.append(f".select({select_args})")
        steps.append(".by(elementMap())")
        steps.append(f".dedup().limit({self.pattern.limit})")
        return "".join(steps)

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
        chain is reversed into a `.where()` step, walked backward with `.in(edge_type)` in
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
            steps.append(f".hasLabel({groovy_string_literal(physical_type_name(primary.entity_type))})")
        if primary.node_id:
            steps.append(f'.has("id",{groovy_string_literal(primary.node_id)})')
        steps.append(f".{has_access}")
        steps.append(f".as({groovy_string_literal(primary.var)})")
        for edge in primary_chain:
            to_node = node_by_var.get(edge.to_var)
            physical_edge_type = physical_type_name(edge.edge_type)
            steps.append(f".select({groovy_string_literal(edge.from_var)})")
            steps.append(f".outE({groovy_string_literal(physical_edge_type)})")
            steps.append(f".{has_access}")
            steps.append(".inV()")
            steps.append(f".{has_access}")
            if to_node and to_node.entity_type:
                steps.append(f".hasLabel({groovy_string_literal(physical_type_name(to_node.entity_type))})")
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
                physical_edge_type = physical_type_name(edge.edge_type)
                reverse_steps.append(f".in({groovy_string_literal(physical_edge_type)})")
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

        # A pinned *secondary* root's own identity is never returned — it is never itself
        # `.as()`-labelled outside its own nested `.where()` check, so it could not be selected at
        # all. The primary root stays in `select()` even when it is also pinned: Gremlin's own
        # `select(x)` (one argument) returns the bound value directly rather than `{x: value}`, a
        # different shape from `select(x, y, ...)` (confirmed empirically — dropping the primary
        # here for a two-node pattern collapses to exactly that single-argument case and the
        # adapter's own multi-key parsing broke against it). Keeping the primary avoids ever
        # emitting a single-argument `select()` for the diamond path; a bare single-pinned-node
        # pattern with no discovered variable at all is `_render_single_chain`'s own scope, not
        # this one, and already shares whatever behaviour that path has for it.
        if count_only:
            assert ceiling is not None  # always passed together — see `render_count_gremlin`
            steps.append(self._count_tail(sorted(primary_bound), ceiling))
            return "".join(steps)

        select_args = groovy_args_literal(sorted(primary_bound))
        steps.append(f".select({select_args})")
        steps.append(".by(elementMap())")
        steps.append(f".dedup().limit({self.pattern.limit})")
        return "".join(steps)
