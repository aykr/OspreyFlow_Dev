"""The stand-ins' refusal of a lookup by id that reads the whole store (ADR-124 Amendment 18), shown
on each shape it must catch and on the shapes the write path sends, which it must let through
(rule 15: a gate shown red, on the shapes the code emits)."""

from __future__ import annotations

import pytest

from tests.adapters.graph_arcadedb.edge_store import refuse_scans

SCANS = [
    'g.V().has("id",\'a\').elementMap()',
    "g.V().has('id','a').elementMap()",
    'g.E().hasLabel(\'mx_X\').has("id",\'e\').property("x",1)',
    'g.V().has("reverted",false).has("id",\'a\').elementMap()',
    'g.V(\'#1:0\').as("s").V().has("id",\'b\').addE("mx_X").from("s")',
    'g.V().hasLabel(\'mx_Person\').hasNot("superseded_by").has(\'id\',\'a\')',
    'g.V().has("datasets",within(\'a\')).has("id",\'b\')',
]
ALLOWED = [
    "g.V('#1:0').elementMap()",
    'g.V(\'#1:0\').outE(\'mx_X\').has("reverted",false).hasNot("superseded_by")'
    '.where(inV().has("id",\'b\')).elementMap()',
    'g.V().outE(\'mx_X\').has("reverted",false).hasNot("superseded_by").values("occurrences").sum()',
    'g.V(\'#1:0\').outE(\'mx_X\').has("id",\'e\').property("x",1)',
]


@pytest.mark.parametrize("query", SCANS)
def test_a_whole_store_lookup_by_id_is_refused(query: str) -> None:
    with pytest.raises(AssertionError, match="scans the whole store"):
        refuse_scans(query)


@pytest.mark.parametrize("query", ALLOWED)
def test_the_write_paths_own_shapes_pass(query: str) -> None:
    refuse_scans(query)
