# Platform P4 · gates at b38c6de (tree 047d0650e6b2d22e22f5f0ddd272806dcf5f60d1), on main 75f277d

After the orchestrator's independent review and the lane's own review of that round. Run 9 November 2026
offline (store ports pinned to the closed ports 59991–59994, no `OSPREY_LANE`, no stack held, and nothing
else of this lane's running), from `OspreyFlow_Build`: `make -k ci` (`b38c6de.ci.txt`), `make test`
(`b38c6de.test.txt`), and `make test-js` from `OspreyFlow_Core` (`b38c6de.test-js.txt`), since `make test`
stops at pytest's failures before its own `test-js` step. Only this README, the red record and the report
follow.

**`make -k ci`: green, exit 0**, the eight image scans included (Docker Hub answered this time).

**`make test`: 9113 passed, 3 skipped, 4 failed and 2 errors, none the branch's**, the same six as at P3's and
round 1's gates: `test_deployment_schema.py::test_the_committed_osprey_yaml_still_validates` (the committed
`osprey.yaml`'s map default, as on main), `test_valkey_config.py` (the offline pins), `test_layout.py` (this
machine's `graphify-out/`), `test_phone_extraction_fixture.py` (no object store offline), and
`test_workspace_proxy.py`'s two errors (its image build).

**`make test-js`: green**: workspace 2756 passed, harness 45 passed.

**The registry ids are not on the branch** (the orchestrator's item 1): `keyboard/map-view.spec.ts` imports
`MAP_VIEW_ACTIONS`, which `MAP_VIEW_ACTIONS.diff` adds at the merge. `make ci`'s typecheck does not cover the
workspace's keyboard specs, so it is green; `test:keyboard` (not in `make ci`) needs the diff. With it
applied in the worktree and reverted: `map-view.spec.ts` 7 passed, `registryCoverage` and the map's units
113 passed, `npm run typecheck` clean.

**Live** (`P4_RED_RECORD.md`, "The leased live run, round 2"): platform lease on stack a, 03:31–03:38 UTC,
336 passed at `aad6e9b` and at `b38c6de`, `test_statelessness.py` included with its wait unchanged; three
live plants red at their own assertions. **Axe**: `map-view-harness.html` in four states × three themes, 16
passed, each state shown drawn first.
