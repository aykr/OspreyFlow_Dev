# case-b · P12 part 2 · round 3 after the orchestrator's round 2, 11 November 2026

**Exit.** A credential step, listed for the owner. Record: `P12p2_RED_RECORD.md` ("Round 2"); as built: ADR-135 Amendment 9.
- **Laurium reads a real model, met** on the product's own (`qwen2.5:7b-instruct` 3 of 3, 1.84–3.65 s, stack b) — the gateway directly, Laurium's code in-process, a one-string schema; **not** the rendered route, its image, the Conduit or the review queue's schema (carried: a rerun with `build_schema`). **The client's engine: 20 Nov.**
- **Laurium's image: built, scanned clean, started once** (round 2's item 2): trivy first found 3 HIGH in pip's own vendored setuptools and urllib3 (the base image's); pip now uninstalls itself last; 0 HIGH/CRITICAL; up as 10001:10001, `/healthz` 200 with no network. In `make ci` through `P12p2_core_makefile.diff`.
- **Only the review queue's route reaches Laurium**, read by a scan of every module (`test_laurium_call_sites.py`, a plant in `questions.py` red). **No screen calls that route today** (Amendment 9 point 2): the owner's preset question goes back with it.
- **Egress to the gateway alone: at merge after P7b** with Laurium's row; the strict xfails take only their stated `AssertionError` (an unreadable manifest is its own exception, FAILED), and the merge step is in the record.

**Gates at 69bb4f8** (main e996106; all six diffs applied; `stack_lease.sh offline case-b`; `gates/69bb4f8.*`): **make -k test: 1 failed / 11,953 passed** — the GPU preflight, the server's. **make -k ci: green** (Laurium's image built and scanned in `core-check`). **test-js**: MatrixView's budget alone (4,362 ms at load; carried, as ruled). **axe** 40 passed. **Laurium's environment**: 26 passed, 14 of 14 plants red, the xfail check 4 of 4. **`--runxfail`**: the 8 strict xfails each fail with their stated `AssertionError`, none with `UnreadableShape`.

**Carried**: the duplication; MatrixView's budget; the rerun with the review queue's schema; the Glass's profile guess; the readiness latch under rotation. **Left**: the xfails until P7b; the client's engine; the owner's preset question; the guide's renumbering to 1.83 after P7b lands.

**Commits**: 54ca87b…69bb4f8 and this record, on `lane/case-b-p12p2`; never pushed. **Diffs at merge**: `P12p2_platform.diff`, `P12p2_glass_models.diff`, `P12p2_docs_admin_guide.diff` (1.82 now, 1.83 after P7b; its PDF reprinted), `P12p2_core_makefile.diff`, `P12p2_CI.diff` (the owner's); the egress rows with P7b. **Shared hunks**: `services/api/app.py`, `services/api/review.py`.

**Requests**: Amendment 9's reservation title, and mark it written. **Questions for the owner**: the preset, with no screen reaching Laurium yet. **Nothing of mine is running**; no lease held.
