# The GOV.UK identity spec: runs on record (slice PL7c, round 2)

`identity.spec.ts` is invariant I9's browser proof (ADR-152): run it with `npm run test:govuk --workspace apps/pages` (Playwright,
Chromium, no server and no network: a page assembled from the real `tokens.css`, the stylesheet `sync_govuk_assets.mjs` writes for a
default build and for a build with the switch on, `applyBrand` from `glass-shared` and `harness/govuk_chrome.js`, with a gov.uk
address given to the browser by request interception). Its CI job is the owner's diff: until it is applied nothing in `make ci` or
`npm test --workspace apps/pages` runs it, so the runs below are the record.

Rule 15: each fault planted in the real file, the spec shown red, the file restored, the spec green again.

| Planted fault (restored after) | Red | Green after |
| --- | --- | --- |
| `tokens.css` names the face under `data-govuk-identity="on"` alone (the first round's rule: no address condition) | "switch on, off gov.uk" | all six |
| `sync_govuk_assets.mjs` leaves GOV.UK Frontend's font stacks naming the face (the gating lost) | "switch on, off gov.uk", "a build that holds the face, with the switch off at run time" and "means nothing under the OspreyFlow brand" | all six |

Green run, 23 November 2026: 6 passed.
