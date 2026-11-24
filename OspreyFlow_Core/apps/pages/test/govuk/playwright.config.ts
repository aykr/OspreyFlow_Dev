import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

// The GOV.UK tree's own page-level runner (slice GR2a; ADR-152 decision 6, "one folder per tree"; `CLAUDE.md` rule 13): Playwright
// against the pages server started in the test itself for the `govuk` tree, with the real assets built to a scratch folder and the
// in-memory store, on a free port, so no deployment, stack or Valkey is touched. `keyboard/` walks the tab order with scripts on and
// `scripts-off/` walks the same page with scripts switched off (decision 6 and invariant I4); a later page adds its own cases beside
// these. The Default tree's walkthrough is where it was built (`keyboard/playwright.config.ts`); `npm run test:keyboard` runs both.
export default defineConfig({
  testDir: ".",
  testMatch: /(?:keyboard|scripts-off)\/.*\.spec\.ts$/,
  timeout: 60_000,
  workers: 1,
  // Results go to the machine's temporary folder, never into the checkout.
  outputDir: join(tmpdir(), "ospreyflow-pages-govuk-results"),
  // Chromium unless `PAGES_KEYBOARD_BROWSER` names `firefox` or `webkit`, as the Default tree's runner does.
  use: { locale: "en-GB", browserName: (process.env["PAGES_KEYBOARD_BROWSER"] ?? "chromium") as "chromium" | "firefox" | "webkit" },
});
