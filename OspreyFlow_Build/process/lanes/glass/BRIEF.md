# Glass lane · brief L2.3, part 2 · build variant B of the case screen's lightening

Written by the orchestrator, 7 November 2026. The owner chose **variant B** from part 1's prototype round
(`process/lanes/glass/l2.3/`, the harness `keyboard/case-screen-options-harness.html?variant=b`). Opus,
medium. Size M.

**Binds.** `process/CLAUDE.md` rules 1–15 (13 above all); ADR-145 decision 4 and N4; ADR-085, ADR-096 (the
panels' order and folding); `spec/02_GLASS_FRONTEND.md` (the case screen, the rail, the view switch).
Reserved for you: **ADR-145 Amendment 2**, which records variant B (heading
`### ADR-145, Amendment 2 (7 November 2026) — …`).

**Build variant B in the product** (`src/**`), as the harness shows it:
1. The right-hand column opens with the Inspector only. Metrics and the Query builder are one click away,
   keeping their order and folding.
2. The rail keeps Cases and Explore. Ownership, History, Questions and Dashboards go under the rail's
   ⋯ More. Monitoring stays reachable from the banner's sections.
3. The view switch keeps Graph and Map, with Matrix and Reports under More views.
4. The GOV.UK banner's stray leading "·" is fixed (`shell/ContextBanner.tsx`).
All of this in dark, light and GOV.UK.

**Tests first.**
- A keyboard case for every new or moved action: More on the rail, each destination under it, More
  views, and the column's one-click panels. Each is shown red with its handler removed. Send me the new
  registry ids as a diff; I land them with your merge.
- Every existing keyboard case that reaches a moved destination is updated, not deleted.
- Axe in all three themes.
- A count test: the case screen has 24 Tab stops before the canvas (red if a control returns), and the
  column shows 8 parts.

**Files.** The Glass lane's map plus `apps/workspace/src/canvas/**`'s panel host only if the column lives
there. Tell me if so; I ratify at merge. `canvas/**` is Lane 3's, so keep to the column's host.

**Exit.** Variant B in the product; the keyboard, axe and count tests green; `spec/02` and ADR-145
Amendment 2 written; DEMO_GUIDE chapters that name a moved rail entry updated (text only); a friction
fragment. **Report** (at most twenty lines): the exit, the proving tests, the commits, one hand check
(full commands and where to click, default and GOV.UK). Owner questions go to me by message.
