# Step 3h: clusters per reader (ADR-124 Amendment 19)

## Red first

`merged_clusters_reds.py`, 11 of 11 red at 01181bd (`merged-clusters-reds.01181bd.log`). Among them:
- **The old shared path, planted back whole.** It sends a reader not cleared for H `{p-v: p-h, p-x: p-h}`: the hidden
  member's id, and V and X joined through it.
- **The stream-first defect.** Its plant is the eleventh.

## On stack b

The lease was taken 11:37Z, under the orchestrator's grant, and the stack was released afterwards.
- **The working-set tests against ArcadeDB: 321 of 321** (`3h-live-pytest.log`, then `3h-live-pytest2.log` after the
  explain access test was held to the amendment).
- **The API replay of the explain flow** (`3h-diag2.log`): seed, seed, expand by SAME_AS, threshold to Strict. Each
  answer carries the right clusters.
- **fixture-corp live, run 1** (`3h-live-corp2.log`, load 6.8). The stream-first defect, found here:
  - *What happened:* the case's stream drew the Same as expansion's add before its answer landed. The canvas said
    "Nothing new" for four people added, and that notice held its keys, so *Explain cluster*'s menu never opened.
  - *The fix:* f9bc8d2 judges *nothing new* against what the canvas held when the expansion was asked for. Its red case
    is `keyboard/canvas-expand-stream-first.spec.ts`.
  - *Scope:* this is outside Amendment 19's own scope, which is the clusters, but it is named in its tests because the
    amendment's live check found it.
- **fixture-corp live, run 2** (`3h-live-corp3.log`): **unmeasured.** The host's load was 56, the pages drew blank, and
  the status bar and search box never appeared. It is neither a pass nor a fail.

## The queue's turn (rebased onto origin/main f10e47a)

1. **First server run, at 74e6ce9** (`server.74e6ce9.log`): `make test` and `make -k ci` both exited 2.
   - Lint: 26 new lines of mine ran past the 100-column limit.
   - `make test`: 5 of 14,298 failed.
     - `test_app` (2): its key sets pinned an answer's fields, and `clusters` is the reader's own clusters, not a count.
     - Two store-only tests had a service with no graph.
     - `test_core_stands_alone` flags `scripts/client_size_plan.py`. That is main's (ce5afbd, rules), not this branch's.
   - Fixed at 122c923.
2. **Second server run, at 122c923** (`server.122c923.log`):
   - **`make -k ci`: exit 0.**
   - `make test`: exit 2. The pytest suite's only failure is main's `test_core_stands_alone`, as above.
   - test-js: one failure, `src/ingest/checks/ChecksScreen.test.tsx`'s "says a refusal in the server's words". It is a
     1-second `findByRole` timeout, during studio's live reseed on stack f (the orchestrator's note), in a file this
     branch does not touch. Rerun alone on the server, run 20261114T134504Z, 6 of 6 passed, the case in 27 ms. So it is
     load, not a result.
3. **fixture-corp live, at 122c923, on stack b** (`live-fixture-corp.122c923.log`):
   - **5 of 5, explain on a merged cluster among them.**
   - The lease was taken at 13:45Z and released afterwards.
   - The host's load was 2.88 at the run, with nothing else full on the host.
   - My queue line was deleted afterwards.
