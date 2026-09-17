"""Dialect-agnostic query builders — `docs/06_DECISIONS.md` ADR-003 amendment.

Each builder describes intent (expand, path, match, neighbourhood stats) and
renders it for one dialect. Only `render_gremlin` exists in Phase 1
(`dialects = {"gremlin"}`); a second dialect is a `render_<dialect>` method
added later, with no change to the callers in `adapter.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from schemas.domain import ExpandRequest, PathRequest, PatternQuery, Principal

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
    """Compiles a bounded `PatternQuery` into a Gremlin traversal by chaining
    `.as(var)`/`.select(var)` steps in the order the pattern's edges are
    given — each edge's `from_var` must already be bound by an earlier node
    or edge, exactly as a caller composing the pattern would build it up."""

    pattern: PatternQuery

    def render_gremlin(self, access: AccessFilter, principal: Principal) -> str:
        if not self.pattern.nodes:
            raise ValueError("PatternQuery must declare at least one node")
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
                raise ValueError(
                    f"pattern edge {edge.edge_type!r} references {edge.from_var!r} before it "
                    "is bound — list edges in traversal order from the first node"
                )
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

        select_args = groovy_args_literal(n.var for n in self.pattern.nodes)
        steps.append(f".select({select_args})")
        steps.append(".by(elementMap())")
        steps.append(f".dedup().limit({self.pattern.limit})")
        return "".join(steps)
