# Platform-b · P5b's owed live proof (CARRIES row 65, ADR-114 Amendment 38 decision 9): report

Amendment 3 merged earlier today; its report is in main's history.

1. **Exit, met.** On the shared test server (stack b, under platform-b's lease), a named deployment's update backed up into its own folder (`backups/osprey-p5b-test/`), and a forced-failure rollback restored it: 185 records before, 185 after, no differences (`gates/p5b-proof-run4.txt`, PASSED at 77686d2).
2. **Not exercised:** the rollback's `git checkout` (the server's copy has no `.git`); the driver says so at the step.
3. **Runs 1–3, the driver's faults, each fixed:** the seed refused by preflight, then for no demo accounts (8b8c123); the old image gone before its put-back (held first, 9214d6b); compose without the env file (77686d2). Run 1's record: `gates/p5b-proof-run1.txt`.
4. **Every teardown was clean:** only `osprey-p5b-*` removed, the run's tags put back by ID, nothing of another's changed.
5. **Decision taken (accepted):** the after-check fails on what the run did and lists, without failing, what another lane did meanwhile.
6. **The prune question:** nothing pruned. Docker 29's containerd image store deletes an image when a build moves its last tag (reproduced with the run's own throwaway tag). osprey-small runs by digest, so lane builds cannot move it. Its ingest image is not on the server (sent to the orchestrator).
7. **Gates.** `make test` (offline, on the server) and `make -k ci` at the ready-to-merge head; the counts go in the message.
8. **Friction:** `process/friction/2026-11-10-platform-b-p5b-owed-proof.md`. **Route:** none added. **Questions:** none.
