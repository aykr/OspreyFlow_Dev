# v0.6.0 stage 4 · the package test on candidate `fb7f336` · stopped after row 5

Run by platform-b on 16 November 2026, 12:23–12:43Z, on R1's kind cluster (stack b's lease), from a copy of
`fb7f336` (the Glass candidate: case's B, case-b's A+C, platform's step-6 all-pods fix b53f303) whose
`OspreyFlow_Core` was the candidate's exactly and whose `OspreyFlow_Build` carried the run's tooling fixes
(`lane/platform-b-v060-chart-before-listing`). **Stopped at the row 5/6 boundary on case's word (deputy, 12:42Z)**:
CI 43864213118 found an accessibility defect in case's B (the merged-drawing notes in Saved view Details scroll with
no keyboard access under GOV.UK; axe `scrollable-region-focusable`). A new C follows and stage 4 restarts from row 0
on it. Records: `~/osprey-runs/platform-b.c7/stage4-fb7f336/` (25 files); the samples in R1's
`memory-samples.fb7f336-to-row5.jsonl`.

**Stage 3 on fb7f336: PASS.** VERSION v0.6.0; `changelog_check --tag v0.6.0`; the four guides v0.6.0 (user 1.74,
administration 2.24), `test_docs_pdf.py` 18 passed; the publication check 0 new, the citations clean. The warm dry run
from a hash-checked archive, rc 0 (12:15:51–12:17:07Z): seven images with the 2026-11-16 stamp, seven trivy scans
clean, the lock refusing only our five, `ospreyflow-0.6.0.tgz`; scan tags removed. `make chart-check
cp-policy-check`: 393 passed.

| # | Result | What it showed |
| --- | --- | --- |
| 0, 0m | PASS (146 s) | the 32 GiB node; the registry started empty; the stand-ins; the sampler |
| 1 | PASS (369 s) | the cold INSTALL, every block; step 6's block now reads `logs -l app.kubernetes.io/name=api --since=24h --tail=-1 --prefix` and said no sign-in was refused; the search rebuild Completed; the Glass answers |
| 2 | PASS | R1's 37 checks |
| 3 | PASS | the dashboards check, 41 checks and 2 RECORD lines |
| 4, 4b, 4c | PASS | spec 08 on poc 14 passed, 15 skipped; the seed-free halves 3 passed; both plants red, as built green. Search lag 0.1–2.2 s, a redraw settled at 5.6 s |
| 5 | PASS (243 s) | a set, a change after it gone after the restore; the rebuild 225/225, the drift check none |
| 6–11 | not run | stopped on case's word |

Memory to row 5: 68 samples, 0 gaps, the node's peak 12.18 GiB. `down` afterwards: no cluster, no container, no
sampler. Lease b kept.

**For row 9b on the next C:** R1 renders the api at `replicas=1`; ea5fc61's second pod was the rollout's. The next
run checks both: during a rollout, and with the api scaled to 2 for the test alone.
