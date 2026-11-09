# The fix round's gates (the independent review of L3.4 at d31f66f): every failure explained

Branch rebased onto main `9db2051`. Run with the hand-off patches applied, uncommitted: `ci-wiring`,
`admin-delete`, `case-b-writer-gate`, `registry`, `audit-census` and (from `e6ea09c`) `reports-viewer-census`
`-L3.4.patch`, and `placesByRole.json` regenerated as `places-regeneration-L3.4.md` says. Heavy local runs on
the orchestrator's go, one at a time.

**make -k test SKIP_JS=1 and make test-js** (`cd935e8.test.txt`), on the server by `stack_lease.sh offline case`
(closed ports, no lane, no stack): pytest 9748 passed, 4 failed, 11 skipped; vitest 341 files passed, 1 failed.
- `tests/services/api/test_reports_viewer_journey.py::test_every_route_naming_no_right_is_one_weighed_for_the_viewer`:
  **this branch's**, L3.4's seven removed-case routes naming no right, unweighed in rules-b's census. Fixed by
  `reports-viewer-census-L3.4.patch` (`e6ea09c`): red there, green with it (10 passed, offline).
- `tests/services/api/test_valkey_config.py`: main's own (the orchestrator's trial at main failed it too).
- `tests/harness/test_webapp_preflight.py::test_gpu_is_skipped_on_this_platform_never_shown_as_a_pass`: the
  server's platform has the GPU the case expects to be absent; not this branch's.
- `tests/test_layout.py::test_no_product_folder_is_left_at_the_root`: `.osprey-lease` and `.runs` at the root
  of the server's copy, the offline verb's own folders; not this branch's.
- vitest `src/matrix/MatrixView.budget.test.tsx`: opened in 8006 ms against 2500 on the shared server under
  other lanes' runs; the matrix is not this branch's.

**make -k ci** (`de06d22.ci.txt`, this Mac): exit 2, every red Docker's (off on this Mac by the owner's
ruling): the eight trivy image scans (so `core-check`), `opentofu-check`, `chart-check`; every other target
passed.

**Keyboard** (`keyboard/boards.spec.ts`, `keyboard/promotions.spec.ts`): 45 passed (`40bf58e.kb.txt`), the
boards' new Alerts panel case among them; the six actions' red records in `keyboard-plants-L3.4.txt`.
**Axe** (`a11y/every-harness.spec.ts`, dark, light and GOV.UK): 776 passed (`de06d22.axe.txt`).

**Live**, under lease case on stack e, held throughout (acquired before the first run, released after the
last), each run detached on the server by `stack_lease.sh remote`, on base `9db2051` with the patches applied:
- `e6ea09c.live-red.txt`: 30 passed, 2 failed, both this branch's own: `test_promotion_store.py`'s two
  clearance-filter cases shared `_three`, which the fix round had rewritten for the waiting cases. The helper
  restored and the waiting cases given `_three_waiting` (the next commit). Route rights 4, the sweep 2 (admin's
  stand-in case and the real-store one), promotion conformance 9 and the board store 6 passed there.
- `promotion-store-rerun.live.txt`: `test_promotion_store.py` again with the fix: 11 passed.
- `sweep-real-store-plant.live.txt`: the sweep's real-store case red with the lifespan's seam put back to
  `NoPromotionsYet()` (no alert raised), `app.py` restored after (rule 15).
