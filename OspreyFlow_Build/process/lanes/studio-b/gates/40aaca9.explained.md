# studio-b · gates at 40aaca9 (rebased onto main 875bba4), 9 November 2026 — superseded

Offline, ports 59991–59994 pinned, no stack. `make -k ci`: the seven trivy image scans (Docker Hub 429)
and `test-file-coverage-check`. The latter named three files: the two live ones whose wiring is in
`L1.6_ci_makefile.diff` (the Makefile and ci.yml left the branch at the orchestrator's item 5), and
`test_connector_private_hosts.py`, an offline file whose `import asyncpg` (for an exception class) the
gate counts as live: **the lane's**, fixed in the next commit. With the diff applied, the gate reports
"853 test file(s), 0 allowlisted, no new drift". `make test`: 5 failed, 9369 passed, 6 skipped, 16
errors: the four of this machine's as at 3a5409c, the same coverage test, the two Docker Hub errors,
and 14 errors from the two live files, collected because the Makefile's ignore for them now rides in
the diff.
