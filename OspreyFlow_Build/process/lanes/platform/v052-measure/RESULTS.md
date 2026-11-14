# v0.5.2 step 4: search measured on B's load (ADR-149 Amendment 2)

- **Run:** (to be filled in)
- **Stack and lease:** (to be filled in), (to be filled in) (rule 14: a figure taken without the lease is not a measurement)
- **The scripts' commit:** (to be filled in)
- **The load:** B, about 281,000 Persons. The owner's tens-of-millions figure is not measured (the owner's ruling of 13 November, "measure what is loaded").
- **Known difference:** the stores on the host's loopback, unsigned and without TLS; SigV4 measured at about 35 µs per request; TLS and the network to the endpoint not measured (ADR-149 Amendment 2).

| Measure | What | Budget | Failure figure | p50 / p95 / max | n | Class | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M1 | Suggestions, 2–6 characters, the largest loaded type | ≤ 300 ms | p95 > 300 ms, or any over 2 s | — | — | — | **not measured** |
| M2 | Suggestions in the Glass, last key to the list | ≤ 400 ms | > 600 ms | — | — | — | not measured here: a perf/ case in a browser slot |
| M3 | Name search (typos, variants, sounds-like) | ≤ 1 s | p95 > 2 s | — | — | — | **not measured** |
| M4 | Full text with the passage highlighted | ≤ 1.5 s | p95 > 3 s | — | — | — | **not measured** |
| M5 | An exact identifier ranked first | ≤ 1 s | p95 > 2 s | — | — | — | **not measured** |
| M6 | The feed's lag: a drawn node to searchable | ≤ 5 s | p95 > 30 s | — | — | — | **not measured** |
| M7 | Rebuild from the graph, B's whole load | measured, then the restore's bound set from it with a margin | the rebuild exceeds the bound the restore runbook gives it | — | — | — | not measured here: the restore's rebuild, timed |
| M8 | Drift check, B's whole load | inside its Job's 4 GiB, its peak flat as the load grows, ≤ 1 h | out of memory, a peak growing with the documents, or over 1 h | — | — | — | not measured here: its Job's peak and time |
| M9 | The fallback: OpenSearch stopped mid-session | the bar falls back and says so within the 5 s timeout | no message, or a wait over 5 s | — | — | — | **not measured** |
| M10 | The leak test at scale (m10-part) | nothing they may not see, count or infer, in results, counts, suggestions or snippets | any | — | — | — | **not measured** |
| M11 | Each container's peak working set during M1–M8 | peak ≤ 80% of its limit | at or over its limit, or killed | — | — | — | not measured here: the cluster's metrics |

A result between the budget and the failure figure is over budget, not failed; past the failure figure, step 4 fails (ADR-149 Amendment 2).
