"""`search_nodes` matches a searchable field on a node of any type that holds it (ADR-124
Amendment 21), live against ArcadeDB, with the deployment's own ontology.

`name` is searchable because `Location` (and others) index it. An `Account` declares `name` without
indexing it, and the query as built, `g.V().or(...)` with no label, found an Account by its name.
Amendment 21 finds its candidates by SQL first, one lookup per stored type and field that type can
hold, so the Account must still be found, and found only by a reader who may see it (rule 3). The
default ontology the rest of this suite applies has no such type, so this case applies the
deployment's (`ontology.packs.load_deployment_ontology`, where `Account` comes from a pack).
"""

from __future__ import annotations

from adapters.graph_arcadedb.testing import arcadedb_adapter
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import Principal

from .test_suite import CLEARED, OFFICIAL, _node, _write

NAME = "Harbour Ledger Holdings"
#: A request reader (ADR-099), who is matched on no gazetteer-only identifier.
REQUEST = Principal(id="reader-case", clearance="SECRET", org_unit="unit-1", datasets=["case-a"])


async def test_a_node_is_found_by_a_searchable_field_its_own_type_does_not_index() -> None:
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
                _node(
                    "Account",
                    classification="OFFICIAL",
                    account_number="A-3",
                    name=NAME,
                    datasets=["case-b"],
                ),
            ],  # fmt: skip
            [],
        )
        everything = {open_account, secret_account, organisation, other_case}
        assert {n.id for n in await adapter.search_nodes(NAME, CLEARED)} == everything
        assert {n.id for n in await adapter.search_nodes(NAME, OFFICIAL)} == everything - {
            secret_account
        }
        # A request reader of case-a's dataset: the three there, the SECRET one by clearance.
        assert {n.id for n in await adapter.search_nodes(NAME, REQUEST)} == everything - {
            other_case
        }
        # By a field the Account indexes, as before.
        assert {n.id for n in await adapter.search_nodes("A-2", CLEARED)} == {secret_account}
        assert await adapter.search_nodes("A-2", OFFICIAL) == []
