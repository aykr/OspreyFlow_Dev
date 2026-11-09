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

**Live, first attempt: withdrawn, unmeasured** (`957ef5d.live-withdrawn.txt`). Platform lease on stack d (the
owner's test server, tunnelled to 127.0.0.1 here), 13:09:36–14:38:13 UTC at `957ef5d`. Over the tunnel each
database call took about 0.7 s, so the set got through only 25 tests in 1 h 29 m (`...F................F.F..`,
three failures whose names `-q` had not yet printed). At the owner's ruling, through the orchestrator, the pytest
was stopped and the run is recorded as **withdrawn and unmeasured**: what it measured is the tunnel's speed. Its
three failures are not read as the branch's or as not the branch's. The lease on d was kept and the stack left up
for the rerun on the server (`stack_lease.sh remote`).

**Live, second attempt: dropped** (its output not kept: the scratch copy was lost in the restart; the figures are from the session transcript). Through `stack_lease.sh remote` on stack d,
14:45–16:02 UTC: 367 passed, 0 failed, then the ssh session dropped (`Timeout, server … not responding`) and the
pytest with it. Not counted.

**Live, the gated run: 702 passed, 0 failed, 0 skipped** (`957ef5d.live.txt`). Platform lease on stack d, run on
ospreyflow-test beside its containers (`stack_lease.sh remote`, the pytest detached with `nohup setsid` so a dropped
ssh session could not end it), 16:08:55–17:34:57 UTC at `957ef5d`. It survived this Mac's restart at 17:09. The
server was shared with three other lanes' runs (load average about 4.5), and nothing else of this lane's ran. It
covered `test_route_rights.py`, the whole graph-port conformance suite, both case-gazetteer live files, the
gazetteer, identifier and recipe live files, both sources-withheld files, `test_tile_cache.py`, `test_prefetch.py`,
`test_statelessness.py`, `tests/geocoder/test_match_live.py` and `tests/services/api/working_set/`. The tunnel
run's three unnamed failures did not recur. **No case needs Java** (none skipped; planetiler is not run in tests).

**The red outstanding from round 2, item 5** (`957ef5d.live-plant.txt`), under the same lease. Plant:
`copy_places` reads the case's copies as unit `system`, not the dataset's own.
`test_a_restricted_case_load_on_a_copy_is_still_the_case_s_at_a_rebuild` went red at its assertion: the re-build
wrote the gazetteer's `Ashwell` over the case's `Ashwell (restricted)`. Restored, the whole copies file had 9 passed.
The stack was brought down and released at 17:40:03 UTC.


## P5 round 3 (the orchestrator's review sending P5 back, then the lane's own review of it)

**Hashes.** Files named `0980675.*` and `360c83c.*` are named for the head when they ran. Both commits were rebased afterwards and are not in the branch's history: `0980675` holds the round's first fixes and `360c83c` the read-path tests. Each file says what it ran.

- **Live**, platform lease on stack d through `stack_lease.sh remote`, detached. Released at 20:44 UTC.
  - `0980675.live-plants-r3.txt`, 18:29–20:25 UTC: each read path red with its fix removed; the conformance case of `PORT_CONTRACT.diff` green and red both ways; then the delta set with the diff applied, **372 passed**.
  - `360c83c.live-retract.txt`, 20:41 UTC: the retract test green, then red with its plant.
- **The image**, built on the test server (amd64) under the same lease, by `p5_image_check.sh`:
  - `360c83c.image-old-pin.txt`, 20:26 UTC, at the old pin. It was made by an earlier version of the script, without its sections 1b and 4b and without the jar's `chmod`, so planetiler's exit 1 there ("Unable to access jarfile") is the script's 0700 temporary directory, not Java.
  - `360c83c.image-repinned.txt`, 20:35 UTC, from the committed script at the new pin: 21.0.13+9; image 1,858,898,417 bytes, `/opt/java` 62 MB; planetiler v0.10.2 `--help` exit 0; trivy exit 0 over both the current image and Temurin 21.0.1; `java-runtime-check` green over the current image and red twice over the old one; the `legal/java.desktop` notices in full.
- **`make -k ci`** on this machine, Docker Desktop off, store ports pinned to the closed ports 59991–59994 and no `OSPREY_LANE`:
  - `ce36c3f.ci.txt`: red at this machine's Docker socket (the eight image scans, `opentofu-check`, `chart-check`), and at `product-tree-link-check` and `provenance-annotation-check` over the register's new paragraph (fixed at `eaae0fa`).
  - `1c1d2aa.ci.txt`: **green but this machine's Docker socket**. The harness axe run inside `core-check` passed, the Geospatial screen in dark and light included. The head after it, `b9d5aeb`, changes only `audit_section.py`'s *Datasets* list and `test_audit_kinds.py` (linted: ruff clean).
- **`make test`** on the server through `stack_lease.sh offline`:
  - `ce36c3f.test.txt`: 9732 passed, 7 failed, 2 errors. Of those, the lane's were `test_core_stands_alone.py` (2, the reviewer's defect 1), `test_audit_kinds.py` (main's new census) and the two citation checks above, all fixed since. The server's own: the GPU preflight case, `test_valkey_config.py` (the offline pins), `test_workspace_proxy.py`'s two errors. test-js: 2776 passed, 2 failed (the Matrix timing cases under load) and `App.test.tsx`'s hook timeout.
  - `b9d5aeb.test.txt`: **9762 passed, 2 failed, 11 skipped, none the branch's**: the server's GPU preflight case and `test_valkey_config.py` (the offline pins). test-js: workspace 2814 passed, 1 failed, `MatrixView.budget.test.tsx`'s first-frame timing under a full run's load, as at every earlier gate. `make test-js` stopped there, before the harness suite.
  - `b9d5aeb.test-js-rest.txt`, the same server: the harness suite, **47 passed**, the Geospatial screen's two among them; then the Matrix timing case alone, 1 passed.


## P5, the orchestrator's re-review, at `d9b0818` on main `15d0d24`

- **Live**, platform lease on stack e, through `stack_lease.sh remote`, 21:57–22:12 UTC at `dc11181` (code identical to `d9b0818`, which adds only the image script's `--pull` and the friction row):
  - `dc11181.live.txt`: part 1, the image build refused by Docker Hub's pull limit on `--pull` (429), then the live set, `test_route_rights.py` and both case-gazetteer files, **15 passed**. Then the port contract's case, green; red with the guard's copy clause dropped; red at the page's `more=True` with the case's earlier checks removed too.
  - `dc11181.image-ci-step.txt`: the image built as CI's job builds it (no `--pull`), 1,858,960,446 bytes. CI's step through the server's `uv`: exit 0 over it, exit 1 over Temurin 21.0.1. `--current`: exit 0 on the committed pin, exit 1 on the previous digest. planetiler `--help` exit 0. trivy exit 0 over both.
- **`make -k ci`**, `d9b0818.ci.txt`: green but this machine's Docker socket, as before.
- **`make test`** on the server, `d9b0818.test.txt`: 9774 passed, 2 failed, none the branch's (the GPU preflight case, `test_valkey_config.py`'s offline pin). Workspace test-js 2814 passed, 1 failed (`MatrixView.budget.test.tsx` under a full run's load); harness 47 passed, run on its own so the workspace's failure cannot skip it.
