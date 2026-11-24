# Slice PL7f: diffs for the owner (none applied)

Both apply cleanly (`git apply --check`) to this branch's base. A protected file or an amendment is the owner's.

1. `PL7f_ADR152_AM5.diff` — the text of **ADR-152 Amendment 5** (`spec/06_DECISIONS.md`, proposed, not accepted) and its
   row in `spec/ADR_RESERVATIONS.md`. It records the three changes the owner made to the table of cases on
   24 November 2026 and the rule that `derive` is the only place the page service's addresses are computed.
   `spec/05_DEPLOYMENT.md` section 2.8 already says the same in the specification (the brief's step 0).
2. `PL7f_CI_YML_AND_MAKEFILE.diff` — wires `tests/harness/test_page_addresses_caddy.py` as a live-service test, as
   `tools/test_file_coverage_check.py` requires (it reads `OSPREY_TEST_CADDY`): ignored by the `test` job in
   `.github/workflows/ci.yml` and by `make test` in `OspreyFlow_Build/Makefile`, and run by GitHub's
   `access-key-proxy-test` job (GitHub is the second place; the Mac's gate is the first). **Until it is applied,
   `make test-file-coverage-check` names the file** ("in neither the `test` job's ignore list nor any live-service job").
   Shown in memory: red without the diff's wiring, clean with it.
