import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

// The pages' own keyboard runner (slice IS5a; `CLAUDE.md` rule 13): Playwright against the pages server started in the test
// itself, with a fake Conduit, the real assets built to a scratch folder, and the in-memory store. No port is fixed: each
// case starts its own server on a free one, and no deployment, stack or Valkey is touched.
export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts$/,
  timeout: 60_000,
  workers: 1,
  // Results go to the machine's temporary folder, never into the checkout.
  outputDir: join(tmpdir(), "ospreyflow-pages-keyboard-results"),
  use: { locale: "en-GB" },
});
