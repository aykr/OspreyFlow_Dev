# Platform P4 · gates at b599708 (tree 894d753f6fe3a81e2bf873b29d170bda982052cc), on main b64c4e2

After the orchestrator's ruling on the case's own searches (ADR-147 Amendment 1, decision 3b) and the
lane's review of it. Run 9 November 2026 offline (store ports pinned to the closed ports 59991–59994, no
`OSPREY_LANE`, no stack held, nothing else of this lane's running), from `OspreyFlow_Build`: `make -k ci`
(`b599708.ci.txt`), `make test` (`b599708.test.txt`), and `make test-js` from `OspreyFlow_Core`
(`b599708.test-js.txt`). Only this README, the red record and the report follow.

**`make -k ci`: green, exit 0**, the eight image scans included.

**`make test`: 9116 passed, 3 skipped, 4 failed and 2 errors, none the branch's**, the same six as at every
earlier P4 gate: `test_deployment_schema.py` (the committed `osprey.yaml`'s map default, as on main),
`test_valkey_config.py` (the offline pins), `test_layout.py` (this machine's `graphify-out/`),
`test_phone_extraction_fixture.py` (no object store offline), `test_workspace_proxy.py`'s two errors (its
image build).

**`make test-js`: workspace 2755 passed, 1 failed**: `MatrixView.budget.test.tsx`'s first-frame timing under a
full run's load (as at P3 and round 1); alone, 1 passed. Harness 45 passed (run after, appended).

**The registry ids are not on the branch** (item 1 of the independent review): `test:keyboard` (not in
`make ci`) needs `MAP_VIEW_ACTIONS.diff`; with it applied, `map-view.spec.ts` 7 passed and typecheck clean
(round 2's check, the keyboard spec unchanged since).

**Live** (`P4_RED_RECORD.md`, "Decision 3b"): platform lease on stack a, 04:13–04:35 UTC at `b599708`,
nothing else running: 688 passed, `test_route_rights.py` and the whole graph-port conformance suite included;
the guard's plants red at their own assertions, a guard matching nothing red at its positive control.
