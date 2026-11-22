# IS5a, before round 10: every case, open or closed (the line's table before a round of 5 or more; 22 November 2026)

The rows 1 to 23 are those of `OspreyFlow_Build/process/lanes/v062/slices/IS5a_ROUND9_TABLE.md` (22 verifier findings of rounds 1 to 8 and the first gate refusal), **unchanged except that row 23 is now closed (round 9, `947211eb0b`: the comment at `studioWords.ts:6` fixed, verified).** Round 10 is the owner's second `add-round` line, for **two places of words only**.

| # | Round | Kind | File and line | What | Status | Cause |
| --- | --- | --- | --- | --- | --- | --- |
| 1 to 20 | R1 to R7 | 13 faults, 7 test gaps | see the round-9 table | all closed | | |
| 21 | R8 | test gap | `OspreyFlow_Core/apps/pages/server/studio.ts:614` | No test that a held folder is bound to its case and dataset | **OPEN: backlog row 13, not for round 10** | no test |
| 22 | R8 | test gap | `OspreyFlow_Core/apps/pages/modules/studio-frame.ts:27` | No keyboard case for the dataset switch | **OPEN: backlog row 14, not for round 10** | no test |
| 23 | gate 1 | gate refusal | `OspreyFlow_Core/apps/pages/server/views/studioWords.ts:6` | A comment names the old path of files PL4d3d moved | closed (round 9, verified) | the comment itself |
| 24 | gate 2 | gate refusal | `OspreyFlow_Core/apps/pages/server/views/studioWords.ts:220` | A comment names `help/roles.ts` as the workspace's "until it moves"; PL4d3e moved it first | **OPEN: round 10** | merge order: PL4d3e merged between IS5a's verification and its merge |
| 25 | gate 2 | gate refusal | `OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md:754` | IS5a's own scenario text ("Exception candidates: when the person's rights cannot be read…") names a path PL4d3e moved | **OPEN: round 10** | the same |

**Totals:** 22 verifier findings (13 faults, 9 test gaps) plus three gate refusals' items (rows 23 to 25) = 25 items; closed 21; **open now 4**: rows 24 and 25 (**round 10's two places of words**) and rows 21 and 22 (backlog rows 13 and 14; not for round 10). **Convergence:** round 8 had no fault; both gate refusals are words naming moved paths, caused by the merge order.
