# The GOV.UK tree's keyboard runner: runs on record (slice GR2a, round 2)

The runner is `npm run test:keyboard --workspace apps/pages` (it runs the Default tree's walkthrough in `keyboard/`, then this
folder's config; `npm run test:keyboard:govuk --workspace apps/pages` runs this folder alone). Playwright, Chromium, the real pages
server started for the `govuk` tree inside each case. Nothing in `make ci` or `npm test --workspace apps/pages` runs it until the
owner applies `ci-wiring.patch` (this folder), so this record is what shows the cases ran. The patch passes `git apply --check`
against main and adds the `pages-keyboard` job; **it replaces `keyboard/ci-wiring.patch`, which adds a job of the same name (apply one,
never both).**

Cases: `keyboard/help.spec.ts` HK1 to HK4 (scripts on), `scripts-off/help.spec.ts` HO1 and HO2 (`javaScriptEnabled: false`). Neither
spec needed a repair: `page.evaluate` still runs with scripts switched off (Playwright evaluates over the browser's debugging
protocol, not through the page's own scripts), and the pages carry no script of their own, so what HO1 and HO2 walk is the page a
reader with scripts off gets.

Rule 15: each fault below was planted in the tree's own template and restored after; the same six cases were run each time.

| Planted fault (restored after) | Red | Green after |
| --- | --- | --- |
| the "Roles" link of the section list removed from `help.njk` (a tab stop gone) | HK1, HO1 | all six |
| the "Back to Home" link removed from `help.njk` | HK1, HK3, HO1, HO2 | all six |
| the skip link removed from `layout.njk` | HK1, HK2, HO1, HO2 | all six |

Green run, 24 November 2026, on the round's tree: `npm run test:keyboard` gave 17 passed (the Default tree's) and 6 passed (this
folder's: HK1 to HK4, HO1 and HO2).
