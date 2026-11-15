# v0.6.0 stage 2 · search measured at client size (ADR-149 Amendment 2), the official run

**Verdict: met.** The run covered every measure stage 2 takes: M1, M3, M4, M5, M6, M9, and M10 (both the leak file
and the never-join file), with M10's words check shown to fire. M2, M7, M8 and M11 are measured elsewhere, as
step 4 recorded.

- **M1** (suggestions): p95 61.5 ms against 300 ms, none over 2 s.
- **M3** (names): p95 131.8 ms against 1 s.
- **M4** (full text): p95 187.9 ms against 1.5 s.
- **M5** (an exact identifier first): p95 159.4 ms against 1 s.
- **M6** (a drawn node to searchable): p95 2.11 s against 5 s.
- **M9** (OpenSearch stopped mid-session): the slowest answer was 1,469 ms against 5 s. The bar fell back and said
  so, and the index answered again 9.2 s after OpenSearch was started.
- **M10, the leak file:** no hidden id, count or word reached the part-cleared principal in 500 cases, all 500
  reached on page 1.
- **M10, never-join:** no failures in 500 cases. 466 controls reached their record (93.2%) against the 90% floor:
  450 on page 1, 12 on page 2 and 4 on page 3, within the first 3 pages of 20 results.
- **The positive control:** the words check fired on 5 of 5.

## The run
- **When:** 15 November 2026, 18:00:53Z (the lease) to 18:15:15Z (the last step). Stack d was then brought down and
  released, and rules-b's QUEUE line deleted. The run was in rules-b's own QUEUE turn, with `pgrep -x make` empty.
- **Stack and lease:** d, held by rules-b from 2026-11-15T18:00:53Z for the whole run (rule 14).
- **The load:** B, as step 4 measured it. The case is `01M7C2SXAPP3RF8QRSR2SKEMJK`.
- **The inputs:** the same three files as step 4 (step 1 checked their hashes):
  - `queries.jsonl` f564f75f…
  - `leaks.jsonl` ae02aa9c…
  - `never_join.jsonl` 48af1d50…
- **The limits:** the Conduit and the worker at the poc's limits (2 CPUs, 4 GB), started by platform's step 4
  runner (`step4_stack.py`), as step 4 ran.
- **The commands:** `STAGE2_SHEET.md` steps 0–8, each step one `stack_lease.sh remote rules-b -- bash
  OspreyFlow_Build/process/lanes/v060/stage2/run.sh <step>`. The raw logs are in `official/<step>.txt`. The results
  are on d's host under `~/osprey-load/stage2/<step>/`.
- **The code measured:** main **a06f952**. The run copy was rules-b's worktree on `lane/rules-b-stage2-official`,
  created from it with nothing changed.

### Why a run before #4's merge stands for v0.6.0
The orchestrator ruled, about 18:00Z, that stage 2 runs now on main rather than after #4 (`MORNING.md`, "Stage 2 run
before #4 merges"). #4 is Glass-only: it changes no route, store, schema or search.

rules-b checked this against #4's branch, `lane/case-b-v060-fullpage` at 0c10422. Its diff from main changes:
- 24 files under `OspreyFlow_Core/apps/workspace/`;
- the spec, the docs, its own process folder;
- two docs tests (`test_user_guide_ask_chat.py`, `test_user_guide_ask_items.py`);
- **nothing under `services/` or `packages/`.**

The server measured here is therefore the server v0.6.0 ships with #4 merged. CI on main after the final push is the
orchestrator's half of stage 2.

