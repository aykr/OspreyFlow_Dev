# case-b · P12 part 2 · round 2 after the orchestrator's round 1, 11 November 2026

**Exit.** A credential step, listed for the owner. Record: `P12p2_RED_RECORD.md` ("Round 1"); as built: ADR-135 Amendment 9.
- **Laurium reads a real model, met** on the product's own (`qwen2.5:7b-instruct` 3 of 3, stack b) through Laurium's adapter over the real service, not the Conduit; the 0.5B 0 of 3 as the control. **The client's engine: 20 Nov, P12's last open item.**
- **Only the review queue's route reaches Laurium** (round 1's blocker fixed): `run_extraction(laurium_may_read=…)`, passed by that route alone; email extraction and a document's content reach Deep read, tested at their call sites (`test_laurium_call_sites.py`, plants red).
- **Laurium's key scoped, its wiring tested offline, met**: no Secret in its pod; key at start never stopping the Conduit; `laurium_in_the_conduit` with `ready` false until the key exists (`test_laurium_start.py`, plants red).
- **cp-policy-check with Laurium on three shapes, met** (`test_laurium_cp_policy.py`). **Egress to the gateway alone: at merge**, after P7b with Laurium's row (the ruling); the network-policy and token xfails come off there, each failing now for its stated reason (`--runxfail`).

**Gates** (rebased on f78b307; the three diffs applied; `stack_lease.sh offline case-b`): **make -k test** at 6052a5b: 3 failed / 11,855 passed: the GPU preflight (the server's); **`test_docs_pdf`, real**, fixed by moving the guide's row into `P12p2_docs_admin_guide.diff` (1.79, PDF at merge); a heartbeat test, passed alone. **make -k ci** at 6052a5b: one failure, `test_rendered_terraform[production+opensearch]`, OpenTofu's registry unreachable, passed alone; all else green. **test-js** at 1977ff4: MatrixView's budget alone failed, and failed alone too at load 24 (carried, as ruled; no branch file under `apps/workspace/src/matrix`). **axe** 40 passed. **Laurium's environment**: 26 passed, 14 of 14 plants red, the xfail's 4 of 4.

**Carried**: the duplication; MatrixView's budget unleased. **Left**: the xfails until P7b; the client's engine; the owner's preset question.

**Commits**: 54ca87b…1977ff4 and this record, on `lane/case-b-p12p2`; never pushed. **Diffs at merge**: `P12p2_platform.diff`, `P12p2_glass_models.diff`, `P12p2_docs_admin_guide.diff` (its PDF), `P12p2_CI.diff` (the owner's); the egress rows with P7b. **Shared hunks**: `services/api/app.py`, `services/api/review.py`.

**Requests**: Amendment 9's reservation title, and mark it written. **Questions for the owner**: the preset (MORNING). **Nothing of mine is running**; no lease held.
