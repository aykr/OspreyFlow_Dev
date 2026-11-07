# glass lane · report · L2.3 part 1, the case screen's lightening: a prototype round (7 November 2026)

1. **Harness:** `keyboard/case-screen-options-harness.{html,tsx}`, never wired into the app. It uses the real shell (top bar, place switcher, banner, rail, `SidePanelStack`), with stand-ins for search, the panels' contents and the canvas. `?variant=today|a|b|c`.
2. **How counted:** Tab stops from the top of the page until the canvas has focus, at 1440 by 900, including the skip link. `keyboard/case-screen-options.spec.ts` pins the counts; its screenshot test runs only with `OSPREY_L23_SHOTS=1`. The ADR's "some 25" measures 29 here (28 without the skip link). The right-hand column's 3 panels hold 15 parts.
3. **Today** (reference): 29 before the canvas; the column shows 15 parts.
4. **A, ADR-145 decision 4 as written:** 29 before the canvas; 8 parts shown. The column opens with the Inspector; Metrics and the Query builder are folded below it, in their order. One click further: Metrics and the Query builder. Trade-off: nothing before the canvas changes.
5. **B, A plus a trimmed rail and view switch:** 24 before the canvas; 8 parts shown. The rail keeps Cases and Explore (Monitoring is already in the banner); Ownership, History, Questions and Dashboards go under the rail's ⋯ *More*. The view switch keeps Graph and Map, with Matrix and Reports under *More views*. Trade-off: six destinations are one click further, but the rail still shows the two used most.
6. **C, B with no rail:** 20 before the canvas; 8 parts shown. The rail's tools become one *Tools ▾* menu in the banner; Help moves to the account menu; the canvas gains the rail's 48px. Trade-off: the fewest stops and the most canvas, but every tool is behind a menu, and Monitoring's open-alert count, which the rail carries today, needs a new place.
7. **Screenshots:** `process/lanes/glass/l2.3/{today,a,b,c}-{dark,light,govuk}.png`, 12 files.
8. **Axe:** `every-harness.spec.ts` scans every variant in dark, light and GOV.UK; 16 pass.
9. **Question sent to the orchestrator:** which lightening part 2 builds. **B (recommended)**, A, C, or keep today's column.
10. **Found:** under GOV.UK the banner's content line opens with a stray "·" (`shell/ContextBanner.tsx`). I left it for part 2, since this part allows no `src` change.
11. **Commit:** eff7570, plus the commit holding this report. No `src/**` change.
12. **Still running:** nothing. No dev stack or lease used.