## The table (`run.sh table`, `results_table.py`)
| Measure | What | Budget | Failure figure | p50 / p95 / max | n | Class | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M1 | Suggestions, 2–6 characters, the largest loaded type | ≤ 300 ms | p95 > 300 ms, or any over 2 s | 55.9 / 61.5 / 254.2 ms | 200 | suggest | **met** |
| M2 | Suggestions in the Glass, last key to the list | ≤ 400 ms | > 600 ms | — | — | — | not measured here: a perf/ case in a browser slot |
| M3 | Name search (typos, variants, sounds-like) | ≤ 1 s | p95 > 2 s | 112.3 / 131.8 / 234.2 ms | 200 | names | **met** |
| M4 | Full text with the passage highlighted | ≤ 1.5 s | p95 > 3 s | 140.8 / 187.9 / 268 ms | 200 | fulltext | **met** |
| M5 | An exact identifier ranked first | ≤ 1 s | p95 > 2 s | 122.8 / 159.4 / 275.8 ms | 200 | exact | **met** |
| M6 | The feed's lag: a drawn node to searchable | ≤ 5 s | p95 > 30 s | 1,049.1 / 2,113.4 / 2,142.7 ms | 50 |  | **met** |
| M7 | Rebuild from the graph, B's whole load | measured, then the restore's bound set from it with a margin | the rebuild exceeds the bound the restore runbook gives it | — | — | — | not measured here: the restore's rebuild, timed |
| M8 | Drift check, B's whole load | inside its Job's 4 GiB, its peak flat as the load grows, ≤ 1 h | out of memory, a peak growing with the documents, or over 1 h | — | — | — | not measured here: its Job's peak and time |
| M9 | The fallback: OpenSearch stopped mid-session | the bar falls back and says so within the 5 s timeout | no message, or a wait over 5 s | max 1,469.1 ms | 10 |  | **met** |
| M10 | The leak test at scale (m10-part), the leak file | nothing they may not see, count or infer, in results, counts, suggestions or snippets | any | — | 500 (500 reached) |  | **met** |
| M10 | The same, the never-join file | the same; at least 90% of the controls reach their record | any leak; under 90% reached is *unmeasured* | — | 500 (466 reached) |  | **met** |
| M11 | Each container's peak working set during M1–M8 | peak ≤ 80% of its limit | at or over its limit, or killed | — | — | — | not measured here: the cluster's metrics |

A result between the budget and the failure figure is over budget, not failed. Past the failure figure, the measure
fails (ADR-149 Amendment 2). No result here is over budget.

## M10's reach
**The reach bound: the first 3 pages of 20 results** (`measure_search.REACH_PAGES` = 3, `LEAK_PAGE_SIZE` = 20). The
bound is the orchestrator's ruling of 15 November, after stage 2's rehearsal; the floor and the files are unchanged.
A control looks within the bound for its hidden record. The part-cleared principal is then asked every page its
control read, so a record reached on page 2 is also checked for a leak on page 2.

| File | Cases | Reached | `reached_on_page` | Indeterminate | Failures | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `leaks.jsonl` | 500 | 500 (100%) | page 1: 500 | 0 | 0 | **met** |
| `never_join.jsonl` | 500 | 466 (93.2%; the floor is 450) | page 1: 450, page 2: 12, page 3: 4 | 34 (not within 60 results) | 0 | **met** |

**The positive control (rule 15):** `positive_control.py` searched 5 hidden reports' own titles as their cleared
control. The words check fired on 5 of 5, so a hidden word in an answer is found when it is there.

## Against 14 November (step 4 on the shipping code, `platform/v052-measure/RESULTS.md`)
| Measure | 14 November p50 / p95 | Today p50 / p95 |
| --- | --- | --- |
| M1 | 56.4 / 61.1 ms | 55.9 / 61.5 ms |
| M3 | 111.1 / 126.2 ms | 112.3 / 131.8 ms |
| M4 | 143.7 / 183.8 ms | 140.8 / 187.9 ms |
| M5 | 117.2 / 143.8 ms | 122.8 / 159.4 ms |
| M6 | 1,044.6 / 2,081.7 ms | 1,049.1 / 2,113.4 ms |
| M9 | max 1,490.2 ms | max 1,469.1 ms |
| M10 leaks | 500 of 500 | 500 of 500 |
| M10 never-join | 450 of 500 (page 1 alone) | 466 of 500 (450 on page 1) |

- **The figures agree within noise.** No server-side search code changed between 14 November's tree and a06f952
  (`STAGE2_SHEET.md`, "What changed since step 4").
- **Never-join's 450 on page 1 is the same.** The 16 more are the widened reach, not a change in the product.

## The runs
| Step | Run id (`osprey-runs/rules-b.meta/runs/<id>/log`) | Took | Log |
| --- | --- | --- | --- |
| 1 inputs | 20261115T180109Z-c23aa504 | under 1 s | `official/inputs.txt` |
| 2 budgets | 20261115T180118Z-78c28d03 | 240 s | `official/budgets.txt` |
| 3 m9 | 20261115T180527Z-24c84373 | 81 s | `official/m9.txt` |
| 4 leaks | 20261115T180655Z-855807e7 | 230 s | `official/leaks.txt` |
| 5 never-join | 20261115T181052Z-1bb48eb4 | 176 s | `official/never-join.txt` |
| 6 control | 20261115T181356Z-8c3b3385 | 70 s | `official/control.txt` |
| 7 table | 20261115T181513Z-a7ad753d | 1 s | `official/table.txt` |

- **M6 drew into B's case:** 55 nodes into the intel case's analyst layer (50 measured, 5 warm-up).
- **Neither `profile` nor `regen` was run.** No figure was over budget, and `scripts/client_size_leaks.py` has not
  changed since 14 November.
