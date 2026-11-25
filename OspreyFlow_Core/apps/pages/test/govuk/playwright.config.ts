import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

// The GOV.UK tree's Playwright runner (ADR-152 decision 6, "one folder per tree"; `CLAUDE.md` rule 13), one config for the folder's two
// kinds of spec, both Chromium with no stack, Valkey or deployment touched:
//   * `identity.spec.ts` (slice PL7c; invariant I9): a page assembled from the real stylesheets the build writes, served by the browser's
//     own request interception, so no server or port is needed and a gov.uk address needs no network. `npm run test:govuk`.
//   * `keyboard/` and `scripts-off/` (slice GR2a): the pages server started inside each case for the `govuk` tree, the real assets built
//     to a scratch folder and the in-memory store, on a free port; the tab order with scripts on and the same page with scripts off
//     (decision 6, invariant I4). `npm run test:keyboard:govuk`, and `npm run test:keyboard` runs these after the Default tree's
//     walkthrough (`keyboard/playwright.config.ts`).
// `test:govuk` takes no filter, so it runs the whole folder; the two keyboard scripts name `keyboard/ scripts-off/`.
export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts$/,
  timeout: 60_000,
  workers: 1,
  // Results go to the machine's temporary folder, never into the checkout.
  outputDir: join(tmpdir(), "ospreyflow-pages-govuk-results"),
  // Chromium unless `PAGES_KEYBOARD_BROWSER` names `firefox` or `webkit`, as the Default tree's runner does.
  use: { locale: "en-GB", browserName: (process.env["PAGES_KEYBOARD_BROWSER"] ?? "chromium") as "chromium" | "firefox" | "webkit" },
});
