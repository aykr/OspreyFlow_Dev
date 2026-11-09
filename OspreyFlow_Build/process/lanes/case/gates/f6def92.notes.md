# 701c027 and f6def92: every failure explained

On main `3be89a7`, with `ci-wiring-L3.4.patch`, `admin-delete-L3.4.patch`, `case-b-writer-gate-L3.4.patch` and
`registry-L3.4.patch` applied and `placesByRole.json` regenerated as `places-regeneration-L3.4.md` says (its one
expected change, `right:review_promotions`' three `answered_hidden` routes), none of it committed. `f6def92`
differs from `701c027` only in `keyboard/boards-harness.tsx` and the red record, which neither `make ci`'s Python
nor `make test` reads. Offline on closed ports (ArcadeDB 59991, Postgres 59992, Valkey 59993, ClickHouse 59994),
`OSPREY_LANE` unset. Docker Desktop is off on this machine (the owner's switch to test on the server).

**make -k ci (`701c027.ci.txt`): exit 2, every red Docker's.** The eight trivy image scans (`docker build`:
no daemon), so `core-check`; `opentofu-check` and `chart-check` (`docker run`). Every other target passed:
ruff, lint, typecheck, schemas, the confinement and authorised-query checks, test-file coverage (with the CI
patch), the doc citations, the install page's axe (34).

**make test (`701c027.test.txt`): 9573 passed, 24 failed, 30 errors, 16 skipped.** None is in a file of this branch:
- Docker's daemon absent: `tests/harness/test_deployment_schema.py`, `test_helm_chart.py` (1 failed, 16 errors),
  `test_proxy_health.py`, `test_proxy_tls_caddy.py`, `test_render_memory.py`, `test_tls_check.py`,
  `test_organisation_sign_in.py` (12 errors), `test_workspace_proxy.py` (2 errors).
- `tests/services/api/test_valkey_config.py`: reads `VALKEY_PORT`, the closed 59993 offline.
- `tests/test_phone_extraction_fixture.py`: needs an object store; none is up offline.
- `tests/test_layout.py`: `graphify-out` at the repository root, gitignored, this machine's own.
At `4b5777a` (Docker up) the same set less Docker's was the whole list.

**Keyboard** (`keyboard/boards.spec.ts`, `keyboard/promotions.spec.ts`): red at `701c027` (`701c027.kb-red.txt`,
2 failed: *an item is edited by keyboard* and the registry check counting it), a defect on main from L3.7 in
this lane's harness; fixed in `f6def92` (`L3.4_RED_RECORD.md`'s last section): 44 passed (`f6def92.kb.txt`).
**Axe** (`a11y/every-harness.spec.ts`, dark, light and GOV.UK): 740 passed (`701c027.axe.txt`), run through a
copy of `a11y/playwright.config.ts` with its port 5184 changed to 5284, rules' Vite holding 5184; the copy
removed after.

**Live**: the run over the tunnel withdrawn, unmeasured (`701c027.live-withdrawn.txt`); the rerun on the
server (`stack_lease.sh remote`), under lease case on stack e, with the same patches applied: `f6def92.live.txt`.
