# v0.5.2 step 4: search measured on B's load (ADR-149 Amendment 2)

- **Runs:** one a measure, all on stack d under rules' lease, each listed under the table with its run id, its results folder on d's host (`~/osprey-load/step4/`) and what was run; the full logs are `~/osprey-runs/rules.meta/runs/<run id>/log`.
- **Stack and lease:** d, rules, since 2026-11-14T03:27:42Z (rule 14: a figure taken without the lease is not a measurement)
- **The scripts' commit:** M1 and M3 to M6 at 8ba5ed6; M9 and M10 from rules' run trees with this branch's runner at 2aa40e3 or later (the echo and the 90% floor) and rules-m10-query (merged as 55a44d5); M9 with ADR-124 Amendment 21 (`lane/rules-adr124-am21`, merged to main as 4693457).
- **The load:** B, about 281,000 Persons. The owner's tens-of-millions figure is not measured (the owner's ruling of 13 November, "measure what is loaded").
- **Known difference:** the stores on the host's loopback, unsigned and without TLS; SigV4 measured at about 35 µs per request; TLS and the network to the endpoint not measured (ADR-149 Amendment 2).

| Measure | What | Budget | Failure figure | p50 / p95 / max | n | Class | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M1 | Suggestions, 2–6 characters, the largest loaded type | ≤ 300 ms | p95 > 300 ms, or any over 2 s | 56.8 / 61.3 / 173.3 ms | 200 | suggest | **met** |
| M2 | Suggestions in the Glass, last key to the list | ≤ 400 ms | > 600 ms | — | — | — | not measured here: a perf/ case in a browser slot |
| M3 | Name search (typos, variants, sounds-like) | ≤ 1 s | p95 > 2 s | 856.3 / 912.7 / 1003.9 ms | 200 | names | **met** |
| M4 | Full text with the passage highlighted | ≤ 1.5 s | p95 > 3 s | 884.5 / 957 / 1005.6 ms | 200 | fulltext | **met** |
| M5 | An exact identifier ranked first | ≤ 1 s | p95 > 2 s | 857.1 / 914.7 / 1011.5 ms | 200 | exact | **met** |
| M6 | The feed's lag: a drawn node to searchable | ≤ 5 s | p95 > 30 s | 1799.1 / 2836 / 2997.9 ms | 50 |  | **met** |
| M7 | Rebuild from the graph, B's whole load | measured, then the restore's bound set from it with a margin | the rebuild exceeds the bound the restore runbook gives it | — | — | — | not measured here: the restore's rebuild, timed |
| M8 | Drift check, B's whole load | inside its Job's 4 GiB, its peak flat as the load grows, ≤ 1 h | out of memory, a peak growing with the documents, or over 1 h | — | — | — | not measured here: its Job's peak and time |
| M9 | The fallback: OpenSearch stopped mid-session | the bar falls back and says so within the 5 s timeout | no message, or a wait over 5 s | max 1490.2 ms | 10 |  | **met** |
| M10 | The leak test at scale (m10-part) | nothing they may not see, count or infer, in results, counts, suggestions or snippets | any | — | 500 (500 reached) |  | **met** |
| M11 | Each container's peak working set during M1–M8 | peak ≤ 80% of its limit | at or over its limit, or killed | — | — | — | not measured here: the cluster's metrics |

A result between the budget and the failure figure is over budget, not failed; past the failure figure, step 4 fails (ADR-149 Amendment 2).

## The runs behind each row

| Measure | Run | Results folder | Notes |
| --- | --- | --- | --- |
| M1, M3, M4, M5, M6 | 20261114T143856Z-516ef319, 14:38:56–14:52Z | `results/` | step 2's measured run, at 8ba5ed6; "1 failed, 5 passed, 1 deselected", the one failure M10's controls before rules' subject fix |
| M9 | 20261114T203513Z-a7331cae, 20:35–20:37Z | `results-m9-am21/` | with ADR-124 Amendment 21; OpenSearch (`osprey-test-d-opensearch`) stopped mid-session: the five name searches answered from the fallback in 92–105 ms, the suggestions within 1,490 ms, the index back in 9.2 s. On main's adapter it was not met: run 20261114T143515Z-d6be4f56, 5,301–5,543 ms, `results-m9/` |
| M10, leaks | 20261114T205703Z-af53b1e6, 20:57–21:01Z | `results-m10-leaks-3/` | 500 cases, 500 controls reached, 0 failures, 0 indeterminate; every case with a checked word (rules' regenerated files, run 20261114T205357Z-b5d8989c: 73,191 words dropped that the case's query or visible records hold) |
| M10, never-join | 20261114T204635Z-869d5050, 20:46–20:48Z | `results-m10-never-join-2/` | 500 cases, 450 controls reached (90%, the floor), 0 failures, 50 indeterminate |
| M10, the words check's positive control | 20261114T210353Z-80a82366, 21:03–21:04Z | — | a planted hidden word in the answer was found in 5 of 5; the hidden record's `sent_at` shows only at `.nodes[].properties`, which the check reads |

Not results: the void and masked runs (`results-expired-20261114T142209Z/`, `results-never-join-masked-20261114T143128Z/`), M10's first runs with the new subjects (`results-m10-leaks/`, `results-m10-never-join/`: the query's echo and words visible records hold), and `results-m10-leaks-2/` (run 20261114T204142Z-229690b0: 500 failures on whole titles the case's own query holds, before rules' regenerated files). `STEP4_RECORD.md` says why each is set aside.

## What each figure means for v0.5.2

- **M1, M3, M4, M5:** met at client size (B, 642,460 nodes) under the poc's limits (the Conduit at 2 CPUs and 4 GB). M3 to M5 sit at about 860 ms p50, close to the 1 s budget. That run predates ADR-124 Amendment 20, and a page measured since takes about 100 ms (`STEP4_RECORD.md`, the page's profile); the gap is being measured, so these rows stand as measured and are not revised from the profile.
- **M6:** a drawn node is searchable within 3 s, inside the 5 s budget.
- **M9:** met with ADR-124 Amendment 21, merged to main as 4693457 (the orchestrator, 14 Nov) and so in the candidate: without it, a search with OpenSearch down takes over 5 s at client size and the bar's own timeout is passed.
- **M10:** no leak at scale: no hidden id, count or word reached the part-cleared reader in 1,000 cases, with the check shown to fire. The never-join file is at the 90% floor exactly; the orchestrator's ruling holds the floor where it is.
- **M2, M7, M8, M11:** not measured by this run; each row says where.

