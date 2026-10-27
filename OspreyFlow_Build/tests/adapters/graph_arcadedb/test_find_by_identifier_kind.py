"""`find_node` with `also`: a property the caller chooses by, among nodes sharing one identifier
value (an Endpoint's `value_normalised` is shared by a handle and an account holding the same text).

`also` cannot be a `has` step: an Endpoint's `endpoint_kind` is not stored as a top-level field, so a
query asking for it matches nothing (found live on ArcadeDB, 27 October 2026, after a version of
this fix put it in the query and its hermetic test passed: rule 15). So the nodes sharing the value
are read, to a bound, and the first whose stored properties carry the asked-for values is taken.
`test_add_by_identifiers_live.py` is the real-store proof; these pin the shape of the read."""

from __future__ import annotations

from adapters.graph_arcadedb.access_filter import AccessFilter
from adapters.graph_arcadedb.adapter import FIND_WITH_ALSO_LIMIT
from adapters.graph_arcadedb.builders import FindByIdentifierBuilder
from ontology.handling import load_uk_le_scheme
from schemas.domain import Principal

READER = Principal(id="reader", clearance="OFFICIAL", org_unit="unit-1")


def _query(limit: int = 1) -> str:
    return FindByIdentifierBuilder(
        "Endpoint", "value_normalised", "SYN-70417", limit=limit
    ).render_gremlin(AccessFilter(load_uk_le_scheme()), READER)


def test_a_plain_lookup_reads_one_node_and_names_no_other_property() -> None:
    query = _query()
    assert query.endswith(".limit(1).elementMap()")
    assert "endpoint_kind" not in query


def test_a_lookup_choosing_by_kind_reads_the_sharing_nodes_not_a_has_step_on_the_kind() -> None:
    query = _query(FIND_WITH_ALSO_LIMIT)
    assert f".limit({FIND_WITH_ALSO_LIMIT})." in query
    assert "endpoint_kind" not in query, "the kind is not a stored field, so it cannot be queried"

