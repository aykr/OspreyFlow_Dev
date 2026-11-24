# Slice PL7f: diffs for the owner (none applied)

Both apply cleanly (`git apply --check`) to this branch's base. A protected file or an amendment is the owner's.

1. `PL7f_ADR152_AM5.diff` — the text of **ADR-152 Amendment 5** (`spec/06_DECISIONS.md`, proposed, not accepted) and its
   row in `spec/ADR_RESERVATIONS.md`. It records the three changes the owner made to the table of cases on
   24 November 2026 and the rule that `derive` is the only place the page service's addresses are computed.
   `spec/05_DEPLOYMENT.md` section 2.8 already says the same in the specification (the brief's step 0).
2. `PL7f_CI_YML.diff` — adds `tests/harness/test_page_addresses_caddy.py` to GitHub's `access-key-proxy-test` job, with
   the Caddy binary taken from the image given in `OSPREY_CADDY_BINARY` (GitHub is the second place; the Mac's gate is the
   first). **Nothing in it is needed for the merge gate:** the test is an ordinary test (it reads no `OSPREY_TEST_*`
   variable, so `tools/test_file_coverage_check.py` does not call it a live-service test), it runs in `make test` and the
   `test` job, and `make test-file-coverage-check` is clean without it. (Round 1 of this slice wired it as live-service
   through a Makefile hunk and an `--ignore`; round 2 removed both, on the conductor's ruling.)
