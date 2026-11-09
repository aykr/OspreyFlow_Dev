# L3.3 gates, rebased on main 057a10e (rules' L2.9), 9 November 2026

The full gates ran at `5d2494b`, offline (closed ports 59991-59994, OSPREY_LANE unset). The head `b9c4ffa`
(tree `b2c1544928d493835b7209f0fbb7653ca9ec7375`) adds only the regenerated `AlertAtAddress.ts`. There
`make schemas-check` (466 match), `test_drift_gate.py` (2 passed) and `tsc` are green.

- **make -k ci** (`5d2494b.ci.txt`):
  - `schemas-check`: AlertAtAddress.ts out of date. L2.9's new type embeds a node's provenance, which
    L3.3's `Provenance.drawn` extends. Fixed at `b9c4ffa`.
  - `test-file-coverage-check`: green with `ci-wiring-L3.3.patch` applied (remade against this main).
  - `opentofu-check`: the provider registry timed out (network).
  - `trivy-image-ingest`: trivy's cache was locked by another process. The other six scans passed.
- **make test** (`5d2494b.test.txt`): 8857 passed.
  - This machine's own: `test_deployment_schema`, `test_valkey_config`, `test_layout`,
    `test_phone_extraction_fixture`, and the two `test_workspace_proxy` errors.
  - `test_proxy_tls_caddy`: "failed to bind host port … address already in use" (this machine).
  - `test_drift_gate`: the AlertAtAddress.ts above, fixed.
  - `test_test_file_coverage_check` and the six `test_board_store.py` errors: wired by the CI patch.
- **npm test** (`5d2494b.js.txt`): 2727 passed.
  - `MatrixView.budget`: timing under load.
  - `registryCoverage`'s RULES_PLACE_ACTIONS: main's own. `rules-place.spec.ts` names its registry
    through a variable, and neither file differs from main.
- **Boards keyboard** (`5d2494b.kb.txt`, with `registry-L3.3.patch`): 33 passed.
- **Boards axe** (`5d2494b.axe.txt`): 56 passed (dark, light and GOV.UK).
- **Live** (`5d2494b.live.txt`): lease case on stack c.
  - On stack c's own database, three tests failed reading rows another lane's code wrote. On a fresh
    database made and dropped under this lease: 310 passed.
  - The 1 failure is main's own (P2's two model routes missing from the route-rights table).
