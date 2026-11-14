"""`search_nodes` finds what the query as built found, type by type (ADR-124 Amendment 21), live
against ArcadeDB, with the deployment's own ontology.

`name` is searchable because `Location` and `Organisation` (among others) index it. An `Account`
declares `name` without indexing it, and the write keeps an unindexed property only inside
`properties` (`serialization._indexed_property_names`: the identifiers and indexed properties are
flattened), so the query as built, `g.V().or(__.has('name', v), …)`, never found an Account by its
name (measured on stack d, 14 November 2026). Amendment 21 asks each type only the fields it keeps
flattened, so it finds the same: the Organisation by its name, the Account by its indexed
`account_number`, each only by a reader who may see it (rule 3). The new answer is compared with
the old query's own, sent to the same store. The default ontology the rest of this suite applies
has no such type, so this case applies the deployment's (`Account` comes from a pack).
"""

from __future__ import annotations

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.builders import match_any_field
from adapters.graph_arcadedb.gremlin_literals import groovy_string_literal
from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import Principal

from .test_suite import CLEARED, OFFICIAL, _node, _write

NAME = "Harbour Ledger Holdings"
#: A request reader (ADR-099) of case-a's dataset.
REQUEST = Principal(id="reader-case", clearance="SECRET", org_unit="unit-1", datasets=["case-a"])


async def _old(adapter: GraphArcadeDBAdapter, query: str, principal: Principal) -> set[str]:
    """The query as built before Amendment 21, word for word, sent to the same store."""
    schema = adapter._require_schema()
    fields = sorted(
        {f for e in schema.entity_types for f in e.identifiers}
        | {p.name for e in schema.entity_types for p in e.properties if p.indexed}
    )
    value = groovy_string_literal(query)
    matched = match_any_field(
        lambda f: f"__.has({groovy_string_literal(f)},{value})", tuple(fields), principal
    )
    has_access = adapter._access.gremlin_has_step(principal)
    rows = await adapter._client.gremlin(
        f"g.V().{matched}.{has_access}.dedup().limit(101).elementMap()"
    )
    return {str(r["id"]) for r in rows}


async def test_each_type_is_searched_as_the_query_as_built_searched_it() -> None:
    async with arcadedb_adapter(load_deployment_ontology(), load_uk_le_scheme()) as adapter:
        (open_account, secret_account, organisation, other_case), _ = await _write(
            adapter,
            [
                _node(
                    "Account",
                    classification="OFFICIAL",
                    account_number="A-1",
                    name=NAME,
                    datasets=["case-a"],
                ),
                _node(
                    "Account",
                    classification="SECRET",
                    account_number="A-2",
                    name=NAME,
                    datasets=["case-a"],
                ),
                _node("Organisation", classification="OFFICIAL", name=NAME, datasets=["case-a"]),
                _node("Organisation", classification="OFFICIAL", name=NAME, datasets=["case-b"]),
            ],  # fmt: skip
            [],
        )
        expected = {
            (NAME, "cleared"): {organisation, other_case},
            (NAME, "official"): {organisation, other_case},
            (NAME, "request"): {organisation},
            ("A-2", "cleared"): {secret_account},
            ("A-2", "official"): set(),
            ("A-1", "request"): {open_account},
            ("A-3", "cleared"): set(),
        }
        readers = {"cleared": CLEARED, "official": OFFICIAL, "request": REQUEST}
        for (query, reader), ids in expected.items():
            new = {n.id for n in await adapter.search_nodes(query, readers[reader], limit=101)}
            assert new == ids, (query, reader, new)
            assert new == await _old(adapter, query, readers[reader]), (query, reader)
