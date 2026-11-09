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


## P5 round 2 at `8f94b0c` (tree `5022d786`), rebased onto main `b620185`

This round covers the orchestrator's review, its ruling (d), and the lane-reviewer's two passes on it.

**`make -k ci`**: green except the seven `trivy-image-*` scans, which all met Docker Hub's pull limit (14 × 429 Too Many
Requests). Every other target passed, `provenance-annotation-check` and `licence-check` among them. `licence-check`
names `git` as awaiting the owner.

**`make test`**: 9442 passed, 6 skipped. The 4 failures and 2 errors are the known six, none the branch's:
- `test_deployment_schema.py`
- `test_valkey_config.py`
- `test_layout.py`
- `test_phone_extraction_fixture.py`
- `test_workspace_proxy.py` ×2

**`make test-js`**: 2760 passed, 5 failed, none the branch's:
- **`IngestStudio.test.tsx` ×3**: fails on main's own tree; checked with main's `placesByRole.json`, 3 failed the same way. The branch
  touches nothing under `src/ingest/`.
- **`keyboard/registryCoverage.test.ts`**: main's `SOURCES_CONNECTORS_ACTIONS` has no keyboard spec yet. The branch touches
  nothing under `keyboard/`.
- **`MatrixView.budget.test.tsx`**: the first-frame timing case. It passed alone at every earlier gate. Today it also failed
  alone, twice: beside the IngestStudio file at load average 25, and by itself at 10:17 UTC at load average 42. The
  branch touches nothing under `src/matrix/`. It is a timing budget, so a run at a quieter time is the check.

**Live:** waiting for a stack in the orchestrator's queue (case, then rules, then rules-b, then platform). Not run at this
head yet.


## P5 at `957ef5d` (tree `23e4abc1`), rebased onto main `3be89a7`

The resumed session rebased round 2 (the code unchanged; the one conflict was `06_DECISIONS.md`, where case-b's
ADR-143 Amendment 6 and this lane's ADR-147 Amendment 2 both end the file, and both are kept). Run 9 November
2026, 12:31–12:53 UTC, offline (the closed ports 59991–59994, no `OSPREY_LANE`, no stack held). **Docker Desktop
is off on this machine** (the stacks are on the owner's test server), so everything that runs `docker` here
fails at its connection, `failed to connect to the docker API at unix:///…/docker.sock`, and proves nothing either way.

**`make -k ci` (`957ef5d.ci.txt`)**: every target green except the ones that run `docker`: the eight
`trivy-image-*` scans, `opentofu-check` and `chart-check`. `licence-check` passes and names `git` as awaiting
the owner. **The api image, with its Java runtime, has not been scanned at any P5 gate** (at round 2 the scans
met Docker Hub's 429; here there is no daemon). It is open in the report.

**`make test` (`957ef5d.test.txt`)**: 9498 passed, 16 skipped, 24 failed, 30 errors. None is the branch's:
- **The known six**, as at every earlier gate: `test_deployment_schema.py`, `test_valkey_config.py`
  (the offline pins), `test_layout.py` (this machine's `graphify-out/`), `test_phone_extraction_fixture.py`
  (no object store offline) and `test_workspace_proxy.py` ×2.
- **The rest all fail at the Docker connection.** Each failure's traceback names the socket:
  `test_helm_chart.py` (16 errors, 1 failure), `test_organisation_sign_in.py` (12 errors),
  `test_proxy_health.py` (2), `test_proxy_tls_caddy.py` (9), `test_render_memory.py` (3) and
  `test_tls_check.py` (5). These were checked mechanically: of the report's failure sections, the only ones
  that do not mention `docker` are the four known failures above.

**`make test-js` (`957ef5d.test-js.txt`)**: workspace 2765 passed and 1 failed, `MatrixView.budget.test.tsx`'s
first-frame timing under a full run's load. Alone at load average 11, it passed. The harness had 45 passed
(run after, appended).
