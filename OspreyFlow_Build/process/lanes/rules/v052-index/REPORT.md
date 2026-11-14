# rules · v052-index (ROUTE_052 step 3c) · report

**Branch:** `lane/rules-v052-index`. Gated at `a879b3c`, on main `4dc9761`. Not pushed: the orchestrator merges.

## Gates at a879b3c (raw output in `gates/`)

| Gate | Result | File |
| --- | --- | --- |
| `make test` (offline, server) | 10 failed, 13,383 passed, 36 skipped; JS all passed. Nine of the ten are main's: the same nine fail on a clean main 4dc9761 (`main-4dc9761.nine.txt`; backups chart/rows ×7 to platform, the 6a8 guide test to docs, `test_write_store_marks` to platform-b). The tenth is `test_test_file_coverage_check`: `test_feed_live.py` is run by no live job until the owner applies `v052-index_ci_yml.diff` | `a879b3c.test.txt` |
| `make -k ci` (offline, server) | exit 2: `test-file-coverage-check` (the same `ci.yml` cause), and `harness-a11y` (3 of 68 timed out waiting for the page, under load); `harness-a11y` re-run alone: 34 passed | `a879b3c.ci.txt`, `a879b3c.harness-a11y-rerun.txt` |
| Live, stack c under the lease | graph conformance, `test_feed_live.py`, `test_route_rights.py`: 403 passed | `a879b3c.live-stack-c.txt` |
| Plants V1–V77, stack c | built GREEN (151), 76 RED (V43 retired), restored GREEN | `PLANTS_RECORD.txt` (offline subset: `PLANTS_RECORD.offline.txt`) |

## What is built, and the test that holds it

| Piece | Proving test |
| --- | --- |
| The outbox in each adapter write's own transaction (load, merge, new version, promotion and revert, revert, withdrawal and restore, deleted case layer) | `tests/conformance/graph_port/test_index_outbox.py`; V1–V14 |
| The indexer, one document per node, the text's own outbox, the rebuild and the drift check | `tests/services/search_index/test_feed_live.py`, `test_document.py`; V15–V21 |
| Rule 4: only the feed's modules name its reads | `test_index_feed_reach.py`; V22, V58 |
| The client (URL first, SigV4, CA bundle, retries) | `test_client.py`, `test_client_sigv4.py`, `test_client_ca.py`; V23, V28–V29, V54–V57, V77 |
| Each `_bulk` request ≤ 10 MiB by bytes sent; a 413 raised | `test_bulk_cap.py`; V32–V37 |
| A document refused for its own content set aside, fail-closed (older version deleted, reason without the value, record cleared on a later write); every cluster-state refusal raised; deletes never set aside, and done only for `not_found` | `test_refused.py`; V38–V39, V61–V65, V68, V71–V72 |
| Access fields without `ignore_above`; names and identifiers with it | `test_refused.py`; V40, V66 |
| A failed, crashed or concurrent rebuild leaves nothing behind | `test_refused.py`, `test_bulk_cap.py`; V41–V42, V67 |
| The drift check's refused and pending | `test_refused.py`; V44–V45 |
| An index written only by the code its mapping was made for; under a mismatch, the batch's deletes still sent | `test_refused.py`; V69–V70, V73, V76 |
| The text and its outbox row in one transaction; the asyncpg stand-in's refusals | `tests/adapters/extract_laurium/test_findings_inferred.py`; V46–V48 |
| Strict ranking (allow-list), trigrams from a tokenizer, the text's date (studio's two live findings) | `test_mapping_strict_ranking.py`, `test_document.py`; V49–V53, V59–V60 |
| The query side's exclusion read, never claimed whole past its limit | `test_pending.py`; V74–V75 |
| Render, restore's rebuild step, seeds' clean-up and reset, the dev stack's OpenSearch | `tests/harness/test_search_index_render_and_restore.py`, `tests/test_seed_support.py`; V26–V27, V30–V31 |

## Decisions taken (Prompt L: the recommended option, the strict one for access)

1. A document OpenSearch refuses for its own content is set aside (`<alias>-refused`, logged), never left to hold the outbox; it is decided by the error's type, never by its status; the older version is deleted in the same pass (fail closed).
2. A write refused by a lasting block (cluster block, security) deletes its older version where deletes are still taken; a 429 is only retried.
3. The index's mapping fingerprint is held in `_meta`; an index made for another mapping is never written, its deletes are still sent, and a rebuild is asked for. The upgrade's rebuild is a CARRIES row (platform and admin).
4. The query side's exclusion read is a helper over the two existing reads, not a new port method: outbox rows repeat, so `complete` false past the limit is the only safe answer.
5. A rebuild lock left by a killed rebuild is deleted by hand, as the refusal says.

## Cross-lane files changed on this branch (the orchestrator's ruling: commits, checked at merge)

| File | Owning lane | Why |
| --- | --- | --- |
| `OspreyFlow_Core/harness/restore.py` | platform-b | the restore ends by rebuilding the index (decision 4) |
| `OspreyFlow_Core/harness/render.py` | platform | tells the Conduit and the worker where OpenSearch is, and the index alias |
| `OspreyFlow_Core/harness/service_inventory.py` | platform | `services/search_index` listed |
| `OspreyFlow_Core/services/api/worker_main.py` | case / api | the indexer runs in the worker under a Valkey lease |
| `OspreyFlow_Core/services/api/review.py` | case | the text's outbox row in `store_document_text`'s transaction |
| `OspreyFlow_Build/tests/adapters/extract_laurium/review_queue.py` | case-b | the asyncpg stand-in takes transactions and refuses what asyncpg refuses |
| `OspreyFlow_Core/deploy/compose/dev.yaml` | platform | the dev stack's OpenSearch |

## Owed elsewhere

- The owner: `v052-index_ci_yml.diff` (an OpenSearch service in the conformance job, `test_feed_live.py` run there).
- CARRIES rows added: a streaming drift check before B's load; a restore searched end to end (platform-b); the upgrade's rebuild on a mapping change (platform, admin).
