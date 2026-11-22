# IS5a, before round 11: every case, open or closed (the line's table before a round of 5 or more; 22 November 2026)

Rows 1 to 25 are those of `OspreyFlow_Build/process/lanes/v062/slices/IS5a_ROUND10_TABLE.md` (every verifier finding of rounds 1 to 8 and the first two gate refusals); **rows 24 and 25 (the two places of words) were closed in round 10 (`d6ff1cf38a`, verified), and the Stop hook's two reds (formatting of main's files, a scan row) were dealt with.** Round 11 is the owner's second `add-round` line.

| # | Source | What | Status |
| --- | --- | --- | --- |
| 1 to 20 | verifiers of rounds 1 to 7 | 13 faults and 7 test gaps | all closed |
| 21, 22 | verifier of round 8 | two test gaps (backlog rows 13 and 14) | open, **not for round 11** |
| 23 to 25 | the gate's first and second refusals | comments and a scenario line naming moved paths | closed (rounds 9 and 10) |
| 26 | round-10 verifier (`d6ff1cf38a`) | no finding | verified |
| 27 | the conductor's cheap checks, before the gate | `mypy`: `OspreyFlow_Core/packages/schemas/deployment.py` line about 2154, "Returning Any from function declared to return `dict[str, object]`" | **OPEN: round 11** |
| 28 | the merge, 22 Nov 11:07 | the branch conflicts with main in `OspreyFlow_Core/apps/pages/server/app.ts` (SE8c merged first) | **OPEN: round 11** |

**Totals:** 28 items; closed 24; **open now 4**: rows 27 and 28 (**round 11's two things**) and rows 21 and 22 (backlog rows 13 and 14; not for round 11). **Convergence:** the last verifier found nothing; every refusal since is a consequence of the merge order or of a check the slice's own checks did not run.
