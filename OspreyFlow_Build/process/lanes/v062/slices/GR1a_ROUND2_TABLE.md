# GR1a, round 2: the scenario and the header say what was ruled (the conductor, 26 November 2026, 14:20 UTC)

From the round-1 verifier's record (tip `da17ce9d99`): one fault. **This round is the row below and nothing else.**

| # | Do | Done when |
| --- | --- | --- |
| 1 | **Scenario CS (`spec/08_ACCEPTANCE_SCENARIOS.md` about 891, 897 and 921) and `server/cases.ts`'s header (lines 8-9) still call the owner's GR1a questions open,** and line 891 misstates the address ruling. Scenario CS is this slice's own scenario, so correct it here, saying only what was ruled (RULINGS.md): **Q1 (a), the query form `/cases?case=<id>`** (the owner, 26 November 2026, about 10:30 UTC; "your ruled `/cases/{case_id}`" is wrong); **Q2, who made a case, is left out for 0.7.0**, with names later through `display_names` (BACKLOG row 39); **Q3 to Q5 (a)** (the three reads and the order as built). Remove the "may want to rule on" list, or make it say these were ruled and where. The header comment says what the code does and cites the ruling. Change no other spec text and no behaviour. | `git grep -n "question in the" -- OspreyFlow_Build/spec/08_ACCEPTANCE_SCENARIOS.md OspreyFlow_Core/apps/pages/server/cases.ts` finds nothing for GR1a's questions; the scenario tests that read Scenario CS stay green; your frozen checks green. |
