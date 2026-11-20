# Open backlog placed: counts

Source: `ospreyflow_evidence_2026-11-18/BACKLOG_VERDICTS_2026-11-18.tsv`. Rows placed: every `open`, `partly built` and `cannot tell` row, 173 in all. The table is `OPEN_BACKLOG_PLACED.tsv` in this folder. Counts were computed by a script over that file, and every table below sums to its total.

Placing was done from each row's area, where, evidence and note. No code was re-read and nothing was run.

**Updated 19 November 2026 with the owner's answers** (15, 20, 21, 22 and 23). The changes:
- C016, C164, C170, C246 and L09 move from `later (D19)` into the build, with the security slices
  (`suggested_build` SE; the conductor names the slice).
- C123, H07, N10 and N14 move to an eleventh part, **Docs**. Docs is not yet a label in `dashboard/index.html`.
- Seven new rows, N19-01 to N19-07, are proposed ids for the conductor to renumber; they are not in the
  repository's backlog:
  - six from the dashboards inventory, N19-01 to N19-06. The silent cut at 100 boards and the case count go
    in with the security slices; the other four are `new: to be judged` by the review's tiers;
  - the D48 row, N19-07, owned by GG5.
- C023 is set aside with the demo items. It was never in this file, being closed.

The 173 rows placed on 18 November become 180.

## 1. Totals

By disposition:

| disposition | Rows |
|---|---|
| in build | 101 |
| later (D19) | 70 |
| new: to be judged | 4 |
| PL5 (D35) | 2 |
| dropped (D17) | 1 |
| dropped (D18) | 2 |
| **Total** | **180** |

By kind:

| open_kind | Rows |
|---|---|
| open | 145 |
| partly built | 16 |
| cannot tell — needs a run | 19 |
| **Total** | **180** |

Rows with a suggested build: SE 7, CO1 4, PL1 4, PL2 2, SE1 2, GG1 2, AD1 2, SE3 1, SE2 1, PL5 1, VA1 1, IS6 1, GG5 1.

## 2. In build: part by theme (101 rows)

| Part | Default | GOV.UK | Both | None | Total |
|---|---|---|---|---|---|
| Glass · Graph analysis | 0 | 0 | 5 | 0 | 5 |
| Glass · Ask & Chat | 0 | 0 | 1 | 1 | 2 |
| Glass · Reports and Cases | 1 | 0 | 1 | 0 | 2 |
| Ingest Studio | 0 | 0 | 3 | 12 | 15 |
| Rules and Monitoring | 0 | 0 | 0 | 6 | 6 |
| Admin | 3 | 0 | 0 | 2 | 5 |
| Conduit | 1 | 0 | 0 | 13 | 14 |
| Vault | 0 | 0 | 0 | 1 | 1 |
| Platform | 0 | 0 | 0 | 25 | 25 |
| Build line | 0 | 0 | 0 | 26 | 26 |
| Docs | 0 | 0 | 0 | 0 | 0 |
| **Total** | **5** | **0** | **10** | **86** | **101** |

## 3. All placed rows: part by theme (180 rows)

| Part | Default | GOV.UK | Both | None | Total |
|---|---|---|---|---|---|
| Glass · Graph analysis | 0 | 0 | 6 | 0 | 6 |
| Glass · Ask & Chat | 0 | 0 | 1 | 1 | 2 |
| Glass · Reports and Cases | 1 | 0 | 3 | 0 | 4 |
| Ingest Studio | 0 | 0 | 4 | 14 | 18 |
| Rules and Monitoring | 0 | 0 | 8 | 16 | 24 |
| Admin | 3 | 0 | 4 | 5 | 12 |
| Conduit | 1 | 0 | 0 | 18 | 19 |
| Vault | 0 | 0 | 0 | 6 | 6 |
| Platform | 3 | 0 | 1 | 54 | 58 |
| Build line | 0 | 0 | 0 | 27 | 27 |
| Docs | 0 | 0 | 0 | 4 | 4 |
| **Total** | **8** | **0** | **27** | **145** | **180** |

## 4. Rows placed by guess

| id | part | theme | disposition | Why it is a guess |
|---|---|---|---|---|
| C080 | Rules and Monitoring | None | later (D19) | Mixed carries; theme unclear |
| C106 | Glass · Graph analysis | Both | in build | A shared colour helper; no single owning screen |
| C210 | Rules and Monitoring | Both | later (D19) | Area is Admin, the words are in rules, lists and schedules |
| L05 | Ingest Studio | Both | later (D19) | Needs a screen for Laurium's document reading; which screen is not said |
| L12 | Platform | None | dropped (D17) | No scope named |

The four documentation rows are no longer guesses: the owner gave them the Docs part (answer 21).

## 5. Rulings that did not apply cleanly

- **D19 and the Later group.** "The Later group" is read as the 17 November review's tier "3 Later" (128 rows), from the hand-over's question 3. That parks 75 rows, including five security rows the summary lists as mattering first: C016, C164, C170, C246 and L09. **Owner's answer 20 (19 November): the five come into the build with the security slices.**
- **Specific rulings over D19.** L08 is in the Later tier, but D16 folds it into IS6, so it is `in build`. L12 and L14 are dropped (D17, D18) rather than parked.
- **D11 against D35.** D35 narrows D11. Only C193 and L04 go to PL5. N05, N06, N07, N11, C013, C082 and H01 stay `in build`; N05, N06, N07 and N11 are suggested for PL1 (laptop demo sound).
- **D15 and L04.** D15 sends the visitor allowance to demo fixes and D35 names L04 for PL5. The dashboard gives it its own build, VA1. L04's disposition is `PL5 (D35)` with VA1 as the suggested build.
- **C023.** It is closed (verdict built), so it is not in this file. D11 places it in PL5, but the 17 November ruling says it stays closed only if the owner recognises ADR-120 Amendment 18. That is still unconfirmed. **19 November: the owner has set C023 aside with the demo items; question 23 stays open.**
- **D15, certificate renewal.** No open row matches it. The dashboard says it was done on 18 November outside the line; only its record is owed. C020 (Java licence notice) and L10 (connection limits) are `in build` with PL2.
- **SE1 to SE3.** C039 and C071 (SE1, D29), C187 (SE2, D30) and C186 (SE3, D31) have disposition `in build`, with the slice in `suggested_build` and the ruling in `reason`. They are counted in the in-build table.
- **The admin model form.** L01 and A02 are `in build` with AD1. The 17 November ruling says to wait for the key-handling review. That is an order, not a removal.
- **D48** asks for a backlog row on site plans' rotation and pitch. No such row exists in the verdicts table. **19 November: added as N19-07, owned by GG5 (answer 22).**
- **The 19 that need a run.** They are kept and marked `cannot tell — needs a run`. Three are dropped (H06, L12, L14), one folds into IS6 (L08), eight are parked by D19 and eight are in the build.
