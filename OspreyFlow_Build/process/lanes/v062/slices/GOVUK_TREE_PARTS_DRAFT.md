# SUPERSEDED on 24 November 2026: the owner ruled all seven points; the briefs are `slices/GR2a.md`, `GR3a.md`, `AD3a.md` and `RM1a.md` (this paper is kept as the record of the questions). AD3, RM1, GR2 and GR3: were DRAFTS (the conductor, the night of 23 November 2026)

**The owner asked for a part for every build whose needs are met and that has nothing cut. These four are met on the plan's own needs (PL3, PL4, PL9, PL10) and none has a slice, but three read-only scouts found that none can start without the owner's rulings, and they share the first one. No row is written, so no builder can start any of them.** Same treatment as PL7f and IS6.

## The shared blocker: no GOV.UK tree exists on main

`OspreyFlow_Core/apps/pages` holds the Default tree only (`tree-default`, its layout, home stub, Studio frame, releases and dataset-map pages; tests under `test/default`; the keyboard walkthrough flat in `keyboard`). **There is no `tree-govuk` folder, no `OSPREY_PAGES_TREE` switch, no `govuk-frontend` in the package, and the design, colour, words and branches gates read only the Default tree's folders (`PAGES_COPY_ROOTS` in `OspreyFlow_Build/tools/layout.py`); a GOV.UK tree would be read by none of them until that list and `test_design_gates_reach.py` change together.** The plan's builds AD3, RM1, GR2, GR3 are GOV.UK-tree pages (ADR-152 decisions 1, 4, 6). Whichever of them started first would create the tree, the switch, the gates' reach and the dependency.

## The owner's rulings these four need (the scouts' lists, merged)

1. **Which build creates the GOV.UK tree** (folder, the `OSPREY_PAGES_TREE` switch, the gates' reach, the route list the parity test reads, the keyboard folder's layout: flat or per tree), and **may a GOV.UK-tree page exist before its Default twin does** (no rule forbids it; ADR-152 decisions 4 and 12 say every function is built this way with its scenario first).
2. **Which functions AD3 and RM1 are.** The plan's text is not in the repository; the scouts read them as `admin` and `alerts-rules-watches` in `OspreyFlow_Core/apps/pages/FUNCTIONS.yaml` (slice "R7"), and `needs-you`.
3. **Scenario ids:** `admin` and `needs-you` have none; Reports (`reports`) and Help (`top-bar-home-help`) have none in `spec/08`; Assessment has A13 to A15; alerts, rules and watches has B12, B13, B14, B20. ADR-152 decision 12 needs a scenario before a page.
4. **Charts (GR3):** no chart helper exists in `packages/glass-shared`; the React bars are divs with inline styles, which ADR-152 decision 8 bans; `spec/02_GLASS_FRONTEND.md` names Apache ECharts, which no pages package uses. **Plain SVG and classes, or a library; no inline style either way.**
5. **The Home path** (`/` is owned by the pages app: a GOV.UK Home needs another path or a ruling), **the split of the `reports` row** (figures versus dashboards) **and of `top-bar-home-help`** (the top bar is R1).
6. **Licence and `spec/00` section 7 entry for `govuk-frontend`** (the owner's licence register).
7. **Whether a non-viewer gets 404 or 403 at the report route's viewer dependency** (the scout could not tell; it decides the existence-oracle words: rule 7).

## The first slices, once ruled (the scouts' proposals)

- **GR2a:** a GOV.UK Help page with static role words from `glass-shared/src/help/roles.ts`: no Conduit call, no chart, no write. Tests: a vitest file under `test/govuk`, a keyboard spec, and a pure scenario test. Must not touch `apps/workspace`, `services/api`, the Makefile, `ci.yml` or the harness.
- **GR3a:** the alert monitoring board as a table, no chart, **after ruling 4.** Reads `GET /v1/investigations/{id}/reports` (READ_REPORTS; alerts the reader cannot see are left out of every total; past the bound the route answers 409); the page draws only what it receives; the test `test_the_alert_monitoring_page_shows_only_the_readers_own_counts` (ADR-152 I15) is the one to write red first.
- **AD3a / RM1a:** one read-only page each (the Admin People list through `/v1/admin/people/rows`; the alert monitoring board for RM1), each with its with-right and without-right tests (rule 4), scripts off, and its own keyboard case (rule 13). The Conduit filters; the page filters nothing after retrieval (decision 5).
- **Every part's brief carries:** never merge another part's unmerged tip; a finding that names a key, a credential or a security rule is stopped and reported.
