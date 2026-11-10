# admin · T1's batched schema red record (10 November 2026)

Each check was planted out at its real call site, its test run red, and the file put back and green. These plants were
run by hand, one at a time. Offline: closed ports, no lane. The file is `OspreyFlow_Core/packages/adapters/graph_arcadedb/schema.py`
throughout. The tests are `OspreyFlow_Build/tests/adapters/graph_arcadedb/test_schema_batch.py` and `test_schema_backfill.py` (20 cases at the last row's head; each row's count is as it was run).

| Plant | Red |
| --- | --- |
| The same statements sent singly, each its own request (the orchestrator's plant) | 5 failed: the golden one-script case, the parse error in the middle and last, the run-time refusal, the re-send on a failure to connect |
| A timed-out script re-sent (every `TransportError` retried) | 1 failed: `…timed_out_is_not_sent_again_beside_itself` |
| No timeout of the script's own | 1 failed: the golden case (`timeout == 600`) |
| A permanent refusal retried (the denylist check removed) | 4 failed: the three parse errors and the run-time refusal (each sent 6 times) |
| No re-send on a failure to connect | 1 failed: `…failure_to_connect_re_sends_the_whole_script` |
| `CommandSQLParsingException` off the denylist (added after the live proof named it) | 1 failed: `…does_not_parse_is_never_retried_even_as_a_5xx` |
| **After my reviewer's second pass**, 20 cases: | |
| `**extra` dropped in `client.py`, so the script's timeout never reaches the request | 1 failed: `…real_client_sends_the_script_with_a_600_s_read_and_a_30_s_connect` (a real `ArcadeDBClient` over `httpx.MockTransport`) |
| A bare 600 s for every timeout (connect included) | 1 failed: the same |
| `ConnectTimeout` not re-sent | 1 failed: `…connect_timeout_is_re_sent_as_a_failure_to_connect` |
| No 5xx ever retried | 2 failed: `…transient_5xx_re_sends_the_whole_script`, `…six_transient_5xx_in_a_row_raise_typed` |
| `cause` required, so the error cannot be unpickled | 1 failed: `…error_survives_pickling` |

**The design changed under review.** My first version undid a refused script by dropping what it had added. My
lane-reviewer found that the cluster profile starts several Conduits and workers at once. One of them, refused,
would drop with `UNSAFE` a type another had just created and written to. The orchestrator accepted the change:
there is no restore, and the failure semantics are main's own. The restore's cases and plants went with it.

**The golden list.** `GOLDEN` in `test_schema_batch.py` is the 48 statements main 17c202d's `apply_schema` sent one at
a time for the test ontology. For the full default ontology, main's own code, recorded against a stand-in, sent the
same 585 statements in the same order with the same 8 copy-ups; that was checked once, not committed.

**Live** (`OspreyFlow_Build/tests/conformance/graph_port/test_schema_batch_live.py`, run by the orchestrator under its own lease):
- At 62072cf on stack c, the dump comparison was red, with only the index `name` differing. At ebc74d8 on stack c, all
  39 differences were a bucket index name's allocation number (`mx_ALERTED_ON_0_1280514856246682` against
  `…_1280508458223250`), none in any other field. Only that number is now relaxed (`_ALLOCATION`), and the
  type and bucket part is kept.
- The comparison's own red, `test_the_dump_comparison_names_a_missing_index`, passed at ebc74d8: one
  `CREATE INDEX … BY ITEM` left out of the batch is named as missing.
- At 366afad: the whole of `tests/conformance/graph_port` and `test_route_rights.py`, 377 passed, 0 failed, under
  "stack c, the lease orchestrator took at 2026-11-10T11:13:03Z; wall 471 s, set-up 8 s" (`gates/366afad.live.txt`).
  The timings it printed, for 585 statements:
  - a fresh database: 15.8 s one at a time, 0.2 s batched;
  - the schema applied again (the Conduit's start-up): 0.8 s one at a time, 0.1 s batched;
  - `arcadedb_adapter`'s open (create and apply): 0.3 s.
- The real classes. A parse error is refused as `com.arcadedb.exception.CommandSQLParsingException`, which was not
  then on the denylist. A run-time refusal is refused as `com.arcadedb.exception.SchemaException`. Each script was
  sent once (`client.scripts == 1`). 8697fc0 added the parse class to the denylist after this run; the next live run
  asserts both classes and prints their status codes.
- At e789147, the whole of `graph_port` and `test_route_rights.py` gave 1 failed and 377 passed, under "stack d, the lease
  orchestrator took at 2026-11-10T11:32:37Z; wall 519 s, set-up 12 s". The timings:
  - a fresh database: 16.3 s one at a time, 0.2 s batched;
  - applied again: 0.7 s one at a time, 0.1 s batched;
  - the adapter's open: 0.3 s.

  A parse error is refused as `CommandSQLParsingException`, **status 400**. The failure was the new populated-type case.
- The probe at a62f7f4 (stack c, the orchestrator's lease) ran that case both ways, one statement at a time and batched.
  Both created the index (`mx_Person[t1_probe]` and its bucket index) and both failed identically. **A test fault**:
  ArcadeDB gives an index's `properties` nested, `[['t1_probe']]`, not `['t1_probe']`. The check is now
  `_indexes_on`. It has its own red, `test_the_index_check_finds_nothing_when_the_index_is_left_out`, which leaves the
  `t1_probe` CREATE INDEX out of the batch and also checks it still finds the `id` index. The populated case's time over
  500 nodes was 1.2 s one at a time and 0.1 s batched.
- **At f6fe015, the step's last live run:** `graph_port` and `test_route_rights.py` gave 380 passed and 0 failed, under
  "stack c, the lease orchestrator took at 2026-11-10T11:44:53Z; wall 514 s, set-up 15 s" (`gates/f6fe015.live.txt`).
  The timings:
  - a fresh database: 16.1 s one at a time, 0.2 s batched;
  - applied again: 0.8 s one at a time, 0.1 s batched;
  - the adapter's open: 0.3 s.

  The earlier runs' logs are `gates/ebc74d8.live.txt`, `gates/e789147.live.txt` and `gates/a62f7f4.probe.txt`.
- **`make -k ci` at e789147** (`gates/e789147.ci.txt`): green apart from Docker's checks and test-file-coverage-check.
  The latter is fixed in 15caebd (`gates/15caebd.coverage.txt`). `make test` is the orchestrator's run, at e789147.
