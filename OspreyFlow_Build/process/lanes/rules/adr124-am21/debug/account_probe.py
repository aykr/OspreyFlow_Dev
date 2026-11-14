"""Why the live Account case found no Account by name: a throwaway database, the case's nodes, then
the old query, the new search, the candidate SQL and the stored record, side by side."""
import asyncio, sys
from pathlib import Path
B = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(B)]
from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.graph_arcadedb.builders import render_field_record_id_lookup_sql
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from tests.conformance.graph_port.test_suite import CLEARED, _node, _write

async def main() -> None:
    async with arcadedb_adapter(load_deployment_ontology(), load_uk_le_scheme()) as a:
        ids, _ = await _write(a, [_node("Account", classification="OFFICIAL", account_number="A-1", name="Harbour X", datasets=["case-a"]),
                                  _node("Organisation", classification="OFFICIAL", name="Harbour X", datasets=["case-a"])], [])
        c = a._client
        print("ids", ids)
        print("types with unique id:", sorted(t for t in await a._types_with_unique_id("vertex") if "Account" in t or "Organisation" in t))
        for t in ("mx_Account", "mx_Organisation"):
            print(t, "sql name:", await c.sql(render_field_record_id_lookup_sql(t, "name"), params={"value": "Harbour X"}))
            rows = await c.sql(f"SELECT * FROM `{t}` LIMIT 1")
            print(t, "stored keys:", sorted(rows[0].keys()) if rows else None, {k: v for k, v in (rows[0] if rows else {}).items() if "name" in k.lower() or k == "properties"})
        print("new search:", [n.id for n in await a.search_nodes("Harbour X", CLEARED)])
        schema = a._require_schema()
        acc = [e for e in schema.entity_types if e.name == "Account"]
        print("Account in schema:", bool(acc), [p.name for p in acc[0].properties] if acc else None)

asyncio.run(main())
