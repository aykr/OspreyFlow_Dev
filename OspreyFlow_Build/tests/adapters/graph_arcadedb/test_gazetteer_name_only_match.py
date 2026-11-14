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
#: A search's candidates (ADR-124 Amendment 21): the match is applied to them in the traversal.
RIDS = ("#9:0",)
#: ADR-147 Amendment 2: a place in a gazetteer dataset, or a case's copy of one by its provenance.
GUARD = (
    """__.not(__.or(__.values("datasets").unfold().is(TextP.startingWith('gazetteer-')),"""
    """__.values("provenance").select("gazetteer")))"""
)


def _queries(principal: Principal) -> list[str]:
    access = AccessFilter(load_uk_le_scheme())
    fields = ("name", "osm_id", "uprn")
    return [
        SearchNodesBuilder(fields, "node/1", record_ids=RIDS).render_gremlin(access, principal),
        SuggestNodesBuilder(("Location",), fields, "node/1").render_gremlin(access, principal),
    ]


def test_a_request_reader_matches_a_gazetteer_node_on_its_name_alone() -> None:
    for query in _queries(READER):
        assert f"__.and({GUARD},__.or(" in query
        # The name is matched outside the guard, a case's own identifier inside it; `osm_id`, only
        # a gazetteer's, is matched on no node at all (Amendment 3).
        assert query.index("__.has('name'") < query.index(GUARD) < query.index("__.has('uprn'")
        assert "__.has('osm_id'" not in query


def test_the_conduit_s_own_work_matches_every_field() -> None:
    for query in _queries(CONDUIT):
        assert GUARD not in query


def test_a_type_with_no_name_field_matches_a_gazetteer_node_on_nothing() -> None:
    """A Person has no `name`: its fields are all guarded, so a person in a gazetteer dataset is
    found by none of them (the form `or(__.and(guard, __.or(...)))`)."""
    access = AccessFilter(load_uk_le_scheme())
    query = SuggestNodesBuilder(("Person",), ("family_name", "nino"), "Smi").render_gremlin(
        access, READER
    )
    assert f"or(__.and({GUARD},__.or(" in query
    assert "__.has('family_name'" in query and query.index(GUARD) < query.index("__.has('nino'")


#: ADR-147 Amendment 3: the identifiers only a gazetteer carries, never matched for a request
#: reader on any node, since no reader is sent them; `uprn` is a case's own and is matched still.
ONLY = ("osm_id", "os_place_id", "gss_code", "gnis_feature_id", "tiger_geoid", "nad_address_id")


def _all_fields(principal: Principal, types: tuple[str, ...] = ("Location",)) -> list[str]:
    access = AccessFilter(load_uk_le_scheme())
    fields = ("name", "uprn", *ONLY)
    return [
        SearchNodesBuilder(fields, "node/1", record_ids=RIDS).render_gremlin(access, principal),
        SuggestNodesBuilder(types, fields, "node/1").render_gremlin(access, principal),
    ]


def test_a_request_reader_matches_no_node_on_a_gazetteer_only_identifier() -> None:
    case_reader = READER.model_copy(update={"datasets": ["case-a"]})
    for query in _all_fields(case_reader):
        for field in ONLY:
            assert f"__.has('{field}'" not in query, (field, query)
        assert "__.has('name'" in query and "__.has('uprn'" in query


def test_the_conduit_s_own_work_still_matches_them() -> None:
    for query in _all_fields(CONDUIT):
        assert all(f"__.has('{field}'" in query for field in ONLY), query


def test_a_search_by_a_gazetteer_only_identifier_alone_matches_nothing() -> None:
    """A type whose only identifier is one of them: the search is asked, and matches nothing,
    rather than falling back to every field."""
    access = AccessFilter(load_uk_le_scheme())
    case_reader = READER.model_copy(update={"datasets": ["case-a"]})
    query = SearchNodesBuilder(("osm_id",), "node/1", record_ids=RIDS).render_gremlin(
        access, case_reader
    )
    assert "__.has('osm_id'" not in query
    # Exactly the step that keeps no node, before the access step, dedup and limit: never a
    # bare or() or a fall-back that matches every node. ArcadeDB's answer to it is proven live
    # (`test_gazetteer_only_ids_withheld_everywhere_live.py`).
    assert query.startswith("g.V(['#9:0']).or(__.not(__.identity())).")
    for builder in (
        SuggestNodesBuilder(("Location",), ("osm_id", "os_place_id"), "7"),
        SearchNodesBuilder(("osm_id", "os_place_id"), "7", record_ids=RIDS),
    ):
        assert ".or(__.not(__.identity()))." in builder.render_gremlin(access, case_reader)
