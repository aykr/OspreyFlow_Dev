"""ADR-150's plants (rule 15): each removes one piece of the search index feed at its real call
site, runs the tests that claim to catch it, expects them red, and puts the file back (in a
`finally`). Live: run under the rules lane's lease on its stack (`stack_lease.sh remote rules -- …`,
from OspreyFlow_Core, the stack's ports pinned by `remote`); the offline tests among them need no
store.

Prints each plant's raw pytest summary line and RED, GREEN or BROKEN (a collection error, an error in
a set-up, or nothing run: never read as red); exits 1 if any was not RED or the built tree is not
green before and after. The output, unfiltered, is `PLANTS_RECORD.txt`, headed by the code's identity.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
B = "../OspreyFlow_Build/tests"
OUTBOX = f"{B}/conformance/graph_port/test_index_outbox.py"
FEED = f"{B}/services/search_index/test_feed_live.py"
DOC = f"{B}/services/search_index/test_document.py"
CLIENT = f"{B}/services/search_index/test_client.py"
REACH = f"{B}/services/search_index/test_index_feed_reach.py"
ADAPTER = "OspreyFlow_Core/packages/adapters/graph_arcadedb/adapter.py"
INDEXER = "OspreyFlow_Core/services/search_index/indexer.py"
DOCUMENT = "OspreyFlow_Core/services/search_index/document.py"
REBUILD = "OspreyFlow_Core/services/search_index/rebuild.py"

PLANTS: list[tuple[str, str, str, str, list[str]]] = [
    # --- decision 1: the outbox, by event type, each at its own write --------------------------
    ("V1 a load records nothing", ADAPTER,
     "        await self._index_pending(ids, tx)  # ADR-150 decision 1: a load\n", "",
     [f"{OUTBOX}::test_a_load_records_each_node_it_wrote", f"{FEED}::test_a_load_reaches_the_index"]),
    ("V2 a merge records nothing", ADAPTER,
     "        await self._index_pending(_same_as_ends(edges), tx)  # ADR-150 decision 1: a merge\n", "",
     [f"{OUTBOX}::test_a_merge_records_both_ends_of_a_same_as_and_nothing_for_another_link",
      f"{FEED}::test_a_merge_re_reads_both_ends_and_adds_no_cluster"]),
    ("V3 a merge loaded in bulk records nothing", ADAPTER,
     "        await self._index_pending(_same_as_ends(edges), None)\n", "",
     [f"{OUTBOX}::test_a_merge_loaded_in_bulk_records_both_ends"]),
    ("V4 a merge superseded records nothing", ADAPTER,
     "            await self._index_pending([replacement.source, replacement.target], tx)\n",
     "            pass\n",
     [f"{OUTBOX}::test_a_merge_superseded_records_both_ends"]),
    ("V5 a new version records nothing", ADAPTER,
     "        await self._index_pending([node_id, new_node_id], tx)  # ADR-150 decision 1: a new version\n",
     "",
     [f"{OUTBOX}::test_a_new_version_records_the_old_revision_and_the_new",
      f"{FEED}::test_a_new_version_replaces_the_old_revisions_document"]),
    ("V6 a promotion records nothing", ADAPTER,
     "        await self._index_pending(list(node_ids), tx)  # ADR-150 decision 1: a promotion\n", "",
     [f"{OUTBOX}::test_a_promotion_and_its_revert_record_each_node",
      f"{FEED}::test_a_promotion_and_its_revert_change_the_documents_datasets"]),
    ("V7 a promotion's revert records nothing", ADAPTER,
     "                    await self._index_pending([str(r[\"id\"]) for r in found], tx)\n",
     "                    pass\n",
     [f"{OUTBOX}::test_a_promotion_and_its_revert_record_each_node",
      f"{FEED}::test_a_promotion_and_its_revert_change_the_documents_datasets"]),
    ("V8 a revert records nothing", ADAPTER,
     "        await self._index_pending(  # ADR-150 decision 1: a deletion\n"
     "            [i for kind, _, ids in plan if kind == \"node\" for i in ids], tx\n"
     "        )\n", "",
     [f"{OUTBOX}::test_a_revert_records_each_node_it_took_back",
      f"{FEED}::test_a_deletion_takes_the_document_and_its_text_out"]),
    ("V9 a withdrawal records nothing", ADAPTER,
     "        await self._index_pending(list(node_ids), tx)  # ADR-150 decision 1: a deletion\n", "",
     [f"{OUTBOX}::test_a_withdrawal_and_its_restore_record_each_node"]),
    ("V10 a deleted case layer records nothing", ADAPTER,
     "                    await self._index_pending(ids, tx)\n", "                    pass\n",
     [f"{OUTBOX}::test_a_deleted_case_layer_records_each_node_it_withdrew"]),
    ("V11 a withdrawal's restore records nothing", ADAPTER,
     "        await self._index_pending(nodes, tx)  # ADR-150 decision 1: a deletion taken back\n", "",
     [f"{OUTBOX}::test_a_withdrawal_and_its_restore_record_each_node"]),
    ("V12 the outbox written outside the write's transaction", ADAPTER,
     "                params={\"rows\": [{\"node_id\": node_id} for node_id in chunk]},\n"
     "                session_id=tx,\n",
     "                params={\"rows\": [{\"node_id\": node_id} for node_id in chunk]},\n"
     "                session_id=None,\n",
     [f"{OUTBOX}::test_a_rolled_back_write_records_nothing"]),
    # --- decision 2: the indexer's read and its deletes --------------------------------------
    ("V13 the indexer's read gives a node not live", ADAPTER,
     "                if record.get(\"reverted\") is True or record.get(\"superseded_by\"):\n",
     "                if False:\n",
     [f"{OUTBOX}::test_the_indexers_read_gives_a_live_node_whole_and_none_for_one_not_live",
      f"{FEED}::test_a_new_version_replaces_the_old_revisions_document"]),
    ("V14 a node not live is left in the index", INDEXER,
     "            body.append({\"delete\": {\"_index\": index, \"_id\": node_id}})\n", "",
     [f"{FEED}::test_a_deletion_takes_the_document_and_its_text_out",
      f"{FEED}::test_a_new_version_replaces_the_old_revisions_document"]),
    ("V15 a Document's text records nothing", "OspreyFlow_Core/services/api/review.py",
     "                \"INSERT INTO search_text_pending (document_id) VALUES ($1)\", document_id\n",
     "                \"SELECT $1::text\", document_id\n",
     [f"{FEED}::test_a_deletion_takes_the_document_and_its_text_out"]),
    ("V16 a change during a rebuild not sent to the index being built", INDEXER,
     "            targets.append(building_alias(self._alias))\n", "            pass\n",
     [f"{FEED}::test_a_change_during_a_rebuild_reaches_the_index_being_built_too"]),
    # --- decision 3: the document ------------------------------------------------------------
    ("V17 a node's handling code not copied", DOCUMENT,
     "        \"handling_code\": node.handling.handling_code,\n", "",
     [f"{DOC}::test_a_nodes_document_copies_its_access_fields_and_holds_no_cluster_or_source"]),
    ("V18 a gazetteer place indexed whole", DOCUMENT,
     "    if is_gazetteer_held(seen):\n", "    if False:\n",
     [f"{DOC}::test_a_gazetteer_place_carries_its_name_alone"]),
    ("V19 a text's unit not carried", DOCUMENT,
     "        \"text_owning_unit\": text_owning_unit,\n", "",
     [f"{DOC}::test_a_documents_text_is_a_document_of_its_own_read_by_its_unit",
      f"{FEED}::test_a_deletion_takes_the_document_and_its_text_out"]),
    # --- decisions 4 and 5: the rebuild and the drift check -----------------------------------
    ("V20 a stale document not reported", REBUILD,
     "                elif indexed[document[\"id\"]] != fingerprint(document):\n",
     "                elif False:\n",
     [f"{FEED}::test_the_drift_check_finds_each_difference_and_the_rebuild_mends_them"]),
    ("V21 the rebuild leaves the alias where it was", REBUILD,
     "        {\"add\": {\"index\": index, \"alias\": alias}},\n", "",
     [f"{FEED}::test_the_drift_check_finds_each_difference_and_the_rebuild_mends_them"]),
    # --- rule 4: the unfiltered read reached by the feed alone; decision 7: the address -------
    ("V22 a route reads through the indexer's read", "OspreyFlow_Core/services/api/search.py",
     "from __future__ import annotations\n",
     "from __future__ import annotations\n\n_READ = \"nodes_for_index\"\n",
     [f"{REACH}::test_no_route_or_other_module_reaches_the_indexers_reads"]),
    ("V23 the host and port win over the URL", "OspreyFlow_Core/services/search_index/client.py",
     "        url = (env.get(\"OPENSEARCH_URL\") or \"\").strip()\n", "        url = \"\"\n",
     [f"{CLIENT}::test_the_url_wins_over_host_and_port"]),
]


def _run(tests: list[str]) -> tuple[str, str]:
    """RED only where pytest ran the tests and some failed (exit 1, "failed" in its summary, no
    error); a collection error, an error in a set-up or nothing run is BROKEN, never read as red."""
    done = subprocess.run(
        [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider",
         "-p", "no:randomly", "-q", *tests],
        cwd=CORE, capture_output=True, text=True, check=False,
    )  # fmt: skip
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    failed = [line for line in lines if line.startswith(("FAILED", "ERROR"))]
    summary = lines[-1] if lines else done.stderr.strip()
    said = " | ".join([*failed, summary])
    if done.returncode == 0:
        return "GREEN", said
    if done.returncode == 1 and " failed" in summary and " error" not in summary:
        return "RED", said
    return "BROKEN", said


def main() -> int:
    every = [OUTBOX, FEED, DOC, CLIENT, REACH]
    state, line = _run(every)
    print(f"built: {state} - {line}")
    if state != "GREEN":
        return 1
    green_left = 0
    root = CORE.parent
    for name, rel, built, planted, tests in PLANTS:
        path = root / rel
        source = path.read_text(encoding="utf-8")
        if source.count(built) != 1:
            print(f"{name}: the built text is not in {rel} exactly once; plant not applied")
            green_left += 1
            continue
        try:
            path.write_text(source.replace(built, planted), encoding="utf-8")
            state, line = _run(tests)
        finally:
            path.write_text(source, encoding="utf-8")
        print(f"{name} [{rel}]: {state} - {line}")
        green_left += 0 if state == "RED" else 1
    state, line = _run(every)
    print(f"restored: {state} - {line}")
    return 1 if green_left or state != "GREEN" else 0


if __name__ == "__main__":
    sys.exit(main())
