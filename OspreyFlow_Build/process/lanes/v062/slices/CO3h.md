# Slice CO3h · CO3 · Three live tests read Valkey's port from the environment, not a fixed localhost:6379

- **Build id:** CO3 (reds on the runners; slice id CO3h).
- **Kind:** test-only, on the owner's standing (a). The owner's word of 28 November 2026, about 12:20 UTC: line-fix's `PLAN_LIVE_PAY.md` is approved, and this part merges early so that the server's pay run of the owed live tests can pass.
- **After:** nothing.
- **The port guard is never widened** (`OspreyFlow_Build/tests/port_guard.py`).

## Why

A fixed `localhost:6379` is stack a's Valkey port. The port guard refuses it from any other stack (b to g hold 6380 to 6385), from a pinned run and on the server. **Three tests hold it and fail on the server:**
- `OspreyFlow_Build/tests/resolve/test_trigger.py:142`, `Valkey(host="localhost", port=6379, db=0)`. The fix exists as `ebd2077` on `away/live-A`, which is not on main. **Take that change into your branch** (`git cherry-pick ebd2077`, or copy its one hunk), with its comment.
- `OspreyFlow_Build/tests/scenarios/test_phase6_extraction_and_resolution.py:127`, `Valkey(host="localhost", port=6379, db=0)`.
- `OspreyFlow_Build/tests/services/api/test_revoked_principal_precheck.py:76`, `ValkeyConfig(host="localhost", port=6379, db=0)`.

## What

1. **Each of the three reads `int(os.environ.get("VALKEY_PORT", "6379"))`**, as main's `test_ws_ticket.py` already does. Keep the same one-line comment as `ebd2077`'s. Change nothing else in each test.
2. **Red first (rule 15), at the real shape.** The acceptance test, `OspreyFlow_Build/tests/test_live_valkey_port_from_environment.py`, reads those three files as text. It fails while any of them builds a Valkey client or `ValkeyConfig` with a literal `port=6379`.
   - It must be red on main, naming all three sites, and green after the fix.
   - **Plant at the real shape:** put back `port=6379` in one of the three and show the test name it.
3. **The other fixed 6379s, listed, not changed.** A grep on main also finds `port=6379` in these files:
   - `tests/worker_isolation.py`;
   - `tests/test_worker_isolation.py`;
   - `tests/services/api/test_auth.py`;
   - `tests/services/api/test_websocket_auth.py`;
   - `tests/services/api/test_service_identity_and_rollup.py`.
   For each, say in your report whether it reaches a real Valkey (a live test) or only builds a configuration that never connects, with the file and line. Change none of them: a live one is a question for the conductor.
4. **The scan map:** say in your report which files the acceptance test reads. The conductor writes its scan-map row.
5. **Not in scope:** the port guard, `stack_lease.sh`, the Makefile, the CI workflow, product code.

Binding: process/CLAUDE.md rules 14 and 15; British English.

## Acceptance test

`OspreyFlow_Build/tests/test_live_valkey_port_from_environment.py`, red on main.

## Checks

- (The three live tests themselves run in the merge gate's live step, not here: with ports pinned to 9 they cannot reach a store. Run each by hand under a stack lease, `VALKEY_PORT` set to that stack's port, and give the result.)
- `test_port_guard.py`.
- Ruff.

**Before your final report, run by hand the cheap checks the conductor will run again before the merge.**
