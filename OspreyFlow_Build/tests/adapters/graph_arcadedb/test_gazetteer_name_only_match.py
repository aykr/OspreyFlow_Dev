"""The query the store is sent for the case's searches (ADR-147 Amendment 1; the orchestrator's
ruling of 9 November 2026): for a request reader, a node in a `gazetteer-*` dataset is matched
on its name alone; the Conduit's own work matches every field. What ArcadeDB does with it is
proven live (`tests/ingest/test_gazetteer_place_search_live.py`,
`test_the_case_s_own_searches_match_a_gazetteer_place_on_its_name_alone`): a string can only
show the rule is asked for.
"""

from __future__ import annotations

from adapters.graph_arcadedb.access_filter import AccessFilter
from adapters.graph_arcadedb.builders import SearchNodesBuilder, SuggestNodesBuilder
from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal

READER = Principal(id="a", clearance="OFFICIAL", org_unit="unit-1", datasets=["gazetteer-osm-x"])
CONDUIT = READER.model_copy(update={"datasets": None})
GUARD = """__.not(__.values("datasets").unfold().is(TextP.startingWith('gazetteer-')))"""


def _queries(principal: Principal) -> list[str]:
    access = AccessFilter(load_uk_le_scheme())
    fields = ("name", "osm_id", "uprn")
    return [
        SearchNodesBuilder(fields, "node/1").render_gremlin(access, principal),
        SuggestNodesBuilder(("Location",), fields, "node/1").render_gremlin(access, principal),
    ]


def test_a_request_reader_matches_a_gazetteer_node_on_its_name_alone() -> None:
    for query in _queries(READER):
        assert f"__.and({GUARD},__.or(" in query
        # The name is matched outside the guard, the identifiers inside it.
        assert query.index("__.has('name'") < query.index(GUARD) < query.index("__.has('osm_id'")


def test_the_conduit_s_own_work_matches_every_field() -> None:
    for query in _queries(CONDUIT):
        assert GUARD not in query
