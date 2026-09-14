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
class ExpandBuilder:
    request: ExpandRequest

    def _edge_label_filter(self) -> str:
        if not self.request.edge_types:
            return ""
        physical = [physical_type_name(t) for t in self.request.edge_types]
        return f".hasLabel({groovy_string_list_literal(physical)})"

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
            edge_filter = f".hasLabel({groovy_string_list_literal(physical)})"
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
