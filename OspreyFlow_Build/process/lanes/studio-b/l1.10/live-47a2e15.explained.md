# L1.10's full live set at 47a2e15 (main f2ef3b3), stack d, `--continue-on-collection-errors`

`live-47a2e15.txt`: **35 failed, 3,292 passed, 77 skipped, 1 error**, in 4,009 s. Stack d was released afterwards (`d: free`).
The first run (`live-47a2e15-stopped-at-collection.txt`) collected nothing, because of the error below.

**The error is main's.** `tests/services/api/test_schedule_notice.py` cannot import `alert_to_view` (L2.10 removed it; rules' L2.11 fixes it).

**All 35 failures are the run's, not this branch's** (the orchestrator's "about 36"):

| Count | Group | Cause |
| ---: | --- | --- |
| 12 | The model, recognise and golden suites: model_port 3, vision 1, recognise_port 4, golden 1. Model-backed scenarios: phase 6 extraction, the witness statement, phase 8. | No model or recognise service on the run (`httpx.ConnectError`, `RecogniserUnavailableError`). Phase 8 fails the same way (`assert 0 == 4` at the seed) in main's baseline `l1.7a/baseline-main-15d0d24.txt` and in nine other lanes' records. |
| 9 | Three files on stack a's default ports: `tests/services/api/test_worker.py` 3, `tests/services/api/test_ws_ticket.py` 5, `tests/resolve/test_trigger.py` 1. | `LeaseNotHeld`: 127.0.0.1:6379 is stack a's valkey. |
| 10 | `tests/harness/test_apply_env.py` | Preflight refuses because port 2480 (proxy) is in use on the server. Render completed, with 7 artefacts. The demo-analyst roles case judges only `harness/realm.py` and `schemas/rights.py`, which this branch does not touch. |
| 4 | `tests/test_media_blob.py` | No Azure blob settings on the run (`KeyError: 'AZURE_STORAGE_ACCOUNT'`). |

**None of the failures is in a ceiling path.**
- No failure or log line cites `AboveTheDeploymentCeiling` or the ceiling's words.
- The branch's Core changes (11 files) include no realm, rights, media, worker, ticket, trigger or seed-route file.
