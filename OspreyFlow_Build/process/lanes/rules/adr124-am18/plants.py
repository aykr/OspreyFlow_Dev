"""ADR-124 Amendment 18's plants (rule 15): each puts one lookup of the write path back to the
shape that scanned the store by `id`, runs the tests that claim to catch it, expects them red, and
puts the file back. The harness is v052-index's (`../v052-index/plants.py`: a fresh bytecode cache
for every run, RED only where pytest ran and failed). Live: under the rules lane's lease
(`stack_lease.sh remote rules -- …`, from OspreyFlow_Core); `--offline` leaves the live scale test
and its plants out."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_HARNESS = Path(__file__).resolve().parents[1] / "v052-index" / "plants.py"
_spec = importlib.util.spec_from_file_location("v052_plants", _HARNESS)
assert _spec is not None and _spec.loader is not None
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)

B = "../OspreyFlow_Build/tests"
G = f"{B}/adapters/graph_arcadedb"
SCALE = f"{B}/conformance/graph_port/test_write_path_scale.py"
REVERTED = f"{G}/test_write_onto_a_reverted_node.py"
AUDIENCE = f"{G}/test_edge_audience_merge.py"
MERGE = f"{G}/test_merge_rules_shared_by_both_paths.py"
STRAYS = f"{G}/test_corpus_stats_ignore_stray_records.py"
SHAPES = f"{G}/test_gremlin_bulk_transport_shapes.py"
ADAPTER = "OspreyFlow_Core/packages/adapters/graph_arcadedb/adapter.py"
BULK = "OspreyFlow_Core/packages/adapters/graph_arcadedb/bulk.py"
LIVE = (SCALE,)

PLANTS: list[tuple[str, str, str, str, list[str]]] = [
    ("A1 a node looked up by a scan of the store", ADAPTER,
     '                rid_lit = groovy_string_literal(known[node_id][0])\n'
     '                found = await self._client.gremlin(f"g.V({rid_lit}).elementMap()", session_id=tx)\n',
     "                found = await self._client.gremlin(\n"
     "                    f'g.V().has(\"id\",{groovy_string_literal(node_id)}).elementMap()', session_id=tx\n"
     "                )\n",
     [f"{REVERTED}::test_a_write_onto_a_live_node_still_merges", SCALE]),
    ("A2 a link's existing edge looked for from a scan", ADAPTER,
     "            f'g.V({src_lit}).{step}({label_lit}).has(\"reverted\",false)'\n",
     "            f'g.V().has(\"id\",{groovy_string_literal(source)}).{step}({label_lit}).has(\"reverted\",false)'\n",
     [f"{AUDIENCE}::test_writes_in_two_datasets_are_two_links", SCALE]),
    ("A3 a link's end degree from a scan", ADAPTER,
     "                f'g.V({rid_lit}).bothE({label_lit}).has(\"reverted\",false)'\n",
     "                f'g.V().has(\"id\",{groovy_string_literal(node_id)}).bothE({label_lit}).has(\"reverted\",false)'\n",
     [f"{STRAYS}::test_the_corpus_total_does_not_count_records_only_a_scan_finds"]),
    ("A4 a new link added from its ends by a scan", ADAPTER,
     "                    f'g.V(src).as(\"__src\").V(tgt).addE(\"{type_name}\").from(\"__src\"){property_steps}'\n",
     "                    f'g.V().has(\"id\", src).as(\"__src\").V().has(\"id\", tgt).addE(\"{type_name}\").from(\"__src\"){property_steps}'\n",
     [f"{MERGE}::test_the_aggregate_is_what_one_at_a_time_upserts_leave_in_the_store", SCALE]),
    ("A5 a merged link found by its label and a scan", ADAPTER,
     '                command = f"g.E({groovy_string_literal(rid)}){property_steps}"\n',
     '                command = f"g.E().hasLabel({groovy_string_literal(type_name)}).has(\\"id\\",{groovy_string_literal(edge_id)}){property_steps}"\n',
     [f"{AUDIENCE}::test_a_write_merges_into_the_link_of_its_own_audience_among_several"]),
    ("A6 the bulk write finds each row's ends by a scan", BULK,
     "            ' def t = g.V(r.sr).as(\"a\").V(r.tr).addE(\"' + label + '\")'\n",
     "            ' def t = g.V().has(\"id\", r.s).as(\"a\").V().has(\"id\", r.t).addE(\"' + label + '\")'\n",
     [f"{SHAPES}::test_no_lookup_scans_the_store_by_id", SCALE]),
    ("A7 the bulk stored links from a scan", BULK,
     "            f'g.V(sources).{step}(\"{label}\").has(\"reverted\", false)'\n",
     "            f'g.V().has(\"id\", within(sources)).{step}(\"{label}\").has(\"reverted\", false)'\n",
     [f"{SHAPES}::test_no_lookup_scans_the_store_by_id"]),
    ("A8 the bulk degrees from a scan", BULK,
     "            'g.V(rids).project(\"id\",\"d\").by(values(\"id\"))'\n",
     "            'g.V().has(\"id\", within(rids)).project(\"id\",\"d\").by(values(\"id\"))'\n",
     [f"{SHAPES}::test_no_lookup_scans_the_store_by_id"]),
]


def main() -> int:
    offline = "--offline" in sys.argv[1:]
    every = [G, SCALE]
    plants = PLANTS
    if offline:
        every = [G]
        plants = [(n, r, b, p, [t for t in ts if t not in LIVE]) for n, r, b, p, ts in PLANTS]
        print("offline: the live scale test left out of every plant")
    ignore = [f"--ignore={G}/{f}" for f in ("test_sources_withheld_live.py", "test_datasets_index.py",
                                            "test_client_row_limit.py")]  # fmt: skip
    state, line = harness._run([*every, *ignore])
    print(f"built: {state} - {line}")
    if state != "GREEN":
        return 1
    left = 0
    root = harness.CORE.parent
    for name, rel, built, planted, tests in plants:
        path = root / rel
        source = path.read_text(encoding="utf-8")
        if source.count(built) != 1:
            print(f"{name}: the built text is not in {rel} exactly once; plant not applied")
            left += 1
            continue
        try:
            path.write_text(source.replace(built, planted), encoding="utf-8")
            state, line = harness._run(tests)
        finally:
            path.write_text(source, encoding="utf-8")
        print(f"{name} [{rel}]: {state} - {line}")
        left += 0 if state == "RED" else 1
    state, line = harness._run([*every, *ignore])
    print(f"restored: {state} - {line}")
    return 1 if left or state != "GREEN" else 0


if __name__ == "__main__":
    sys.exit(main())
