# SE6b, before round 10: every case, open or closed (the line's table before a round of 5 or more; 22 November 2026)

Rows 1 to 8 are those of `OspreyFlow_Build/process/lanes/v062/slices/SE6b_ROUND9_TABLE.md`, and `OspreyFlow_Build/process/lanes/v062/SE6b_ROUNDS_TABLE_2026-11-22.md` has the causes. Round 9 (the owner's one added round) closed the last verifier finding (the Admin list's query): **the round-9 verifier passed `7ce303416e` with no finding.**

| # | Source | What | Status |
| --- | --- | --- | --- |
| 1 to 8 | verifiers of rounds 1 to 8 | the faults and gaps of the removal path, the last being the Admin list reading the stamp | all closed |
| 9 | round-9 verifier | no finding | verified |
| 10 | the merge gate, 22 Nov | `test_the_refusal_is_in_the_shape_the_admin_screen_reads` reads the Admin client's old path under `apps/workspace/src/admin`, which PL4d3e moved to the shared package; on main plus this slice the file is not found | **OPEN: round 10 (one path)** |

**Open also, not for round 10:** backlog row 15 (the function the reader login can call) and row 16 (row security proved only against a fake). **Convergence:** the verifiers found nothing in round 9; the refusal is a path moved by a slice that merged first. The demo server's early warning named this test.
