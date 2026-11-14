"""ADR-150's plants (rule 15): each removes one piece of the search index feed at its real call
site, runs the tests that claim to catch it, expects them red, and puts the file back (in a
`finally`). Live: run under the rules lane's lease on its stack (`stack_lease.sh remote rules -- …`,
from OspreyFlow_Core, the stack's ports pinned by `remote`); the offline tests among them need no
store, and `--offline` runs those alone (no lease: the live files and their plants left out).

Prints each plant's raw pytest summary line and RED, GREEN or BROKEN (a collection error, an error in
a set-up, or nothing run: never read as red); exits 1 if any was not RED or the built tree is not
green before and after. The output, unfiltered, is `PLANTS_RECORD.txt`, headed by the code's identity.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"
B = "../OspreyFlow_Build/tests"
OUTBOX = f"{B}/conformance/graph_port/test_index_outbox.py"
FEED = f"{B}/services/search_index/test_feed_live.py"
DOC = f"{B}/services/search_index/test_document.py"
CLIENT = f"{B}/services/search_index/test_client.py"
REACH = f"{B}/services/search_index/test_index_feed_reach.py"
RUN = f"{B}/services/search_index/test_run.py"
HARNESS = f"{B}/harness/test_search_index_render_and_restore.py"
SIGV4 = f"{B}/services/search_index/test_client_sigv4.py"
SEEDS = f"{B}/test_seed_support.py"
ADAPTER = "OspreyFlow_Core/packages/adapters/graph_arcadedb/adapter.py"
INDEXER = "OspreyFlow_Core/services/search_index/indexer.py"
DOCUMENT = "OspreyFlow_Core/services/search_index/document.py"
REBUILD = "OspreyFlow_Core/services/search_index/rebuild.py"
MAPPING = "OspreyFlow_Core/services/search_index/mapping.py"
CLIENTPY = "OspreyFlow_Core/services/search_index/client.py"
REVIEW = "OspreyFlow_Core/services/api/review.py"
BULK = f"{B}/services/search_index/test_bulk_cap.py"
REFUSED = f"{B}/services/search_index/test_refused.py"
CA = f"{B}/services/search_index/test_client_ca.py"
RANK = f"{B}/services/search_index/test_mapping_strict_ranking.py"
LAURIUM = f"{B}/adapters/extract_laurium/test_findings_inferred.py"
PENDING = f"{B}/services/search_index/test_pending.py"
DRIFT = f"{B}/services/search_index/test_drift_streams.py"
STAND_IN = "OspreyFlow_Build/tests/adapters/extract_laurium/review_queue.py"
REACH_TEST = "OspreyFlow_Build/tests/services/search_index/test_index_feed_reach.py"
#: Tests that need the leased stack; `--offline` leaves them, and every plant that names one, out.
LIVE = (OUTBOX, FEED)

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
    ("V24 every replica drains, lease or none", "OspreyFlow_Core/services/search_index/run.py",
     "    if await store.set(LEASE_KEY, me, nx=True, ex=LEASE_SECONDS):\n",
     "    if True:\n",
     [f"{RUN}::test_the_lease_is_one_replicas_and_renewed_by_it",
      f"{RUN}::test_only_the_replica_holding_the_lease_drains"]),
    ("V25 a prefix longer than 20 characters matches nothing", "OspreyFlow_Core/services/search_index/mapping.py",
     "PREFIX_MAX_CHARS = 50\n", "PREFIX_MAX_CHARS = 20\n",
     [f"{FEED}::test_a_long_typed_prefix_still_finds_the_name"]),
    ("V26 the render tells no service where OpenSearch is", "OspreyFlow_Core/harness/render.py",
     "                \"OPENSEARCH_HOST=opensearch\",\n", "",
     [f"{HARNESS}::test_a_deployment_with_opensearch_tells_the_conduit_and_worker_where_it_is"]),
    ("V27 a restore leaves the index empty", "OspreyFlow_Core/harness/restore.py",
     "    rebuild_search_index(compose_file)\n", "",
     [f"{HARNESS}::test_the_restore_rebuilds_after_every_store_is_back"]),
    ("V28 sigv4 asked for and nothing signed", "OspreyFlow_Core/services/search_index/client.py",
     "    if config.signing == \"sigv4\":\n", "    if False:\n",
     [f"{SIGV4}::test_a_sigv4_client_is_answered"]),
    ("V29 signed for another service", "OspreyFlow_Core/services/search_index/client.py",
     "    return AWSV4SignerAsyncAuth(credentials, region, \"es\")\n",
     "    return AWSV4SignerAsyncAuth(credentials, region, \"aoss\")\n",
     [f"{SIGV4}::test_a_sigv4_client_is_answered"]),
    ("V30 a seed's clean-up deletes past the index", "OspreyFlow_Core/scripts/seed_support.py",
     "    await record_for_search_index(client, node_type, node_prefix)\n", "",
     [f"{SEEDS}::test_a_clean_up_names_each_node_it_deletes_to_the_search_index_first"]),
    ("V31 a reset leaves the dropped graph's documents in the index", "OspreyFlow_Core/scripts/seed_support.py",
     "    await rebuild_search_index_if_configured(database, say=say)\n", "",
     [f"{SEEDS}::test_a_reset_rebuilds_the_search_index_where_there_is_one"]),
    ("V23 the host and port win over the URL", "OspreyFlow_Core/services/search_index/client.py",
     "        url = (env.get(\"OPENSEARCH_URL\") or \"\").strip()\n", "        url = \"\"\n",
     [f"{CLIENT}::test_the_url_wins_over_host_and_port"]),
    # --- decision 2: the request cap, at the bytes sent ------------------------------------------
    ("V32 a batch over the cap goes as one request", INDEXER,
     "        if size + n > MAX_BULK_BYTES:\n", "        if False:\n",
     [f"{BULK}::test_a_batch_over_the_cap_goes_as_several_requests_each_within_it",
      f"{BULK}::test_the_indexer_drains_a_batch_over_the_cap",
      f"{BULK}::test_the_rebuild_sends_within_the_cap"]),
    ("V33 one action over the cap alone is sent", INDEXER,
     "        if n > MAX_BULK_BYTES:\n", "        if False:\n",
     [f"{BULK}::test_one_action_alone_over_the_cap_is_set_aside_and_the_rest_sent",
      f"{REFUSED}::test_a_document_over_the_cap_is_set_aside_and_the_outbox_moves_on"]),
    ("V34 the cap counts characters", INDEXER,
     "        n = len(_encoded(lines))\n", "        n = len(lines)\n",
     [f"{BULK}::test_the_cap_counts_bytes_not_characters"]),
    ("V35 a 413 swallowed", INDEXER,
     "    answer = await client.bulk(body=request)\n",
     "    try:\n        answer = await client.bulk(body=request)\n    except Exception:\n        return [], []\n",
     [f"{BULK}::test_a_413_is_raised_and_the_outbox_keeps_the_batch",
      f"{BULK}::test_a_413_in_the_rebuild_is_raised_and_leaves_nothing_behind"]),
    ("V36 the cap at 20 MiB", INDEXER,
     "MAX_BULK_BYTES = 10 * 1024 * 1024\n", "MAX_BULK_BYTES = 20 * 1024 * 1024\n",
     [f"{BULK}::test_the_cap_is_ten_mib"]),
    ("V37 measured with strict encoding", INDEXER,
     '    return text.encode("utf-8", "surrogatepass")\n', '    return text.encode("utf-8")\n',
     [f"{BULK}::test_a_lone_surrogate_is_measured_as_the_client_sends_it"]),
    # --- decision 2: a document refused for good is set aside --------------------------------------
    ("V38 a refusal for the document's own content holds the outbox", INDEXER,
     "    return bool(kinds & _DOCUMENT_REFUSALS)\n", "    return False\n",
     [f"{REFUSED}::test_a_permanent_refusal_of_one_item_is_set_aside",
      f"{REFUSED}::test_a_refused_update_deletes_the_older_version_so_it_fails_closed"]),
    ("V39 a refusal set aside unrecorded", INDEXER,
     "    if not refused:\n        return\n    index = refused_index(alias)\n",
     "    return\n    index = refused_index(alias)\n",
     [f"{REFUSED}::test_a_document_over_the_cap_is_set_aside_and_the_outbox_moves_on"]),
    ("V40 a long name refused for its length", MAPPING,
     "            \"ignore_above\": KEYWORD_MAX_CHARS,\n", "",
     [f"{REFUSED}::test_a_keyword_over_the_term_limit_is_indexed_not_refused"]),
    # --- decision 4: a failed or crashed rebuild leaves nothing ------------------------------------
    ("V41 a failed rebuild leaves its index", REBUILD,
     "        await client.indices.delete(index=index, ignore_unavailable=True)\n        raise\n",
     "        raise\n",
     [f"{REFUSED}::test_a_rebuild_that_fails_leaves_nothing_and_keeps_the_refusal_record",
      f"{BULK}::test_a_413_in_the_rebuild_is_raised_and_leaves_nothing_behind"]),
    ("V42 a crashed rebuild's index kept", REBUILD,
     "            await client.indices.delete(index=left, ignore_unavailable=True)\n", "            pass\n",
     [f"{REFUSED}::test_a_rebuild_removes_the_index_a_crashed_rebuild_left"]),
    # --- decision 5: the drift check's refused and pending -----------------------------------------
    # V44 retired: the streaming drift check replaced the code it planted; V82 holds its sentence.
    ("V45 the drift check never says the outboxes are pending", REBUILD,
     "    pending = bool(await source.pending_index(1)) or bool(await texts.pending_text_index(1))\n",
     "    pending = False\n",
     [f"{REFUSED}::test_the_drift_check_says_the_outboxes_still_hold_changes"]),
    # --- decision 3: the text and its outbox row, one transaction ----------------------------------
    ("V46 the text's outbox row outside its transaction", REVIEW,
     "        async with self._pool.acquire() as conn, conn.transaction():\n            await conn.execute(\n"
     "                \"INSERT INTO document_texts",
     "        async with self._pool.acquire() as conn:\n            await conn.execute(\n"
     "                \"INSERT INTO document_texts",
     [f"{LAURIUM}::test_a_documents_text_and_its_outbox_row_are_one_transaction"]),
    ("V47 the stand-in takes a string for a TIMESTAMPTZ", STAND_IN,
     '    "TIMESTAMPTZ": (datetime,),\n', '    "TIMESTAMPTZ": (datetime, str),\n',
     [f"{LAURIUM}::test_the_pools_stand_in_refuses_what_postgres_refuses"]),
    ("V48 the stand-in goes on after a failed statement", STAND_IN,
     "            self._aborted = self._in_transaction\n", "            self._aborted = False\n",
     [f"{LAURIUM}::test_the_pools_stand_in_keeps_a_transaction_whole"]),
    # --- decision 3: strict ranking -----------------------------------------------------------------
    ("V49 a name's words scored by BM25", MAPPING,
     '                "words": {"type": "text", "analyzer": "words", **_BOOLEAN},\n',
     '                "words": {"type": "text", "analyzer": "words"},\n',
     [f"{RANK}::test_every_scored_field_is_boolean_so_no_word_rarity_ranks"]),
    ("V50 the text scored by BM25", MAPPING,
     '            "index_options": "offsets",\n            **_BOOLEAN,\n',
     '            "index_options": "offsets",\n',
     [f"{RANK}::test_every_scored_field_is_boolean_so_no_word_rarity_ranks"]),
    ("V51 a built-in stemmer on the words", MAPPING,
     '                "tokenizer": "standard",\n                "filter": ["lowercase", "asciifolding"],\n',
     '                "tokenizer": "standard",\n                "filter": ["lowercase", "asciifolding", "porter_stem"],\n',
     [f"{RANK}::test_no_phonetic_fuzzy_synonym_or_stemming_analysis_inside_opensearch"]),
    ("V52 a language analyser on the text", MAPPING,
     '            "type": "text",\n            "analyzer": "words",\n            "index_options": "offsets",\n',
     '            "type": "text",\n            "analyzer": "english",\n            "index_options": "offsets",\n',
     [f"{RANK}::test_no_phonetic_fuzzy_synonym_or_stemming_analysis_inside_opensearch"]),
    ("V53 no trigrams on a name", MAPPING,
     '                "tokenizer": "tri",\n', '                "tokenizer": "whole",\n',
     [f"{RANK}::test_names_match_by_trigrams_edge_ngrams_and_the_conduits_phonetic_key"]),
    # --- studio's two findings, live on stack f (13 November): each test red on the old shape -------
    # The analysis as it was at 0001fd3, put back whole: a keyword tokenizer and an ngram filter.
    ("V59 trigrams from a filter, all at one position (read as synonyms)", MAPPING,
     '        "filter": {\n            "edge_prefix": {"type": "edge_ngram", "min_gram": 2, "max_gram": PREFIX_MAX_CHARS},\n        },\n        "tokenizer": {\n            "whole": {"type": "keyword"},\n            # Trigrams from a tokenizer, each at its own position, so `minimum_should_match`\n            # counts them; an `ngram` filter puts them at one position, read as synonyms.\n            "tri": {"type": "ngram", "min_gram": 3, "max_gram": 3, "token_chars": []},\n        },\n        "analyzer": {\n            "prefix_index": {\n                "type": "custom",\n                "tokenizer": "whole",\n                "filter": ["lowercase", "asciifolding", "edge_prefix"],\n            },\n            "prefix_search": {\n                "type": "custom",\n                "tokenizer": "whole",\n                "filter": ["lowercase", "asciifolding"],\n            },\n            "tri": {\n                "type": "custom",\n                "tokenizer": "tri",\n                "filter": ["lowercase", "asciifolding"],\n            },\n',
     '        "filter": {\n            "edge_prefix": {"type": "edge_ngram", "min_gram": 2, "max_gram": PREFIX_MAX_CHARS},\n            "tri": {"type": "ngram", "min_gram": 3, "max_gram": 3},\n        },\n        "tokenizer": {"whole": {"type": "keyword"}},\n        "analyzer": {\n            "prefix_index": {\n                "type": "custom",\n                "tokenizer": "whole",\n                "filter": ["lowercase", "asciifolding", "edge_prefix"],\n            },\n            "prefix_search": {\n                "type": "custom",\n                "tokenizer": "whole",\n                "filter": ["lowercase", "asciifolding"],\n            },\n            "tri": {\n                "type": "custom",\n                "tokenizer": "whole",\n                "filter": ["lowercase", "asciifolding", "tri"],\n            },\n',
     [f"{RANK}::test_names_match_by_trigrams_edge_ngrams_and_the_conduits_phonetic_key"]),
    ("V60 a Document's text carries no date", DOCUMENT,
     '        "date": _date(_as_its_reader(node), date_of),\n', "",
     [f"{DOC}::test_a_documents_text_is_a_document_of_its_own_read_by_its_unit"]),
    # --- decision 7: the CA bundle ------------------------------------------------------------------
    ("V54 the named bundle not passed to the client", CLIENTPY,
     '        kwargs["ca_certs"] = config.ca_certs\n', "        pass\n",
     [f"{CA}::test_the_bundle_a_deployment_names_is_trusted"]),
    ("V55 the last bundle named wins", CLIENTPY,
     "                ca_certs = named\n                break\n", "                ca_certs = named\n",
     [f"{CA}::test_the_first_named_wins", f"{CA}::test_ssl_cert_file_wins_over_the_others"]),
    ("V56 SSL_CERT_FILE read last", CLIENTPY,
     'CA_BUNDLE_VARIABLES = ("SSL_CERT_FILE", "AWS_CA_BUNDLE", "REQUESTS_CA_BUNDLE")\n',
     'CA_BUNDLE_VARIABLES = ("AWS_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE")\n',
     [f"{CA}::test_ssl_cert_file_wins_over_the_others"]),
    ("V57 a named bundle that is not there accepted", CLIENTPY,
     "                if not os.path.isfile(named):\n", "                if False:\n",
     [f"{CA}::test_a_named_bundle_that_is_not_there_is_refused_in_words"]),
    # --- rule 4: the exemption by file, not by folder -----------------------------------------------
    ("V58 the feed's folder exempt whole", REACH_TEST,
     '            if rel in ALLOWED or "/node_modules/" in rel:\n',
     '            if rel in ALLOWED or rel.startswith("services/search_index/") or "/node_modules/" in rel:\n',
     [f"{REACH}::test_the_walk_names_a_planted_route_and_a_query_module_beside_the_feed"]),
    # --- the second lane review: the set-aside path fails closed -----------------------------------
    ("V61 every refusal set aside, whatever it is", INDEXER,
     "    return bool(kinds & _DOCUMENT_REFUSALS)\n", "    return True\n",
     [f"{REFUSED}::test_the_clusters_own_refusal_is_raised_whatever_its_status",
      f"{REFUSED}::test_an_alias_over_two_indexes_is_raised_not_set_aside"]),
    ("V62 a refused document's older version left in the index", INDEXER,
     "    if refused:\n        removal = ", "    if False:\n        removal = ",
     [f"{REFUSED}::test_a_refused_update_deletes_the_older_version_so_it_fails_closed"]),
    ("V63 the refusal's reason quotes the record", INDEXER,
     "    return f\"{status} {' / '.join(kinds)} in {'field ' if named == field else ''}{named}\"\n",
     "    return f\"{status} {error}\"\n",
     [f"{REFUSED}::test_a_refused_update_deletes_the_older_version_so_it_fails_closed",
      f"{REFUSED}::test_the_reason_keeps_the_type_and_field_never_the_value"]),
    ("V64 a write to the alias without require_alias", INDEXER,
     "require_alias=index is None", "require_alias=False",
     [f"{REFUSED}::test_a_write_to_a_missing_alias_makes_no_index_of_its_name"]),
    ("V65 a refusal record kept after its document is written", INDEXER,
     "        await clear_refused(self._client, self._alias, sorted(sent - set(refused)))\n", "",
     [f"{REFUSED}::test_a_record_is_removed_once_its_document_is_written"]),
    ("V66 an access field's long value left unindexed", MAPPING,
     '_KEYWORD = {"type": "keyword", **_BOOLEAN}\n',
     '_KEYWORD = {"type": "keyword", "ignore_above": KEYWORD_MAX_CHARS, **_BOOLEAN}\n',
     [f"{REFUSED}::test_a_refused_update_deletes_the_older_version_so_it_fails_closed"]),
    ("V67 two rebuilds at once", REBUILD,
     '        await client.indices.create(index=lock, body={"settings": {"number_of_shards": 1}})\n',
     "        pass\n",
     [f"{REFUSED}::test_one_rebuild_at_a_time"]),

    # --- the third lane review: no fail-open left -------------------------------------------------
    ("V68 a delete to an index that is gone counted done", INDEXER,
     'if status < 300 or (op == "delete" and status == 404 and error is None):',
     'if status < 300 or (op == "delete" and status == 404):',
     [f"{REFUSED}::test_a_delete_to_an_index_that_is_gone_is_raised_not_done"]),
    ("V69 written without checking the index's mapping", INDEXER,
     "                    await check_mapping(self._client, target)\n",
     "                    pass\n",
     [f"{REFUSED}::test_an_index_made_for_another_mapping_is_never_written"]),
    ("V70 a start accepts an index made for another mapping", INDEXER,
     "        await check_mapping(client, alias)\n        return\n", "        return\n",
     [f"{REFUSED}::test_an_index_made_for_another_mapping_is_never_written"]),
    ("V71 a lasting block leaves the older version searchable", INDEXER,
     "        if lasting:\n", "        if False:\n",
     [f"{REFUSED}::test_the_clusters_own_refusal_is_raised_whatever_its_status"]),
    ("V72 a field the mapping does not hold copied into the reason", INDEXER,
     "    named = field if field in _MAPPED_FIELDS else", "    named = field if True else",
     [f"{REFUSED}::test_the_reason_keeps_the_type_and_field_never_the_value",
      f"{REFUSED}::test_a_permanent_refusal_of_one_item_is_set_aside"]),
    ("V73 an index made without its mapping's fingerprint", MAPPING,
     '"_meta": {"mapping_fingerprint": MAPPING_FINGERPRINT}', '"_meta": {}',
     [f"{REFUSED}::test_a_document_over_the_cap_is_set_aside_and_the_outbox_moves_on"]),
    # --- the query side's exclusion read ------------------------------------------------------------
    ("V74 the exclusion set claimed whole when an outbox holds more", "OspreyFlow_Core/services/search_index/pending.py",
     "    complete = len(rows) <= limit and len(text_rows) <= limit\n", "    complete = len(ids) <= limit\n",
     [f"{PENDING}::test_more_rows_than_the_limit_is_never_claimed_whole"]),
    ("V75 the text outbox left out of the exclusion", "OspreyFlow_Core/services/search_index/pending.py",
     " | {d for _, d in text_rows[:limit]}", "",
     [f"{PENDING}::test_both_outboxes_ids_alone_and_whole"]),
    ("V76 under another mapping, the batch's deletes held back too", INDEXER,
     "                    await self._withdraw_all(target, node_ids)\n", "",
     [f"{REFUSED}::test_an_index_made_for_another_mapping_is_never_written"]),
    ("V77 the query side's retries ignored", CLIENTPY,
     '        "max_retries": max_retries,\n', "",
     [f"{CLIENT}::test_the_query_side_can_ask_for_no_retries"]),
    # --- decision 5: the drift check streams -------------------------------------------------------
    ("V78 the drift check holds the whole index in one page", REBUILD,
     '    nodes_stream = _Stream(client, alias, "node", "id", page)\n',
     '    nodes_stream = _Stream(client, alias, "node", "id", 10_000)\n',
     [f"{DRIFT}::test_its_memory_is_bounded_by_the_page_not_the_graph"]),
    ("V79 the graph's order not checked", REBUILD,
     "            if previous is not None and node_id <= previous:\n", "            if False:\n",
     [f"{DRIFT}::test_a_stream_out_of_order_is_raised"]),
    ("V80 the id lists kept whole", REBUILD,
     "        if len(kept) < DRIFT_IDS_KEPT:\n", "        if True:\n",
     [f"{DRIFT}::test_the_counts_are_exact_and_the_lists_say_they_are_cut"]),
    ("V81 the texts not compared", REBUILD,
     "                if node is not None and node_id in held\n", "                if False\n",
     [f"{DRIFT}::test_each_difference_is_found_while_streaming"]),
    ("V82 a refused document reported missing", REBUILD,
     "        if doc_id in reasons:\n", "        if False:\n",
     [f"{REFUSED}::test_a_document_over_the_cap_is_set_aside_and_the_outbox_moves_on"]),
    ("V83 the text stream in one page", REBUILD,
     '    texts_stream = _Stream(client, alias, "text", "node_id", page)\n',
     '    texts_stream = _Stream(client, alias, "text", "node_id", 10_000)\n',
     [f"{DRIFT}::test_its_memory_is_bounded_by_the_page_not_the_graph"]),
    ("V84 every missing id held to the end", REBUILD,
     "            if len(missing) >= page:\n", "            if False:\n",
     [f"{DRIFT}::test_its_memory_is_bounded_by_the_page_not_the_graph"]),
    ("V85 the index streams' order not checked", REBUILD,
     "            if before is not None and self.head[0] <= before[0]:\n", "            if False:\n",
     [f"{DRIFT}::test_an_index_stream_out_of_order_is_raised"]),
    ("V86 an order fault reported as drift", "OspreyFlow_Core/scripts/search_index_drift.py",
     "            return ORDER_FAULT\n", "            return 1\n",
     [f"{DRIFT}::test_the_command_says_an_order_fault_and_exits_3_never_1"]),
]


def _run(tests: list[str]) -> tuple[str, str]:
    """RED only where pytest ran the tests and some failed (exit 1, "failed" in its summary, no
    error); a collection error, an error in a set-up or nothing run is BROKEN, never read as red."""
    # A fresh bytecode cache for every run: Python matches a cached module by its source's mtime (to
    # the second) and size, so two plants of one file that are the same size, written in the same
    # second, would run the first plant's bytecode for the second (seen: V53 green on V52's).
    with tempfile.TemporaryDirectory() as cache:
        done = subprocess.run(
            [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider",
             "-p", "no:randomly", "-q", *tests],
            cwd=CORE, capture_output=True, text=True, check=False,
            env={**os.environ, "PYTHONPYCACHEPREFIX": cache, "PYTHONDONTWRITEBYTECODE": "1"},
        )  # fmt: skip
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    failed = [line for line in lines if line.startswith(("FAILED ", "ERROR ../"))]
    summary = lines[-1] if lines else done.stderr.strip()
    said = " | ".join([*failed, summary])
    if done.returncode == 0:
        return "GREEN", said
    if done.returncode == 1 and " failed" in summary and " error" not in summary:
        return "RED", said
    return "BROKEN", said


def main() -> int:
    offline = "--offline" in sys.argv[1:]
    every = [OUTBOX, FEED, DOC, CLIENT, REACH, RUN, HARNESS, SIGV4, SEEDS, BULK, REFUSED, CA, RANK,
             LAURIUM, PENDING, DRIFT]  # fmt: skip
    plants = PLANTS
    if offline:
        every = [t for t in every if t not in LIVE]
        plants = [p for p in PLANTS if not any(t.startswith(LIVE) for t in p[4])]
        print(f"offline: {len(plants)} of {len(PLANTS)} plants, the live files left out")
    state, line = _run(every)
    print(f"built: {state} - {line}")
    if state != "GREEN":
        return 1
    green_left = 0
    root = CORE.parent
    for name, rel, built, planted, tests in plants:
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
