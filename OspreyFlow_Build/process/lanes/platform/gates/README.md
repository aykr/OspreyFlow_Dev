# Platform P3 · gates at 95b9312 (tree 0fd7f16ed84ff26d11b422bb78cea0add5c69a0a), on main 47b0bc4

Run 8 November 2026 offline (store ports pinned to unused ports, no stack held), from `OspreyFlow_Build`:
`make -k ci` (`95b9312.ci.txt`), `make test` (`95b9312.test.txt`), `make test-js` (`95b9312.test-js.txt`).
The branch's own fixes after them (the guide's version row and its PDF, from `test_docs_pdf.py`) are the
commit after; nothing else changed.

**`make -k ci`: green but for the environment.** The seven `trivy-image-*` scans could not build: Docker Hub
refused the base images' pulls (`429 Too Many Requests`, 15 times in the log). `harness-a11y` lost its port
(5193, another lane's server); run again alone once free: 34 passed (`95b9312.harness-a11y.txt`). Every other
gate passed, `licence-check` included.

**`make test`: 8820 passed, 5 failed:**
- `test_docs_pdf.py::test_the_guides_and_their_pdfs_are_in_step`: **the branch's** (the guide's `ospreyflow map`
  rows); fixed in the next commit (version 1.57, its PDF rebuilt; 18 passed).
- Not the branch's, as at P2's gates: `test_deployment_schema.py::test_the_committed_osprey_yaml_still_validates`
  (the committed `osprey.yaml`'s map default), `test_valkey_config.py` (the offline pins), `test_layout.py`
  (this machine's `graphify-out/`), `test_phone_extraction_fixture.py` (no object store offline).

**`make test-js`: 2697 passed, 1 failed**: `MatrixView.budget.test.tsx`'s first-frame timing under a full run's
load; alone, 1 passed.

The branch's own keyboard and axe, after the gates: `admin-maps.spec.ts` with `admin-models.spec.ts` 24 passed
(`95b9312.keyboard-admin-maps.txt`); axe on `maps-harness.html` 20 passed in dark, light and GOV.UK
(`95b9312.axe-maps-harness.txt`). Live, each under the platform lease on stack a (`P3_RED_RECORD.md`).
