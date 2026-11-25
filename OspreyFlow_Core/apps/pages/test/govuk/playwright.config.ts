import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

// The GOV.UK identity runner (slice PL7c; ADR-152 invariant I9): Playwright against a page assembled here from the real
// stylesheets the build writes, served by the browser's own request interception, so no server, port, stack or deployment
// is touched and a gov.uk address needs no network.
export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts$/,
  timeout: 60_000,
  workers: 1,
  outputDir: join(tmpdir(), "ospreyflow-pages-govuk-results"),
  use: { locale: "en-GB", browserName: "chromium" },
});
