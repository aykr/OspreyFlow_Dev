# The GOV.UK identity spec: runs on record (slice PL7c, round 2)

`identity.spec.ts` is invariant I9's browser proof (ADR-152): run it with `npm run test:govuk --workspace apps/pages` (Playwright,
Chromium, no server and no network: a page assembled from the real `tokens.css`, the stylesheet `sync_govuk_assets.mjs` writes for a
default build and for a build with the switch on, `applyBrand` from `glass-shared` and `harness/govuk_chrome.js`, with a gov.uk
address given to the browser by request interception). Its CI job is `ci-wiring.patch` beside this file (it passes `git apply
--check`), for the owner to apply: until it is applied nothing in `make ci` or `npm test --workspace apps/pages` runs it (the
pages' vitest takes `test/**/*.test.ts` only), so the runs below are the record.

Rule 15: each fault planted in the real file, the spec shown red, the file restored, the spec green again.

| Planted fault (restored after) | Red | Green after |
| --- | --- | --- |
| `tokens.css` names the face under `data-govuk-identity="on"` alone (the first round's rule: no address condition) | "switch on, off gov.uk" | all six |
| `sync_govuk_assets.mjs` leaves GOV.UK Frontend's font stacks naming the face (the gating lost) | "switch on, off gov.uk", "a build that holds the face, with the switch off at run time" and "means nothing under the OspreyFlow brand" | all six |
| `govuk_chrome.js` draws the organisation's name and drops the service's (round 3's header fault) | "switch off, on a gov.uk address" and "switch off, off gov.uk" (the header must also name the service) | all six |
| `govuk_chrome.js` reads a settings object with no `govukIdentity` key as identity ON (`given === true \|\| given === undefined`, round 7's change) | "switch off, on a gov.uk address", "switch off, off gov.uk" and "a build that holds the face, with the switch off at run time" (3 failed, 3 passed) | all six |

Green run, 23 November 2026 (round 3): 6 passed.

Green run, 23 November 2026 (round 8, at the commit that makes a missing key mean off): `npm run test:govuk` in `apps/pages`, 6 passed, the spec unchanged since round 3. The three cases above fail against round 7's script and pass against this one.

---

# The GOV.UK tree's keyboard runner: runs on record (slice GR2a, round 2)

The runner is `npm run test:keyboard --workspace apps/pages` (it runs the Default tree's walkthrough in `keyboard/`, then this
folder's config; `npm run test:keyboard:govuk --workspace apps/pages` runs this folder's `keyboard/` and `scripts-off/` alone; one config, `playwright.config.ts`, serves this folder and PL7c's `identity.spec.ts`, and `npm run test:govuk` runs all three). Playwright, Chromium, the real pages
server started for the `govuk` tree inside each case. Nothing in `make ci` or `npm test --workspace apps/pages` runs it until the
owner applies `ci-wiring.patch` (this folder), so this record is what shows the cases ran. The patch passes `git apply --check`
against main and adds two jobs, PL7c's `govuk-identity` (above) and this slice's `pages-keyboard`, in one hunk (both patches wrote the same place); **it replaces `keyboard/ci-wiring.patch`, which adds a job of the same name (apply one,
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
