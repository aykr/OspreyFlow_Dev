# v052-measure · the measurement session's plan (route step 4, Mon 23 Nov)

Written by the platform lane on 14 November 2026, for the orchestrator to put the proposed budgets to the owner
as one decision before Mon 23. **Nothing here is in `spec/` until the owner accepts it**; the budgets below are
proposals.

## What already exists, and what does not

- **No budget is stated anywhere** for search latency (names, full text, highlighting, ranking, grouped counts,
  filters), the index feed's lag, the rebuild's or the drift check's duration, or the load's duration. That holds
  on main and on every v0.5.2 branch: `lane/rules-v052-index` (3c), `lane/studio-search` (3d) and
  `lane/rules-v052-load` (B).
- **The load is at full scale (1.0)**: the owner ruled full scale after the write-path fix (ADR-124 Amendment 18),
  so the largest node type is Person at about 281,000 (`v052-load/DESIGN.md`'s 70,250 at 0.25, times four). The
  figures below are based on it.
- **The figures that do exist:**
  - ADR-059's rule: a suggestion over about 300 ms on the largest case needs an index-backed form
    (`spec/06_DECISIONS.md:9065`; repeated by ADR-061 and ADR-074 as "unmeasured for names").
  - The Glass waits 250 ms after typing stops before asking for suggestions (`SUGGEST_PAUSE_MS`).
  - The search service's timeouts, after which the bar falls back: 5 s for a search, 2 s for a suggestion
    (`lane/studio-search`, ADR-149).
  - The drift check streams: both sides in one id order, compared a page at a time, its memory bounded by the
    page, not the graph (`lane/rules-adr124-am18` 90442ba; `test_drift_streams.py`, red first on the whole-set
    check, plant V78).
  - The poc manifest's sizes, which ADR-148 Amendment 12 decision 4 calls "the profile's proposals, not
    measurements", for step 4 to measure.
- **No harness times search.** `perf/perf.spec.ts` (glass-perf) times the Glass's first frame on a harness page with
  no backend. `bench_reader_view_previews.py` times working-set previews against a stub graph. B's
  `load_client_size.py` and `calibrate.sh` time the load's own stages.
- **The owner's words:**
  - "Suggestions at typing speed, with one type in the tens of millions" (ROUTE_052 scope 5).
  - On 13 Nov: "suggestions measured on what is loaded, said plainly" (MORNING).

## Before the session (preconditions)

1. 3c, 3d, 3e′ and B are on main, and B's load is up on its long-leased stack. The measurement runs on **that**
   stack, under the orchestrator's word, with rules' lease or a hand-over of it; never a second load.
2. The drift check reports "none" on the load, as `v052-load/DESIGN.md:159-162` requires before step 4.
3. A synthetic query set is made from B's plants (the `truth` column), never typed by hand:
   - exact identifiers;
   - names with one typo;
   - spelling variants;
   - sounds-like names;
   - full-text phrases from the narrative documents;
   - prefixes of 2 to 6 characters for suggestions.

   200 queries of each class, fixed by a seed.
4. Two principals, as B's accounts allow: one cleared for everything loaded, and one for a part. The leak test
   (requirement a) runs at this scale as the second.

## What is measured, how, and the proposed budgets

Each latency is measured at the Conduit, by `scripts/measure_search.py` (to be written; below), as a p50, p95, p99
and max over the query class. A warm-up of 20 is discarded, and the server's other runs are paused. The Glass's
end-to-end is measured separately, in a browser.

| # | What | Proposed budget (p95) | A failure | Basis |
| --- | --- | --- | --- | --- |
| M1 | Suggestions (`POST /v1/suggest`), 2–6 characters, on the largest loaded type (Person, about 281,000) | ≤ 300 ms | p95 > 300 ms, or any over 2 s (the fallback's timeout) | ADR-059's 300 ms; the owner's "typing speed". **The owner's tens-of-millions figure is not measured, by the owner's ruling of 13 Nov ("measure what is loaded")**: the result says so beside the figure |
| M2 | Suggestions in the Glass: last key to the list shown, the 250 ms pause excluded | ≤ 400 ms | > 600 ms | M1 plus one render; spec 02 §5's hover budget, 100 ms, as the render's share |
| M3 | Name search (typos, variants, sounds-like), grouped by type with counts | ≤ 1 s | > 2 s | Half the fallback's 5 s, so the fallback never fires under normal load |
| M4 | Full text with the passage highlighted, with a dataset and a date filter | ≤ 1.5 s | > 3 s | Below the 5 s timeout, with room for highlighting |
| M5 | Ranking: an exact identifier comes first | 100% of the exact-identifier class first | any not first | Scope 3 (a correctness figure, measured on the same runs) |
| M6 | Index feed lag: a change made through the Conduit to searchable | ≤ 5 s | > 30 s (the indexer's lease) | ADR-150: "lags the graph by the indexer's poll" (1 s idle) |
| M7 | Rebuild from the graph, B's whole load | measured and recorded, then the restore's bound set from it | the rebuild exceeds the bound the restore runbook gives it | See finding F1 |
| M8 | Drift check, B's whole load | finishes inside its Job's 4 GiB, its peak flat as the load grows, ≤ 1 h | out of memory, a peak that grows with the documents, or over 1 h | The streaming check's bound by the page (rules' 90442ba); the poc manifest's 4 GiB; see finding F2 |
| M9 | The fallback: OpenSearch stopped mid-session | the bar falls back and says so within the 5 s timeout | no message, or a wait over 5 s | Requirement c |
| M10 | The leak test at scale (the part-cleared principal) | nothing they may not see, count or infer, in results, counts, suggestions or snippets | any | Requirement a (pass or fail, not a time) |
| M11 | Sizes: each container's peak working set during M1–M8 | peak ≤ 80% of its limit | at or over its limit, or killed | ADR-148 Am 12 d4: step 4 measures the manifest's sizes |

**How each becomes a gate**, once accepted:
- **M1, M3, M4, M5 and M6:** the live test file `tests/perf/test_search_budget_live.py`, run by step 6 (`v052-r1`) and
  at each release against the load. It fails at the failure figure, not the budget (ADR-149 Amendment 2). M6 draws a
  node on a board and polls the search until the index answers it (`measure_search.measure_lag`).
- **M1, M3 and M4 in CI:** a regression gate on a fixed 1-million-name corpus (CI cannot hold B's load). It fails if
  a p95 grows by more than 50% over its recorded baseline, as glass-perf is a regression gate.
- **M2:** a case in `perf/`, beside glass-perf, against the live stack in a granted browser slot.
- **M5:** in the same live file (every exact identifier first). **M10:** the same file's pass/fail case
  (`measure_search.measure_leaks`), each case a hidden record's query as `m10-part`, its control the cleared subject of
  the record's owning unit (`m10-cleared-<unit>`, one per R-owning unit: unit-fiu, unit-intel-covert, unit-covert,
  unit-border). Its cases are derived by rules' generator from B's SAME_AS truth and source table, on the case
  *Intelligence reports* (ADR-149 Amendment 2). Step 4 leaves M6's board and its drawn nodes in B's case (no route
  removes them).
- **M7 and M8:** they set the runbooks' and the CronJobs' bounds and memory, held by the render tests.
- **M11:** changes the manifest and the profile together, as ADR-148 Amendment 12 decision 4 says.

## What the session produces

- `process/lanes/platform/v052-measure/RESULTS.md`:
  - each measurement's figures;
  - its run id, and the stack and lease it ran under (rule 14: a figure taken without the lease is not a
    measurement);
  - the script's commit.
- For each budget, a plain "met" or "not met", with what not met means for v0.5.2.
- The manifest's and the profile's sizes changed where M11 says so, in one commit with their render tests.
- What the load cannot answer, said plainly beside the figure it limits (M1's scale).

## Findings already, before any measurement

- **F1. The restore's rebuild bound is a guess.** On 13 Nov I gave the recovery runbook's search rebuild 5
  minutes to start and 30 to finish (the orchestrator's ruling against the earlier 6 h). Nothing measured a rebuild
  at client size. If M7 is longer, every restore of a client-size deployment fails at its last step. The bound must
  come from M7, with a margin; until then, a restore on a large deployment may stop at its rebuild and say why. It
  says so in words, and the data is restored by then.
- **F2. The drift check's memory, now that it streams.** The whole-set check needed about 150 bytes a
  document (about 4.5 GB at thirty million) against the drift Job's 4 GiB. Rules' streaming check
  (`lane/rules-adr124-am18` 90442ba) bounds its memory by the page; its test holds that offline. M8 confirms it on
  the full load: the peak recorded with the document count, and expected flat, not proportional.

## Owner questions the plan cannot settle

- **The budgets above**, as one decision (the orchestrator puts them to the owner): accept, change, or measure
  without budgets. (Whether to measure suggestions at tens of millions was ruled on 13 Nov: measure what is
  loaded.)

## The script, to be written before Mon 23 (offline, then shown red first)

`scripts/measure_search.py` runs in the api image on the load's stack.

- **Inputs.** The query set (a file made from B's plants), the principal, the class, N and a warm-up.
- **Requests.** The Conduit's own routes (`/v1/suggest`, the search route 3d adds), signed as the principal, as the
  Glass sends them.
- **Output.** The percentiles as JSON, with the run's commit and stack.
- **The lag measurement.** It writes a synthetic node through the Conduit and polls search until it appears.
- **Red first.** A planted slow path, a sleep in a stub Conduit, must turn its check red at the failure figure.
  Then the timer is known to measure, not merely exist (rule 15).
