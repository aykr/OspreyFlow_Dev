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
LOOKUP = "OspreyFlow_Core/packages/adapters/graph_arcadedb/lookup.py"
REBUILD = "OspreyFlow_Core/services/search_index/rebuild.py"
TRIPS = f"{G}/test_write_path_round_trips.py"
REFUSE = f"{G}/test_refuse_scans.py"
DRIFT = f"{B}/services/search_index/test_drift_streams.py"
LINKS_ONCE = f"{B}/ingest/test_run_writes_each_link_once.py"
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
    ("A5 a merged link written by its record in the id index (a stray copy)", ADAPTER,
     '                    f"g.V({groovy_string_literal(ends[write.source][0])})"\n'
     '                    f".{step}({groovy_string_literal(type_name)})"\n'
     "                    f'.has(\"id\",{groovy_string_literal(edge_id)}){property_steps}'\n",
     '                    f"g.E({groovy_string_literal((await self._client.sql('
     "f'SELECT @rid AS rid, id FROM `{type_name}` WHERE id IN :ids', "
     'params={\"ids\": [edge_id]}, session_id=tx))[0][\"rid\"])}){property_steps}"\n',
     [f"{AUDIENCE}::test_a_merge_is_written_to_the_link_a_traversal_reaches_not_a_stray_record"]),
    ("A5b a merged link found by its label and a scan", ADAPTER,
     '                    f"g.V({groovy_string_literal(ends[write.source][0])})"\n'
     '                    f".{step}({groovy_string_literal(type_name)})"\n',
     '                    f"g.E().hasLabel({groovy_string_literal(type_name)})"\n',
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
    # The live scale test alone, each against one scanning shape: red by its own measure, not by
    # an offline test's refusal (rule 15's second paragraph).
    ("A9 the scale test: a node looked up by a scan", ADAPTER,
     '                rid_lit = groovy_string_literal(known[node_id][0])\n'
     '                found = await self._client.gremlin(f"g.V({rid_lit}).elementMap()", session_id=tx)\n',
     "                found = await self._client.gremlin(\n"
     "                    f'g.V().has(\"id\",{groovy_string_literal(node_id)}).elementMap()', session_id=tx\n"
     "                )\n",
     [SCALE]),
    ("A10 the scale test: a new link added from its ends by a scan", ADAPTER,
     "                    f'g.V(src).as(\"__src\").V(tgt).addE(\"{type_name}\").from(\"__src\"){property_steps}'\n",
     "                    f'g.V().has(\"id\", src).as(\"__src\").V().has(\"id\", tgt).addE(\"{type_name}\").from(\"__src\"){property_steps}'\n",
     [SCALE]),
    ("A11 the scale test: the bulk write's ends by a scan", BULK,
     "            ' def t = g.V(r.sr).as(\"a\").V(r.tr).addE(\"' + label + '\")'\n",
     "            ' def t = g.V().has(\"id\", r.s).as(\"a\").V().has(\"id\", r.t).addE(\"' + label + '\")'\n",
     [SCALE]),
    ("A12 a bulk row with no end dropped unsaid", BULK,
     "        if missing:\n", "        if False:\n",
     [f"{SHAPES}::test_a_rows_end_not_in_the_graph_is_refused_in_words_never_dropped"]),
    ("A13 an id written earlier in the call not found again", ADAPTER,
     "            if node_id in written:\n", "            if False:\n",
     [f"{SCALE}::test_one_call_writing_one_node_twice_ends_as_one_node"]),
    # The lane review of 14 November, its second round: each fix put back, red by its own test.
    ("R1 a node write onto an id another type holds goes ahead", ADAPTER,
     "            if held is not None and held[1] != physical_type_name(write.type):\n",
     "            if False:\n",
     [f"{TRIPS}::test_a_node_write_onto_an_id_another_type_holds_is_refused"]),
    ("R2 a link's ends asked of every type", ADAPTER,
     "            ids, tx=tx, types=None if types is None else sorted(types)\n",
     "            ids, tx=tx, types=None\n",
     [f"{TRIPS}::test_a_link_write_asks_only_the_types_its_link_joins"]),
    ("R3 an end missed by the narrow question not asked again", ADAPTER,
     "        if missing and types is not None:\n", "        if False:\n",
     [f"{TRIPS}::test_an_end_of_a_type_the_link_does_not_join_is_refused_for_its_type_not_missing"]),
    ("R4 one id in two types kept silently", LOOKUP,
     "                if node_id in found and found[node_id][1] != type_name:\n",
     "                if False:\n",
     [f"{TRIPS}::test_one_id_held_by_two_types_stops_the_write"]),
    ("D1 documents no stream reads not counted", REBUILD,
     "    report.unread_count = max(0, report.index_documents - nodes_stream.seen - texts_stream.seen)\n",
     "    report.unread_count = 0\n",
     [f"{DRIFT}::test_a_document_no_stream_reads_is_counted_unread_never_passed_over"]),
    ("D2 a document without its sort key read as one with it", REBUILD,
     "            if len(keyed) < len(hits):\n                self._done = True\n",
     "            keyed = keyed + [h for h in hits if h not in keyed]\n",
     [f"{DRIFT}::test_a_document_no_stream_reads_is_counted_unread_never_passed_over"]),
    ("D3 the stand-in takes a page over the result window", f"{B[3:]}/services/search_index/fake_opensearch.py",
     "        if size > self.max_result_window:\n", "        if False:\n",
     [f"{DRIFT}::test_a_page_larger_than_the_result_window_is_refused_as_opensearch_refuses_it"]),
    ("S1 the scan refusal as it was (double quotes, hasLabel alone)", f"{B[3:]}/adapters/graph_arcadedb/edge_store.py",
     '''    r"""(^g|\\.)(V|E)\\(\\)(\\.(hasLabel|has|hasNot)\\((?:[^()]|\\([^()]*\\))*\\))*?\\.has\\((["\'])id\\5"""\n''',
     '''    r\'(^g|\\.)(V|E)\\(\\)(\\.hasLabel\\([^)]*\\))?\\.has\\("id"\'\n''',
     [REFUSE]),
    ("I1 the ingest stand-in reading the old shape (the source's id, not its record id)",
     f"{B[3:]}/ingest/combined_run_support.py",
     "            src, label, tgt = self.vertex_id(quoted[0]), quoted[1], quoted[-1]\n",
     "            src, label, tgt = quoted[1], quoted[2], quoted[-1]\n",
     [LINKS_ONCE]),
]


def main() -> int:
    offline = "--offline" in sys.argv[1:]
    every = [G, SCALE, DRIFT, LINKS_ONCE]
    plants = PLANTS
    if offline:
        every = [G, DRIFT, LINKS_ONCE]
        plants = [
            (n, r, b, p, kept)
            for n, r, b, p, ts in PLANTS
            if (kept := [t for t in ts if not t.startswith(LIVE)])
        ]
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
