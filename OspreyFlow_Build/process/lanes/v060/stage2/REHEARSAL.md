# v0.6.0 stage 2 · the rehearsal (rules-b, 15 November 2026)

**Not a measurement.** Each command of `../STAGE2_SHEET.md` was run once, short (`STAGE2_SHORT=1`), to prove it
runs on today's main against B's load.

## How it ran
- **Stack and lease:** stack d, under rules-b's lease from 16:26:59Z, in rules-b's QUEUE turn. Down and released
  afterwards; the QUEUE line deleted.
- **The code:** branch `lane/rules-b-stage2` from main 33a7c9f, at 25671b1 for the main run and 4b98887 for the
  profile rerun.
- **Runs:**
  - 20261115T162715Z-0775a925: every step, 519 s (`rehearsal.txt`).
  - 20261115T163622Z-9810284c: profile, broken (`rehearsal-profile-broken.txt`).
  - The profile rerun after the fix, 324 s (`rehearsal-profile.txt`).
- **Results:** on d's host, `~/osprey-load/stage2-rehearsal-20261115T1627/`.

## Step by step
| Step | Exit | What it showed |
| --- | --- | --- |
| inputs | 0 | the three files' hashes are step 4's; d's six containers up |
| regen (20 cases) | 0 | `client_size_leaks` runs; `leaks_words.measured` true; written to its own folder, the files in use untouched |
| budgets (n 10, M6 n 3) | 0 | the five pytest cases passed: M1 68 / 71 ms, M3 171 / 199, M4 198 / 318, M5 177 / 313, M6 1,885 / 2,074 (p50 / p95; short, so not figures) |
| m9 | 0 | M9 met, max 1,783 ms; OpenSearch was up again afterwards |
| leaks (20 cases) | 0 | M10 met, 20 of 20 reached |
| never-join (20 cases) | **1** | M10 **unmeasured**, 17 of 20 reached (85%, under the 90% floor). See below |
| control | 0 | the words check fired on 5 of 5 |
| profile | 1, then 0 | `profile_m9.py` raised `TypeError`; fixed at 4b98887 and rerun, see below |
| table | 0 | every measure has a row; M2, M7, M8 and M11 say "not measured here" |

## Found
1. **`profile_m9.py` was broken on main, and is fixed (4b98887).**
   - It still built `SearchNodesBuilder` without the `record_ids` that ADR-124 Amendment 21 added. Its own
     docstring had foreseen this.
   - Now its `shipping` arm is `search_nodes` as built, timed whole, and the other variants are the
     pre-Amendment-21 query and its parts. Each variant's ids are compared with `shipping`'s.
   - `tests/test_profile_m9.py` renders every variant offline. It was red on main's file with the same
     `TypeError` (`profile_m9-red-first.txt`), and is green after the fix.
   - In the rerun, the fallback as built answered in 59–212 ms, against about 5,050 ms for the query before
     Amendment 21. Both gave the same ids for all five names.
2. **Never-join sits on its floor.**
   - On 14 November, 450 of 500 controls were reached: the 90% floor exactly. The first 20 cases here reached 17.
     The three not reached were org-1822, org-1894 and org-1911: the cleared control's first page did not name the
     companies record.
   - Nothing the measure reads has changed since: the same files, the same load, and the same search path.
     So the official run should reach the same 450 again, but with no margin.
   - The sheet now says what an under-floor result is: *unmeasured*, recorded as such, and the file is never
     trimmed to pass. Whether to keep the floor or the file is the orchestrator's ruling.
3. **M6 draws into B's case.** This rehearsal drew 8 nodes (3 after 5 warm-ups) into the intel case's analyst
   layer. The official run draws 55 more.
4. **Nothing else needed fixing.** #3, #4 and #5 changed no server-side search code, and every other runner ran
   unchanged.

## The reach widened, rehearsed again (the orchestrator's ruling, 15 November)
- **The change:** the floor stays at 90% and the file at 500. The control now looks within the first 3 pages of
  20 results, not page 1 alone, and the part-cleared principal is asked every page its control read (d68ac22).
- **Proved offline:**
  - The tests were red on main's `measure_search.py` and on three plants: the control asking page 1 alone, the
    part-cleared principal asking page 1 alone, and the control looking past the bound. The control was green
    (`reach-plants.txt`).
  - A record found only on page 2 counts as reached with the bound and as unreached without it.
- **Short again on d:** rules-b's lease from 17:03:57Z, its own QUEUE turn, 226 s (`rehearsal-reach.txt`).

| Step | Before (page 1) | With the bound |
| --- | --- | --- |
| never-join, 20 cases | 17 reached, *unmeasured* | **18 reached** (17 on page 1, 1 on page 2), *met* |
| leaks, 20 cases | 20 reached | 20 reached, all on page 1, *met* |

- **The reach rose, by one of the three:** two never-join controls still don't find the companies record within
  60 results.
- **What it means for the full file:** if the 500 behave like these 20, the official run gains some cases above
  450. 20 cases are too few to say how many.
